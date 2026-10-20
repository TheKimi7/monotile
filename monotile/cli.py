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


def make_tone(a):
    from .tone import Tone
    return Tone(darkness=a.darkness, contrast=a.contrast, separation=a.separation)


def make_converter(a):
    """path, size -> RGBA image, for the chosen style."""
    if a.style == "grey":
        from .iconfile import preview_pair
        tone = make_tone(a)
        return lambda path, size: preview_pair(path, tone, size)[1]
    from . import poster
    return lambda path, size: poster.convert(path, (size,), a.shape, a.tones)[0][size]


def cmd_preview(a):
    from .preview import contact_sheet
    items, skipped = collect(a.source, a.all)
    if a.limit:
        items = items[: a.limit]
    t = time.time()
    sheet, failed = contact_sheet([(lbl, p) for lbl, _, p in items], make_converter(a), a.columns)
    out = os.path.abspath(a.output)
    sheet.save(out)
    print(f"{len(items)} icons in {time.time() - t:.1f}s  (failed {failed})")
    for name, why in skipped:
        print(f"  skipped: {name} ({why})")
    print(f"preview: {out}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="monotile", description="Nothing-style monochrome icon themes for every installed app.")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--source", default=default_source(),
                        help="icon theme to read app icons from (default: Papirus if installed)")
    common.add_argument("--style", choices=("poster", "grey"), default="poster",
                        help="poster: four flat tones on a dark tile (default); grey: whole-icon greyscale")
    common.add_argument("--shape", choices=("circle", "squircle"), default="circle",
                        help="tile shape for the poster style")
    common.add_argument("--tones", type=int, choices=(2, 4), default=4,
                        help="poster style: 4 = white/light/mid grey on the tile, 2 = white only, parts split by cuts")
    common.add_argument("--darkness", type=float, default=1.0,
                        help="grey style: how far mid-tones are pushed towards black")
    common.add_argument("--contrast", type=float, default=1.15, help="grey style: contrast around mid-grey")
    common.add_argument("--separation", type=float, default=1.0,
                        help="grey style: how strongly different colours get different greys")

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
