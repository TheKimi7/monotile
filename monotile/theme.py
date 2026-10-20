"""Generate the icon theme: convert icons, write index.theme, refresh the icon cache.

Covered contexts (each in its own folder of the theme):
  apps, categories                         on a tile (circle or squircle, like apps)
  places, mimetypes, devices, status,      "native": the icon keeps its own shape,
  emblems                                  drawn as a flat white stencil

Symbolic icons (panel, tray, toolbar) are already monochrome and are inherited untouched.

Incremental: a manifest records, per output, the source file (path, mtime, size) and a
hash of the settings that produced it. Unchanged icons are skipped, outputs whose
source went away are deleted (only files the manifest owns), names that share one
image are converted once and symlinked, conversions run in parallel, and a lock
prevents concurrent runs.
"""
import concurrent.futures as cf
import fcntl
import hashlib
import io
import json
import os
import re
import shutil
import subprocess

from . import config as C
from . import poster
from .iconfile import render
from .lookup import SAFE_NAME, IconResolver, Theme, installed_apps, menu_category_icons

MARKER = ".monotile"          # identifies a theme folder we created
OVERRIDE_EXTS = (".svg", ".png")

# folder in the theme, freedesktop Context, style ("tile" = the configured shape)
CONTEXTS = [
    ("apps", "Applications", "tile"),
    ("categories", "Categories", "tile"),
    ("places", "Places", "native"),
    ("mimetypes", "MimeTypes", "native"),
    ("devices", "Devices", "native"),
    ("status", "Status", "native"),
    ("emblems", "Emblems", "native"),
    ("actions", "Actions", "native"),
]
# kinds where icons that are already monochrome (tray symbols, toolbar buttons) are
# left alone and inherited, and only coloured ones are converted
KEEP_MONO = ("status", "actions")
# session and system icons the shell shows outside any app entry (menu power, lock and
# log-out buttons, settings): converted like apps even though no .desktop file uses them
SYSTEM_APP_ICON = re.compile(r"^system-")
CONTEXT_NAMES = [c for c, _, _ in CONTEXTS]

# Papirus ships every folder in ~25 colours; only the default set is ever used
# unless the user recolours folders, so the variants are not converted.
_COLOUR_VARIANT = re.compile(
    r"^(folder|user)-(adwaita|black|blue|bluegrey|breeze|brown|carmine|cyan|darkcyan|deeporange|"
    r"green|grey|indigo|magenta|nordic|orange|palebrown|paleorange|pink|red|teal|violet|white|"
    r"yaru|yellow)(-|$)")


def default_source(name):
    for t in ("Papirus", "Papirus-Dark"):
        if t != name and Theme(t).exists:
            return t
    return "hicolor"


def style_of(cfg, ctx):
    return next(st for c, _, st in CONTEXTS if c == ctx) if ctx else None


def shape_for(cfg, ctx):
    return cfg["shape"] if style_of(cfg, ctx) == "tile" else "native"


def settings_hash(cfg, shape):
    key = {"algo": poster.ALGO_VERSION, "shape": shape, "tones": cfg["tones"], "sizes": cfg["sizes"]}
    return hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()[:16]


def find_overrides():
    """{icon name: path} for user-made icons in the overrides folder."""
    out, d = {}, C.overrides_dir()
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            base, ext = os.path.splitext(f)
            if ext.lower() in OVERRIDE_EXTS and SAFE_NAME.match(base) and ".." not in base:
                out[base] = os.path.join(d, f)
    return out


def _safe(name):
    return bool(SAFE_NAME.match(name)) and ".." not in name and not name.endswith("-symbolic")


def plan(cfg):
    """Work out every (context, name) to produce and where it comes from.

    Returns (source theme, {(ctx, name): (kind, path)}, skipped apps)."""
    source = cfg["source"] or default_source(cfg["name"])
    resolver = IconResolver(source, skip=(cfg["name"],))
    overrides = find_overrides()
    contexts = cfg["contexts"]
    jobs, skipped = {}, []

    def add(ctx, name, path):
        if name in overrides:
            jobs[(ctx, name)] = ("override", overrides[name])
        elif path:
            jobs[(ctx, name)] = ("convert", path)

    if "apps" in contexts:
        for app in installed_apps():
            name = app.icon_name
            if name is None:
                skipped.append((app.desktop_id, "icon is a file path" if app.icon_is_path else "unsafe icon name"))
                continue
            if ("apps", name) in jobs:
                continue
            path = resolver.resolve(name)
            if path or name in overrides:
                add("apps", name, path)
            else:
                skipped.append((app.desktop_id, "icon not found"))
        for name in overrides:                    # overrides for icons no app uses yet
            jobs.setdefault(("apps", name), ("override", overrides[name]))

    src = Theme(source)
    if "apps" in contexts:
        for name, (_, path) in sorted(src.index("Applications").items()):
            if SYSTEM_APP_ICON.match(name) and _safe(name) and ("apps", name) not in jobs:
                add("apps", name, path)
    if "categories" in contexts:
        for name in sorted(menu_category_icons()):
            add("categories", name, resolver.resolve(name))
    for ctx, fd_context, _ in CONTEXTS[2:]:
        if ctx not in contexts:
            continue
        for name, (_, path) in sorted(src.index(fd_context).items()):
            if _safe(name) and not (ctx == "places" and _COLOUR_VARIANT.match(name)):
                add(ctx, name, path)
    return source, jobs, skipped


def _key(kind, path, shash):
    st = os.stat(path)
    return {"kind": kind, "src": os.path.realpath(path), "mtime": st.st_mtime_ns, "size": st.st_size, "settings": shash}


def _out(tdir, ctx, name, size):
    return os.path.join(tdir, f"{size}x{size}", ctx, name + ".png")


def is_monochrome(path):
    """True if an icon has (almost) no coloured pixels, e.g. a white tray symbol."""
    im = render(path, 64)
    px = [p for p in im.getdata() if p[3] > 128]
    if not px:
        return True
    coloured = sum(1 for r, g, b, _ in px if max(r, g, b) - min(r, g, b) > 40)
    return coloured < 0.03 * len(px)


def _convert_job(job):
    """Worker: (kind, path, shape, tones, sizes, keep_mono) -> {size: PNG bytes},
    or None when the icon is already monochrome and should be inherited as it is."""
    kind, path, shape, tones, sizes, keep_mono = job
    if keep_mono and kind != "override" and is_monochrome(path):
        return None
    if kind == "override":
        images = {s: render(path, s) for s in sizes}
    else:
        images, _ = poster.convert(path, sizes, shape, tones)
    out = {}
    for s, im in images.items():
        buf = io.BytesIO()
        im.save(buf, "PNG")
        out[s] = buf.getvalue()
    return out


def _link(target, link):
    """Atomically make `link` a relative symlink to `target`."""
    os.makedirs(os.path.dirname(link), exist_ok=True)
    tmp = link + ".tmp-link"
    if os.path.lexists(tmp):
        os.unlink(tmp)
    os.symlink(os.path.relpath(target, os.path.dirname(link)), tmp)
    os.replace(tmp, link)


def write_index(cfg, tdir, fallback, used_contexts):
    """Every size folder is Scalable over the range above the next smaller size, and the
    largest one up to 512 px, so a request for any size picks the nearest larger image
    and the toolkit scales it (Fixed folders made 150-400 px requests snap to 256)."""
    sizes = sorted(cfg["sizes"])
    ranges = {s: (8 if i == 0 else sizes[i - 1] + 1, 512 if i == len(sizes) - 1 else s)
              for i, s in enumerate(sizes)}
    dirs = []
    for s in sizes:
        for ctx, fd_context, _ in CONTEXTS:
            if ctx in used_contexts:
                dirs.append((f"{s}x{s}/{ctx}", s, fd_context))
    lines = ["[Icon Theme]", f"Name={cfg['name']}",
             "Comment=Monochrome icons generated by monotile",
             f"Inherits={fallback},hicolor" if fallback != "hicolor" else "Inherits=hicolor",
             "Directories=" + ",".join(d for d, _, _ in dirs), ""]
    for d, s, fd_context in dirs:
        lo, hi = ranges[s]
        lines += [f"[{d}]", f"Size={s}", f"Context={fd_context}", "Type=Scalable",
                  f"MinSize={lo}", f"MaxSize={hi}", ""]
    C.atomic_write(os.path.join(tdir, "index.theme"), "\n".join(lines))


def update_icon_cache(tdir):
    exe = shutil.which("gtk-update-icon-cache") or shutil.which("gtk4-update-icon-cache")
    if exe:
        subprocess.run([exe, "-f", "-t", "-q", tdir], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def generate(cfg, fallback, dry_run=False, log=print, workers=None):
    """Bring the theme up to date. Returns a stats dict."""
    tdir = C.theme_dir(cfg)
    if os.path.isdir(tdir) and not os.path.exists(os.path.join(tdir, MARKER)) and os.listdir(tdir):
        raise RuntimeError(f"{tdir} exists and was not created by monotile; pick another name")
    os.makedirs(C.cache_dir(), exist_ok=True)
    lock = open(os.path.join(C.cache_dir(), "lock"), "w")
    fcntl.flock(lock, fcntl.LOCK_EX)
    try:
        return _generate(cfg, fallback, tdir, dry_run, workers)
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


def _manifest_path(cfg):
    return os.path.join(C.cache_dir(), "manifest-%s.json" % cfg["name"])


def _generate(cfg, fallback, tdir, dry_run, workers):
    try:
        with open(_manifest_path(cfg), encoding="utf-8") as f:
            manifest = json.load(f)
    except (OSError, ValueError):
        manifest = {}
    if manifest and not all("/" in k for k in manifest):        # v1 manifest: apps only
        manifest = {f"apps/{k}": v for k, v in manifest.items()}
    source, jobs, skipped = plan(cfg)
    stats = {"source": source, "fallback": fallback, "converted": 0, "overrides": 0, "linked": 0, "kept": 0,
             "unchanged": 0, "removed": 0, "failed": [], "skipped": skipped,
             "contexts": sorted({c for c, _ in jobs})}

    wanted = {f"{c}/{n}" for c, n in jobs}
    for mkey in sorted(set(manifest) - wanted):                 # sources that went away
        stats["removed"] += 1
        if not dry_run:
            ctx, name = mkey.split("/", 1)
            for s in manifest[mkey].get("sizes") or []:
                p = _out(tdir, ctx, name, s)
                if os.path.lexists(p):
                    os.unlink(p)
            del manifest[mkey]

    # what needs (re)doing, grouped so one source image is converted once per shape
    todo, groups = {}, {}
    for (ctx, name), (kind, path) in sorted(jobs.items()):
        shape = shape_for(cfg, ctx)
        try:
            # status icons also depend on the "keep already-monochrome icons" rule
            key = _key(kind, path, settings_hash(cfg, shape + ("+keep-mono" if ctx in KEEP_MONO else "")))
        except OSError as e:
            stats["failed"].append((f"{ctx}/{name}", str(e)))
            continue
        mkey = f"{ctx}/{name}"
        old = manifest.get(mkey, {})
        outs = [_out(tdir, ctx, name, s) for s in cfg["sizes"]]
        same = {k: old.get(k) for k in key} == key
        if same and (old.get("passthrough") or all(os.path.lexists(p) for p in outs)):
            stats["unchanged"] += 1
            continue
        todo[mkey] = (ctx, name, kind, key, old)
        groups.setdefault((key["src"], kind, shape, ctx in KEEP_MONO), []).append(mkey)

    if dry_run:
        for mkeys in groups.values():
            stats["overrides" if todo[mkeys[0]][2] == "override" else "converted"] += 1
            stats["linked"] += len(mkeys) - 1
        stats["changed"] = bool(groups) or stats["removed"] > 0
        return stats

    jobs_list = [(g, (todo[m[0]][2], g[0], g[2], cfg["tones"], cfg["sizes"], g[3])) for g, m in groups.items()]
    results = {}
    if len(jobs_list) > 4:
        with cf.ProcessPoolExecutor(max_workers=workers or os.cpu_count()) as ex:
            futures = {ex.submit(_convert_job, j): g for g, j in jobs_list}
            for fut in cf.as_completed(futures):
                results[futures[fut]] = fut
    else:
        for g, j in jobs_list:
            f = cf.Future()
            try:
                f.set_result(_convert_job(j))
            except Exception as e:
                f.set_exception(e)
            results[g] = f

    changed = stats["removed"] > 0
    for g, mkeys in groups.items():
        try:
            pngs = results[g].result()
        except Exception as e:                                   # one bad icon never stops the run
            for m in mkeys:
                stats["failed"].append((m, f"{type(e).__name__}: {e}"))
            continue
        if pngs is None:                                         # already monochrome: inherit it
            for m in mkeys:
                ctx, name, kind, key, old = todo[m]
                for sz in set(old.get("sizes", [])) | set(cfg["sizes"]):
                    p = _out(tdir, ctx, name, sz)
                    if os.path.lexists(p):
                        os.unlink(p)
                manifest[m] = dict(key, sizes=[], passthrough=True)
                stats["kept"] += 1
            changed = True
            continue
        first = None
        for m in mkeys:
            ctx, name, kind, key, old = todo[m]
            for s in cfg["sizes"]:
                p = _out(tdir, ctx, name, s)
                if first is None or s not in first:
                    C.atomic_write(p, pngs[s], mode="wb")
                else:
                    _link(first[s], p)
            for s in set(old.get("sizes", [])) - set(cfg["sizes"]):    # sizes no longer wanted
                p = _out(tdir, ctx, name, s)
                if os.path.lexists(p):
                    os.unlink(p)
            if first is None:
                first = {s: _out(tdir, ctx, name, s) for s in cfg["sizes"]}
                stats["overrides" if kind == "override" else "converted"] += 1
            else:
                stats["linked"] += 1
            manifest[m] = dict(key, sizes=cfg["sizes"])
            changed = True

    os.makedirs(tdir, exist_ok=True)
    open(os.path.join(tdir, MARKER), "a").close()
    write_index(cfg, tdir, fallback, {m.split("/", 1)[0] for m, v in manifest.items() if not v.get("passthrough")})
    C.atomic_write(_manifest_path(cfg), json.dumps(manifest, indent=1, sort_keys=True))
    if changed or not os.path.exists(os.path.join(tdir, "icon-theme.cache")):
        update_icon_cache(tdir)
    stats["changed"] = changed
    return stats


def remove(cfg):
    """Delete the generated theme folder (only if monotile created it) and its manifest."""
    tdir = C.theme_dir(cfg)
    if os.path.isdir(tdir) and os.path.exists(os.path.join(tdir, MARKER)):
        shutil.rmtree(tdir)
    mpath = _manifest_path(cfg)
    if os.path.exists(mpath):
        os.unlink(mpath)
