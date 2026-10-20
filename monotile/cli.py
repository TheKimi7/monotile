"""Command line interface."""
import argparse
import os
import sys
import time

from . import __version__
from .lookup import IconResolver, Theme, installed_apps


def default_source():
    for t in ("Papirus", "Papirus-Dark", "Adwaita"):
        if Theme(t).exists:
            return t
    return "hicolor"


def collect(source, include_hidden=False, exclude_theme=None):
    """[(label, icon_name, path)] for installed apps; plus a list of unresolved/skipped."""
    res = IconResolver(source, skip=(exclude_theme,) if exclude_theme else ())
    items, skipped, seen = [], [], set()
    for app in installed_apps():
        if app.hidden and not include_hidden:
            continue
        name = app.icon_name
        if name is None:
            skipped.append((app.name, "icon is a file path" if app.icon_is_path else "unsafe icon name"))
            continue
        if name in seen:
            continue
        path = res.resolve(name)
        if not path:
            skipped.append((app.name, "icon not found"))
            continue
        seen.add(name)
        items.append((app.name, name, path))
    return items, skipped


def cmd_preview(a):
    from .preview import contact_sheet
    items, skipped = collect(a.source, a.all)
    if a.limit:
        items = items[: a.limit]
    t = time.time()
    sheet, stats = contact_sheet([(lbl, p) for lbl, _, p in items], a.style, a.shape, a.columns)
    out = os.path.abspath(a.output)
    sheet.save(out)
    print(f"{len(items)} icons in {time.time() - t:.1f}s  "
          f"(plate {stats['plate']}, logo {stats['logo']}, failed {stats['failed']})")
    for name, why in skipped:
        print(f"  skipped: {name} ({why})")
    print(f"preview: {out}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="monotile", description="Monochrome tile icons for every installed app.")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--source", default=default_source(),
                        help="icon theme to read app icons from (default: Papirus if installed)")
    common.add_argument("--style", choices=("dark", "light"), default="dark")
    common.add_argument("--shape", choices=("circle", "squircle", "none"), default="circle")

    pv = sub.add_parser("preview", parents=[common], help="render a before/after contact sheet")
    pv.add_argument("-o", "--output", default="monotile-preview.png")
    pv.add_argument("--columns", type=int, default=10)
    pv.add_argument("--limit", type=int, default=0)
    pv.add_argument("--all", action="store_true", help="include hidden (NoDisplay) entries")
    pv.set_defaults(func=cmd_preview)

    a = p.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    sys.exit(main())
