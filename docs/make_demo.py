#!/usr/bin/env python3
"""Rebuild the README demo images from a fixed list of common apps (needs Papirus).

    python3 docs/make_demo.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from monotile.lookup import IconResolver  # noqa: E402
from monotile.poster import convert  # noqa: E402
from monotile.preview import contact_sheet  # noqa: E402

APPS = [
    "firefox", "google-chrome", "chromium", "thunderbird", "telegram", "discord", "spotify", "vlc",
    "gimp", "inkscape", "blender", "krita", "obs", "steam", "visual-studio-code", "libreoffice-writer",
    "libreoffice-calc", "org.gnome.Terminal", "org.gnome.Nautilus", "org.gnome.Calculator",
    "gnome-disks", "org.gnome.Settings", "gnome-system-monitor", "org.gnome.Weather",
    "org.gnome.Maps", "org.gnome.clocks", "org.gnome.Calendar", "rhythmbox", "transmission", "org.gnome.Software",
]

resolver = IconResolver("Papirus")
items = [(name, resolver.resolve(name)) for name in APPS]
items = [(n, p) for n, p in items if p]
missing = sorted(set(APPS) - {n for n, _ in items})
if missing:
    print("not in Papirus, skipped:", ", ".join(missing))
for shape in ("circle", "squircle"):
    sheet, failed = contact_sheet(items, lambda p, s, shape=shape: convert(p, (s,), shape, 2)[0][s], columns=10)
    out = os.path.join(HERE, f"demo-{shape}.png")
    sheet.save(out)
    print(f"{out}: {len(items)} apps, {failed} failed")
