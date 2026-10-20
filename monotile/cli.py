"""monotile command line."""
import argparse
import os
import sys
import time

from . import __version__
from . import config as C
from . import desktop, theme, watch


def resolve_fallback(cfg):
    """The theme everything non-app is inherited from. Fixed at first run and saved,
    so the generated theme never ends up inheriting itself once it is active."""
    if cfg["fallback"]:
        return cfg["fallback"]
    cur = desktop.current_theme()
    fb = cur if cur and cur != cfg["name"] else None
    if not fb:
        prev = C.load_state().get("previous", {})
        fb = next((v for v in prev.values() if v and v != cfg["name"]), None)
    fb = fb or ("Papirus-Dark" if theme.Theme("Papirus-Dark").exists else "Adwaita")
    cfg["fallback"] = fb
    C.save(cfg)
    return fb


def load_cfg(a, persist=False):
    cfg = C.load()
    for k in ("name", "source", "fallback", "shape", "tones"):
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
    items = [(n, p) for n, (kind, p) in sorted(jobs.items()) if kind == "convert"]
    if a.limit:
        items = items[: a.limit]
    t = time.time()
    sheet, failed = contact_sheet(items, lambda p, s: convert(p, (s,), cfg["shape"], cfg["tones"])[0][s], a.columns)
    out = os.path.abspath(a.output)
    sheet.save(out)
    print(f"{len(items)} icons in {time.time() - t:.1f}s (failed {failed}) -> {out}")


def cmd_generate(a):
    cfg = load_cfg(a, persist=True)
    fallback = resolve_fallback(cfg)
    t = time.time()
    s = theme.generate(cfg, fallback, dry_run=a.dry_run)
    if not a.quiet or s["failed"]:
        verb = "would convert" if a.dry_run else "converted"
        print(f"{cfg['name']}: {verb} {s['converted']}, overrides {s['overrides']}, unchanged {s['unchanged']}, "
              f"removed {s['removed']}, failed {len(s['failed'])} in {time.time() - t:.1f}s")
        print(f"  source: {s['source']}   inherits: {fallback}   folder: {C.theme_dir(cfg)}")
        for name, why in s["failed"]:
            print(f"  failed: {name}: {why}")
        if a.verbose:
            for did, why in s["skipped"]:
                print(f"  skipped: {did} ({why})")
        elif s["skipped"]:
            print(f"  {len(s['skipped'])} apps skipped (use -v to list): icons given as file paths or not found")
    if a.refresh and s["changed"] and not a.dry_run and desktop.is_active(cfg["name"]):
        desktop.refresh(cfg["name"], fallback)


def cmd_apply(a):
    cfg = load_cfg(a, persist=True)
    fallback = resolve_fallback(cfg)
    if not os.path.exists(os.path.join(C.theme_dir(cfg), "index.theme")):
        s = theme.generate(cfg, fallback)
        print(f"generated {s['converted'] + s['overrides']} icons")
    keys = desktop.apply(cfg["name"])
    print(f"icon theme set to {cfg['name']} ({', '.join(s for s, _ in keys)})")
    print("Some panels cache icons: if one still shows the old icon, log out and back in.")


def cmd_revert(a):
    prev = desktop.revert()
    if prev:
        print("restored: " + ", ".join(f"{k.split()[0]} = {v}" for k, v in prev.items()))
    else:
        print("nothing to revert (monotile was not applied)")


def cmd_status(a):
    cfg = C.load()
    tdir = C.theme_dir(cfg)
    n = 0
    for _, _, files in os.walk(tdir):
        n += sum(1 for f in files if f.endswith(".png"))
    print(f"desktop:   {desktop.desktop_name()}")
    print(f"theme:     {cfg['name']} ({'generated' if os.path.isdir(tdir) else 'not generated'}, {n} files)")
    print(f"active:    {desktop.is_active(cfg['name'])} (current icon theme: {desktop.current_theme()})")
    print(f"style:     {cfg['tones']} tones on a {cfg['shape']}")
    print(f"source:    {cfg['source'] or theme.default_source(cfg['name'])}   "
          f"fallback: {cfg['fallback'] or '(set at first run)'}")
    print(f"overrides: {len(theme.find_overrides())} in {C.overrides_dir()}")
    print(f"watcher:   {watch.status()}")


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
        print(f"This reverts the icon theme, disables the watcher and deletes {C.theme_dir(cfg)}.")
        print(f"Your settings and overrides in {C.config_dir()} are kept. Re-run with --yes to proceed.")
        return
    desktop.revert()
    watch.disable()
    theme.remove(cfg)
    print(f"monotile uninstalled (settings and overrides kept in {C.config_dir()})")


# ------------------------------------------------------------------ parser

def build_parser():
    p = argparse.ArgumentParser(prog="monotile",
                                description="Nothing-inspired monochrome icon theme for every installed app.")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    style = argparse.ArgumentParser(add_help=False)
    style.add_argument("--shape", choices=("circle", "squircle"))
    style.add_argument("--tones", type=int, choices=(2, 3, 4),
                       help="2 = white stencil (default), 3 = grey bodies, 4 = white/light/mid grey")
    style.add_argument("--source", help="icon theme to read app icons from (default: Papirus if installed)")
    style.add_argument("--fallback", help="icon theme to inherit non-app icons from (default: your current theme)")
    style.add_argument("--name", help="name of the generated theme (default: Monotile)")

    pv = sub.add_parser("preview", parents=[style], help="render a before/after contact sheet (changes nothing)")
    pv.add_argument("-o", "--output", default="monotile-preview.png")
    pv.add_argument("--columns", type=int, default=10)
    pv.add_argument("--limit", type=int, default=0)
    pv.set_defaults(func=cmd_preview)

    g = sub.add_parser("generate", parents=[style], help="create or update the icon theme")
    g.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    g.add_argument("--refresh", action="store_true", help="make the desktop reload icons if anything changed")
    g.add_argument("-q", "--quiet", action="store_true")
    g.add_argument("-v", "--verbose", action="store_true", help="list skipped apps")
    g.set_defaults(func=cmd_generate)

    ap = sub.add_parser("apply", parents=[style], help="generate if needed and switch the desktop to the theme")
    ap.set_defaults(func=cmd_apply)
    sub.add_parser("revert", help="switch back to the icon theme you had before").set_defaults(func=cmd_revert)
    sub.add_parser("status", help="show what is generated, active and watched").set_defaults(func=cmd_status)

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
