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

from . import base
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
    ("emotes", "Emotes", "native"),
    ("animations", "Animations", "native"),
]
# kinds where icons that are already monochrome (tray symbols, toolbar buttons) are
# left alone and inherited, and only coloured ones are converted
KEEP_MONO = ("status", "actions", "animations")

CONTEXT_NAMES = [c for c, _, _ in CONTEXTS]

# Folder colour variants (folder-red-music...), as in Papirus: only the default and black
# sets are used, the others show the matching black folder.
_COLOUR_VARIANT = re.compile(
    r"^(folder|user)-(adwaita|black|blue|bluegrey|breeze|brown|carmine|cyan|darkcyan|deeporange|"
    r"green|grey|indigo|magenta|nordic|orange|palebrown|paleorange|pink|red|teal|violet|white|"
    r"yaru|yellow)(-|$)")


SHAPE_TITLES = {"circle": "Circle", "squircle": "Squircle"}
TILE_CONTEXTS = [c for c, _, st in CONTEXTS if st == "tile"]


def variant_name(cfg, shape):
    """Installed theme name for a tile shape, e.g. Monotile-Squircle."""
    return f"{cfg['name']}-{SHAPE_TITLES[shape]}"


def variant_names(cfg):
    return [variant_name(cfg, s) for s in SHAPE_TITLES]


def light_name(cfg, shape):
    """Light-scheme theme name for a tile shape, e.g. Monotile-Light-Circle."""
    return f"{cfg['name']}-Light-{SHAPE_TITLES[shape]}"


def light_names(cfg):
    return [light_name(cfg, s) for s in SHAPE_TITLES]


def light_fallback(fallback):
    """Fallback for the light themes: Monotile-Base-Dark -> Monotile-Base-Light (dark panel and
    tray icons). Another X-Dark fallback becomes "X-Light,X" or X, whichever exists."""
    base_name = fallback
    for suffix in ("-Dark", "-dark"):
        if fallback.endswith(suffix) and Theme(fallback[:-len(suffix)]).exists:
            base_name = fallback[:-len(suffix)]
    light = f"{base_name}-Light"
    if not Theme(light).exists:
        return base_name
    return light if base_name == base.SOURCE else f"{light},{base_name}"


def generate_all(cfg, fallback, dry_run=False, workers=None):
    """Build both themes. Monotile-Circle holds every icon; Monotile-Squircle holds
    only the tile icons (apps, menu categories) and inherits the rest from Circle,
    so the second shape costs a few seconds and a few MB instead of a full copy."""
    circle = dict(cfg, name=variant_name(cfg, "circle"), shape="circle")
    squircle = dict(cfg, name=variant_name(cfg, "squircle"), shape="squircle",
                    contexts=[c for c in cfg["contexts"] if c in TILE_CONTEXTS] or ["apps"])
    if not dry_run and any(n in base.NAMES for n in (cfg["source"] or base.SOURCE, *fallback.split(","))):
        base.install()
    out = {
        circle["name"]: generate(circle, fallback, dry_run=dry_run, workers=workers),
        squircle["name"]: generate(squircle, f"{circle['name']},{fallback}", dry_run=dry_run, workers=workers),
    }
    if not dry_run:
        lfb = light_fallback(fallback)
        lc, ls = light_name(cfg, "circle"), light_name(cfg, "squircle")
        derive_light(circle["name"], lc, lfb, workers=workers)
        derive_light(squircle["name"], ls, f"{lc},{lfb}", workers=workers)
    return out


def remove_all(cfg):
    """Delete both themes and a legacy single-theme folder from monotile 0.1."""
    for name in variant_names(cfg) + light_names(cfg) + [cfg["name"]]:
        remove(dict(cfg, name=name))
    base.remove()


def black_variant(places_index, name, path):
    """Every folder has a black colour variant (folder-black-music, user-black-home...):
    use it for the "black" file style when there is one."""
    m = re.match(r"^(folder|user)(-.*)?$", name)
    if m:
        alt = places_index.get(f"{m.group(1)}-black{m.group(2) or ''}")
        if alt:
            return alt[1]
    return path


def default_source(name):
    return base.SOURCE


def style_of(cfg, ctx):
    return next(st for c, _, st in CONTEXTS if c == ctx) if ctx else None


FILE_CONTEXTS = ("places", "mimetypes")


def shape_for(cfg, ctx):
    if style_of(cfg, ctx) == "tile":
        return cfg["shape"]
    if ctx in FILE_CONTEXTS and cfg.get("file_style", "black") in ("grey", "black"):
        return "grey"
    return "native"


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
    src = Theme(source)
    # names the source draws as a folder, file type or device keep that native look
    # even when an app or menu category uses them; GTK looks names up regardless of
    # context, so a tile version would replace the folder icon in the file manager too
    native_names = set()
    for _, fd_context, style in CONTEXTS:
        if style == "native" and fd_context in ("Places", "MimeTypes", "Devices"):
            native_names |= set(src.index(fd_context))

    def add(ctx, name, path):
        if ctx in TILE_CONTEXTS and name in native_names:
            return
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
            if ("apps", name) in jobs or name in native_names:
                continue
            path = resolver.resolve(name)
            if path or name in overrides:
                add("apps", name, path)
            else:
                skipped.append((app.desktop_id, "icon not found"))
        for name in overrides:                    # overrides for icons no app uses yet
            jobs.setdefault(("apps", name), ("override", overrides[name]))

    if "apps" in contexts:
        # every app-style icon the source theme has, not only those of installed apps,
        # so the theme stays complete for settings modules, dialogs and future apps
        for name, (_, path) in sorted(src.index("Applications").items()):
            if _safe(name) and ("apps", name) not in jobs:
                add("apps", name, path)

    if "categories" in contexts:
        for name in sorted(menu_category_icons()):
            add("categories", name, resolver.resolve(name))
    for ctx, fd_context, _ in CONTEXTS[2:]:
        if ctx not in contexts:
            continue
        index = src.index(fd_context)
        style = cfg.get("file_style", "black")
        for name, (_, path) in sorted(index.items()):
            if not _safe(name):
                continue
            if ctx == "places" and style == "black":
                # every colour variant (folder-red-music…) shows the matching black folder;
                # they share its source image, so they become links, not new conversions
                path = black_variant(index, _COLOUR_VARIANT.sub(r"\1\3", name), path)
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
        stats = _generate(cfg, fallback, tdir, dry_run, workers)
        if not dry_run and _drop_dangling(cfg, tdir):
            # an alias pointed at a file that was removed this run: rebuild those once
            again = _generate(cfg, fallback, tdir, dry_run, workers)
            for k in ("converted", "linked", "kept", "overrides"):
                stats[k] += again[k]
            stats["failed"] += again["failed"]
            stats["changed"] = True
        return stats
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


def _drop_dangling(cfg, tdir):
    """Delete links whose target is gone and forget them in the manifest, so the next
    pass regenerates them. Returns True if anything was dropped."""
    dangling = []
    for root, _, files in os.walk(tdir):
        for f in files:
            p = os.path.join(root, f)
            if os.path.islink(p) and not os.path.exists(p):
                dangling.append(p)
    if not dangling:
        return False
    mpath = _manifest_path(cfg)
    with open(mpath, encoding="utf-8") as fh:
        manifest = json.load(fh)
    for p in dangling:
        ctx, fname = os.path.basename(os.path.dirname(p)), os.path.basename(p)
        manifest.pop(f"{ctx}/{os.path.splitext(fname)[0]}", None)
        os.unlink(p)
    C.atomic_write(mpath, json.dumps(manifest, indent=1, sort_keys=True))
    return True


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


# ------------------------------------------------------------------ light scheme

# dark tile (30) -> light grey (218), white glyph (242) -> near black (16), greys in between
_LIGHT_LUT = [max(0, min(255, round(246.6 - 0.953 * v))) for v in range(256)]


def _lighten(job):
    """Worker: write the light-scheme copy of one dark icon (same alpha, tones flipped)."""
    src, dst = job
    from PIL import Image
    im = Image.open(src).convert("RGBA")
    r, g, b, a = im.split()
    out = Image.merge("RGBA", [c.point(_LIGHT_LUT) for c in (r, g, b)] + [a])
    buf = io.BytesIO()
    out.save(buf, "PNG")
    C.atomic_write(dst, buf.getvalue(), mode="wb")


def derive_light(dark_name, name, inherits, workers=None):
    """Make the light scheme of a generated theme: every tile and line-art icon with its
    tones flipped (black symbol on a light-grey tile), folders and file types shared
    with the dark theme through folder links (the black folders suit both).
    Incremental: only icons newer than their light copy are redrawn."""
    sdir = os.path.join(C.icons_dir(), dark_name)
    tdir = os.path.join(C.icons_dir(), name)
    if os.path.isdir(tdir) and not os.path.exists(os.path.join(tdir, MARKER)) and os.listdir(tdir):
        raise RuntimeError(f"{tdir} exists and was not created by monotile; pick another name")
    os.makedirs(tdir, exist_ok=True)
    open(os.path.join(tdir, MARKER), "a").close()
    todo, changed = [], False
    for size in sorted(os.listdir(sdir)):
        sd = os.path.join(sdir, size)
        if not os.path.isdir(sd):
            continue
        for ctx in sorted(os.listdir(sd)):
            src_ctx, dst_ctx = os.path.join(sd, ctx), os.path.join(tdir, size, ctx)
            if ctx in FILE_CONTEXTS:
                target = os.path.relpath(os.path.realpath(src_ctx), os.path.dirname(dst_ctx))
                if not (os.path.islink(dst_ctx) and os.readlink(dst_ctx) == target):
                    if os.path.isdir(dst_ctx) and not os.path.islink(dst_ctx):
                        shutil.rmtree(dst_ctx)
                    _link(os.path.realpath(src_ctx), dst_ctx)
                    changed = True
                continue
            if os.path.islink(dst_ctx):
                os.unlink(dst_ctx)
            os.makedirs(dst_ctx, exist_ok=True)
            want = set()
            with os.scandir(src_ctx) as it:
                for e in it:
                    want.add(e.name)
                    dst = os.path.join(dst_ctx, e.name)
                    if e.is_symlink():                   # aliases stay aliases
                        link = os.readlink(e.path)
                        if not (os.path.islink(dst) and os.readlink(dst) == link):
                            if os.path.lexists(dst):
                                os.unlink(dst)
                            os.symlink(link, dst)
                            changed = True
                    elif not os.path.exists(dst) or os.lstat(dst).st_mtime_ns < e.stat().st_mtime_ns \
                            or os.path.islink(dst):
                        if os.path.islink(dst):
                            os.unlink(dst)
                        todo.append((e.path, dst))
            for f in set(os.listdir(dst_ctx)) - want:    # icons the dark theme dropped
                os.unlink(os.path.join(dst_ctx, f))
                changed = True
    if len(todo) > 4:
        with cf.ProcessPoolExecutor(max_workers=workers or os.cpu_count()) as ex:
            list(ex.map(_lighten, todo, chunksize=64))
    else:
        for j in todo:
            _lighten(j)
    idx = open(os.path.join(sdir, "index.theme"), encoding="utf-8").read()
    idx = re.sub(r"(?m)^Name=.*$", f"Name={name}", idx, count=1)
    idx = re.sub(r"(?m)^Inherits=.*$", f"Inherits={inherits},hicolor" if inherits != "hicolor" else "Inherits=hicolor", idx, count=1)
    idx = re.sub(r"(?m)^Comment=.*$", "Comment=Monochrome icons for light themes, generated by monotile", idx, count=1)
    C.atomic_write(os.path.join(tdir, "index.theme"), idx)
    if todo or changed or not os.path.exists(os.path.join(tdir, "icon-theme.cache")):
        update_icon_cache(tdir)
    return {"redrawn": len(todo), "changed": bool(todo) or changed}


def remove(cfg):
    """Delete the generated theme folder (only if monotile created it) and its manifest."""
    tdir = C.theme_dir(cfg)
    if os.path.isdir(tdir) and os.path.exists(os.path.join(tdir, MARKER)):
        shutil.rmtree(tdir)
    mpath = _manifest_path(cfg)
    if os.path.exists(mpath):
        os.unlink(mpath)
