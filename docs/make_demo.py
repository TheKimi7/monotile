#!/usr/bin/env python3
"""Rebuild the README demo images from a fixed list of common apps (built-in icons).

    python3 docs/make_demo.py
"""
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from monotile import base, config, theme  # noqa: E402
from monotile.iconfile import render  # noqa: E402
from monotile.lookup import IconResolver, Theme  # noqa: E402
from monotile.poster import convert, greyscale  # noqa: E402
from monotile.preview import contact_sheet  # noqa: E402

APPS = [
    "firefox", "google-chrome", "chromium", "thunderbird", "telegram", "discord", "spotify", "vlc",
    "gimp", "inkscape", "blender", "krita", "obs", "steam", "visual-studio-code", "libreoffice-writer",
    "libreoffice-calc", "org.gnome.Terminal", "org.gnome.Nautilus", "org.gnome.Calculator",
    "gnome-disks", "org.gnome.Settings", "gnome-system-monitor", "org.gnome.Weather",
    "org.gnome.Maps", "org.gnome.clocks", "org.gnome.Calendar", "rhythmbox", "transmission", "org.gnome.Software",
]

SYSTEM = [  # folders, file types and devices, drawn the way the generated theme draws them
    "folder", "folder-documents", "folder-download", "folder-music", "folder-pictures", "folder-videos",
    "user-home", "user-trash", "folder-git", "folder-github", "text-x-generic", "application-pdf",
    "image-x-generic", "audio-x-generic", "video-x-generic", "application-x-archive", "text-x-python",
    "application-json", "x-office-spreadsheet", "x-office-presentation", "drive-harddisk",
    "drive-removable-media", "computer", "computer-laptop", "camera-photo", "audio-headphones",
    "input-keyboard", "input-mouse", "phone", "printer"]

resolver = IconResolver(base.SOURCE)
cfg = config.validate({})
source = Theme(base.SOURCE)
contexts = {ctx: source.index(fd) for ctx, fd, _ in theme.CONTEXTS if ctx in ("places", "mimetypes", "devices")}


def system_icon(name):
    """(path, shape) exactly as `generate` picks them: black folders, grey file types, line-art devices."""
    for ctx, index in contexts.items():
        if name in index:
            path = index[name][1]
            if ctx == "places" and cfg["file_style"] == "black":
                path = theme.black_variant(index, name, path)
            return path, theme.shape_for(cfg, ctx)
    return None, None


def light(im):
    """The light-scheme version of a dark icon, as derive_light draws it."""
    r, g, b, a = im.split()
    return Image.merge("RGBA", [c.point(theme._LIGHT_LUT) for c in (r, g, b)] + [a])


def converted(path, size, shape):
    if shape == "grey":
        return greyscale(render(path, size))
    return convert(path, (size,), shape, cfg["tones"])[0][size]


items = [(name, resolver.resolve(name)) for name in APPS]
items = [(n, p) for n, p in items if p]
missing = sorted(set(APPS) - {n for n, _ in items})
if missing:
    print("not in the built-in icons, skipped:", ", ".join(missing))
for shape in ("circle", "squircle"):
    sheet, failed = contact_sheet(items, lambda p, s, shape=shape: converted(p, s, shape), columns=10)
    out = os.path.join(HERE, f"demo-{shape}.png")
    sheet.save(out)
    print(f"{out}: {len(items)} apps, {failed} failed")

sheet, failed = contact_sheet(items, lambda p, s: light(converted(p, s, "circle")), columns=10,
                              bg=(242, 242, 242), label_fg=(90, 90, 90))
out = os.path.join(HERE, "demo-light.png")
sheet.save(out)
print(f"{out}: {len(items)} apps, {failed} failed")

shapes = {}
sys_items = []
for n in SYSTEM:
    path, shape = system_icon(n)
    if path:
        sys_items.append((n, path))
        shapes[path] = shape
sheet, failed = contact_sheet(sys_items, lambda p, s: converted(p, s, shapes[p]), columns=10)
out = os.path.join(HERE, "demo-system.png")
sheet.save(out)
print(f"{out}: {len(sys_items)} icons, {failed} failed")
