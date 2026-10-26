"""monotile command line."""
import argparse
import os
import sys
import time

from . import __version__
from . import config as C
from . import base, desktop, theme, watch


def resolve_fallback(cfg, save=True):
    """The theme everything not converted is inherited from: monotile's own Monotile-Base-Dark
    unless another one was chosen with --fallback."""
    return cfg["fallback"] or base.DARK


def load_cfg(a, persist=False):
    cfg = C.load()
    for k in ("name", "source", "fallback", "shape", "tones", "contexts", "file_style"):
        v = getattr(a, k, None)
        if v is not None:
            cfg[k] = v
    cfg = C.validate(cfg)
    if persist:
        C.save(cfg)
    return cfg


# ------------------------------------------------------------------ commands

def cmd_preview(a):
    from .poster import convert
    from .preview import contact_sheet
    cfg = load_cfg(a)
    _, jobs, _ = theme.plan(cfg)
    ctx = a.context
    shape = theme.shape_for(cfg, ctx)
    items = [(n, p) for (c, n), (kind, p) in sorted(jobs.items()) if c == ctx and kind == "convert"]
    if a.limit:
        items = items[: a.limit]
    t = time.time()
    def one(p, s):
        if ctx == "status" and theme.is_monochrome(p):      # kept as it is, like generate does
            from .iconfile import render
            return render(p, s)
        return convert(p, (s,), shape, cfg["tones"])[0][s]
    sheet, failed = contact_sheet(items, one, a.columns)
    out = os.path.abspath(a.output)
    sheet.save(out)
    print(f"{len(items)} icons in {time.time() - t:.1f}s (failed {failed}) -> {out}")


def _report(stats, name, a, elapsed):
    verb = "would convert" if a.dry_run else "converted"
    print(f"{name}: {verb} {stats['converted']}, aliases {stats['linked']}, already mono {stats['kept']}, "
          f"overrides {stats['overrides']}, unchanged {stats['unchanged']}, removed {stats['removed']}, "
          f"failed {len(stats['failed'])} in {elapsed:.1f}s")
    print(f"  contexts: {', '.join(stats['contexts']) or '-'}   inherits: {stats['fallback']}")
    for item, why in stats["failed"]:
        print(f"  failed: {item}: {why}")


def _migrate_legacy(cfg):
    """monotile 0.1 made one theme named after cfg["name"]; switch to the matching
    variant if it was active, then delete it."""
    legacy = C.theme_dir(cfg)
    if os.path.exists(os.path.join(legacy, theme.MARKER)):
        if desktop.current_theme() == cfg["name"]:
            desktop.apply(theme.variant_name(cfg, cfg["shape"]))
        theme.remove(cfg)
        print(f"replaced the old single theme '{cfg['name']}' with {', '.join(theme.variant_names(cfg))}")


def _adopt_legacy(cfg):
    """Seed Monotile-Circle from a monotile 0.1 single theme (hard links, so it is
    instant and uses no extra space): its folder/file/device/status icons are
    identical, and only the tile icons get redone."""
    import shutil
    legacy = C.theme_dir(cfg)
    circle = C.theme_dir(dict(cfg, name=theme.variant_name(cfg, "circle")))
    if os.path.exists(os.path.join(legacy, theme.MARKER)) and not os.path.exists(circle):
        shutil.copytree(legacy, circle, symlinks=True, copy_function=os.link)
        old_m = os.path.join(C.cache_dir(), f"manifest-{cfg['name']}.json")
        new_m = os.path.join(C.cache_dir(), f"manifest-{theme.variant_name(cfg, 'circle')}.json")
        if os.path.exists(old_m) and not os.path.exists(new_m):
            shutil.copyfile(old_m, new_m)


def cmd_generate(a):
    if getattr(a, "contexts", None):
        a.contexts = [c.strip() for c in a.contexts.split(",") if c.strip()]
    cfg = load_cfg(a, persist=not a.dry_run)          # a dry run never writes settings
    fallback = resolve_fallback(cfg, save=not a.dry_run)
    t = time.time()
    if not a.dry_run:
        _adopt_legacy(cfg)
    results = theme.generate_all(cfg, fallback, dry_run=a.dry_run)
    if not a.quiet or any(s["failed"] for s in results.values()):
        for name, s in results.items():
            _report(s, name, a, time.time() - t)
        skipped = next(iter(results.values()))["skipped"]
        if a.verbose:
            for did, why in skipped:
                print(f"  skipped: {did} ({why})")
        elif skipped:
            print(f"  {len(skipped)} apps skipped (use -v to list): icons given as file paths or not found")
    if not a.dry_run:
        _migrate_legacy(cfg)
    active = desktop.current_theme()
    if a.refresh and not a.dry_run and active in results and any(s["changed"] for s in results.values()):
        desktop.refresh(active, fallback)


def cmd_apply(a):
    cfg = load_cfg(a, persist=True)
    fallback = resolve_fallback(cfg)
    if not all(os.path.exists(os.path.join(C.theme_dir(dict(cfg, name=n)), "index.theme"))
               for n in theme.variant_names(cfg)):
        theme.generate_all(cfg, fallback)
    name = theme.variant_name(cfg, cfg["shape"])
    keys = desktop.apply(name)
    _migrate_legacy(cfg)
    print(f"icon theme set to {name} ({', '.join(s for s, _ in keys)})")
    print("Switch shape any time with: apply --shape circle|squircle")
    print("Some panels cache icons: if one still shows the old icon, log out and back in.")


def cmd_revert(a):
    prev = desktop.revert()
    if prev:
        print("restored: " + ", ".join(f"{k.split()[0]} = {v}" for k, v in prev.items()))
    else:
        print("nothing to revert (monotile was not applied)")


def cmd_status(a):
    cfg = C.load()
    print(f"desktop:   {desktop.desktop_name()}")
    for name in theme.variant_names(cfg):
        tdir = C.theme_dir(dict(cfg, name=name))
        n = sum(1 for _, _, files in os.walk(tdir) for f in files if f.endswith(".png"))
        print(f"theme:     {name} ({'generated' if os.path.isdir(tdir) else 'not generated'}, {n} files)")
    print(f"active:    {desktop.current_theme()}")
    print(f"style:     {cfg['tones']} tones, applied shape {cfg['shape']}")
    print(f"source:    {cfg['source'] or theme.default_source(cfg['name'])}   "
          f"fallback: {cfg['fallback'] or '(set at first run)'}")
    print(f"overrides: {len(theme.find_overrides())} in {C.overrides_dir()}")
    print(f"watcher:   {watch.status()}")


def cmd_audit(a):
    import json
    from .audit import audit
    cfg = C.load()
    name = theme.variant_name(cfg, a.shape or cfg["shape"])
    kept = set()
    for variant in theme.variant_names(cfg):
        try:
            with open(os.path.join(C.cache_dir(), f"manifest-{variant}.json"), encoding="utf-8") as f:
                kept |= {k.split("/", 1)[1] for k, v in json.load(f).items() if v.get("passthrough")}
        except (OSError, ValueError):
            pass
    r = audit(name, cfg["source"] or theme.default_source(cfg["name"]), kept)
    print(f"{name}: {r['total']} icon names checked")
    print(f"  {r['ours']} drawn by monotile")
    print(f"  {len(r['kept'])} already monochrome, inherited unchanged on purpose")
    print(f"  {len(r['outside'])} still coming from another theme")
    print(f"  {len(r['missing'])} not found anywhere")
    for n, p in r["outside"][: a.limit]:
        print(f"    outside: {n}  ({p.split('/icons/')[-1]})")
    if len(r["outside"]) > a.limit:
        print(f"    ... and {len(r['outside']) - a.limit} more (use --limit)")
    return 0 if not r["outside"] else 1


def cmd_watch(a):
    if a.action == "enable":
        watch.enable()
        print("watcher enabled: icons regenerate when apps are installed or removed")
    elif a.action == "disable":
        watch.disable()
        print("watcher disabled")
    else:
        print(watch.status())


def cmd_uninstall(a):
    cfg = C.load()
    if not a.yes:
        print("This reverts the icon theme, disables the watcher and deletes the themes "
              f"{', '.join(theme.variant_names(cfg))} in {C.icons_dir()}.")
        print(f"Your settings and overrides in {C.config_dir()} are kept. Re-run with --yes to proceed.")
        return
    desktop.revert()
    watch.disable()
    theme.remove_all(cfg)
    print(f"monotile uninstalled (settings and overrides kept in {C.config_dir()})")


# ------------------------------------------------------------------ parser

def build_parser():
    p = argparse.ArgumentParser(prog="monotile",
                                description="Nothing-inspired monochrome icon theme for every installed app.")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    style = argparse.ArgumentParser(add_help=False)
    style.add_argument("--shape", choices=("circle", "squircle"),
                       help="which of the two themes `apply` activates (both are always generated)")
    style.add_argument("--tones", type=int, choices=(2, 3, 4),
                       help="2 = white stencil (default), 3 = grey bodies, 4 = white/light/mid grey")
    style.add_argument("--file-style", dest="file_style", choices=("black", "grey", "native"),
                       help="folders and file types: black = the source theme's black folders and "
                            "greyscale files (default), grey = everything greyscale, native = white line art")
    style.add_argument("--source", help="icon theme to read app icons from (default: monotile's own Monotile-Base)")
    style.add_argument("--fallback", help="icon theme to inherit everything else from (default: monotile's own Monotile-Base-Dark)")
    style.add_argument("--name", help="name of the generated theme (default: Monotile)")

    pv = sub.add_parser("preview", parents=[style], help="render a before/after contact sheet (changes nothing)")
    pv.add_argument("-o", "--output", default="monotile-preview.png")
    pv.add_argument("--columns", type=int, default=10)
    pv.add_argument("--limit", type=int, default=0)
    pv.add_argument("--context", default="apps", choices=theme.CONTEXT_NAMES,
                    help="which kind of icons to show (default: apps)")
    pv.set_defaults(func=cmd_preview)

    g = sub.add_parser("generate", parents=[style], help="create or update the icon theme")
    g.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    g.add_argument("--refresh", action="store_true", help="make the desktop reload icons if anything changed")
    g.add_argument("-q", "--quiet", action="store_true")
    g.add_argument("-v", "--verbose", action="store_true", help="list skipped apps")
    g.add_argument("--contexts", help="comma-separated kinds of icons to convert, e.g. apps,places,mimetypes")
    g.set_defaults(func=cmd_generate)

    ap = sub.add_parser("apply", parents=[style], help="generate if needed and switch the desktop to the theme")
    ap.set_defaults(func=cmd_apply)
    sub.add_parser("revert", help="switch back to the icon theme you had before").set_defaults(func=cmd_revert)
    sub.add_parser("status", help="show what is generated, active and watched").set_defaults(func=cmd_status)

    au = sub.add_parser("audit", help="check every icon name resolves inside the generated theme")
    au.add_argument("--shape", choices=("circle", "squircle"))
    au.add_argument("--limit", type=int, default=40)
    au.set_defaults(func=cmd_audit)

    w = sub.add_parser("watch", help="regenerate automatically when apps change (systemd --user)")
    w.add_argument("action", choices=("enable", "disable", "status"))
    w.set_defaults(func=cmd_watch)

    u = sub.add_parser("uninstall", help="revert, stop watching and delete the generated theme")
    u.add_argument("--yes", action="store_true")
    u.set_defaults(func=cmd_uninstall)
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        a.func(a)
    except (RuntimeError, ValueError) as e:
        print(f"monotile: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
