"""monotile's own copy of the Papirus icons it needs (base/, see tools/import_papirus.py).

Installed as three hidden themes so nothing else has to be:
  Monotile-Base        what monotile converts, plus the small toolbar, status and symbolic icons
  Monotile-Base-Dark   light glyphs (toolbar, panel and tray icons) for dark desktops
  Monotile-Base-Light  dark glyphs (panel and tray icons, spinners) for light desktops
"""
import os
import shutil

from . import config as C

BUNDLED = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "base")
SOURCE, DARK, LIGHT = "Monotile-Base", "Monotile-Base-Dark", "Monotile-Base-Light"
NAMES = (SOURCE, DARK, LIGHT)
STAMP = ".monotile-base"


def version():
    with open(os.path.join(BUNDLED, "VERSION"), encoding="utf-8") as f:
        return f.read().strip()


def install(log=print):
    """Copy the base themes into the icons folder when missing or from another version."""
    from .theme import update_icon_cache
    want = version()
    for name in NAMES:
        dest = os.path.join(C.icons_dir(), name)
        stamp = os.path.join(dest, STAMP)
        if os.path.exists(stamp) and open(stamp, encoding="utf-8").read().strip() == want:
            continue
        if os.path.isdir(dest) and not os.path.exists(stamp):
            raise RuntimeError(f"{dest} exists and was not created by monotile")
        log(f"installing {name} ({want})")
        tmp = dest + ".new"
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.copytree(os.path.join(BUNDLED, name), tmp, symlinks=True)
        with open(os.path.join(tmp, STAMP), "w", encoding="utf-8") as f:
            f.write(want + "\n")
        shutil.rmtree(dest, ignore_errors=True)
        os.replace(tmp, dest)
        update_icon_cache(dest)


def remove():
    for name in NAMES:
        dest = os.path.join(C.icons_dir(), name)
        if os.path.exists(os.path.join(dest, STAMP)):
            shutil.rmtree(dest)
