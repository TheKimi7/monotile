"""Isolated fake desktop for tests: temp XDG dirs, a tiny icon theme, .desktop files."""
import os
import shutil
import tempfile
import unittest

from PIL import Image, ImageDraw

XDG_VARS = ("HOME", "XDG_DATA_HOME", "XDG_DATA_DIRS", "XDG_CONFIG_HOME", "XDG_CACHE_HOME")


def plate_icon_png(path, plate=(50, 120, 230), glyph=(255, 255, 255), size=128):
    """A coloured circle plate carrying a white square glyph."""
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((4, 4, size - 5, size - 5), fill=plate + (255,))
    q = size // 4
    d.rectangle((q + 8, q + 8, size - q - 8, size - q - 8), fill=glyph + (255,))
    im.save(path)
    return path


PLATE_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">
<circle cx="32" cy="32" r="30" fill="#2e7d32"/><path d="M20 20h24v24H20z" fill="#ffffff"/></svg>"""


class FakeDesktop(unittest.TestCase):
    """Base class: every test gets its own HOME and XDG directories."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="monotile-test-")
        self._saved = {k: os.environ.get(k) for k in XDG_VARS}
        self.home = os.path.join(self.root, "home")
        self.sys = os.path.join(self.root, "usr", "share")
        os.environ.update({
            "HOME": self.home,
            "XDG_DATA_HOME": os.path.join(self.home, ".local", "share"),
            "XDG_DATA_DIRS": self.sys,
            "XDG_CONFIG_HOME": os.path.join(self.home, ".config"),
            "XDG_CACHE_HOME": os.path.join(self.home, ".cache"),
        })
        for d in (os.environ["XDG_DATA_HOME"], self.sys):
            os.makedirs(os.path.join(d, "applications"), exist_ok=True)
        self.make_theme("Base", inherits=None, dirs={"48x48/apps": 48, "scalable/apps": "scalable"})

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.root, ignore_errors=True)

    # ------------------------------------------------------------ builders

    def make_theme(self, name, inherits=None, dirs=None, where=None):
        base = os.path.join(where or self.sys, "icons", name)
        os.makedirs(base, exist_ok=True)
        dirs = dirs or {"48x48/apps": 48}
        lines = ["[Icon Theme]", f"Name={name}", "Directories=" + ",".join(dirs)]
        if inherits:
            lines.append(f"Inherits={inherits}")
        for d, size in dirs.items():
            context = None
            if isinstance(size, tuple):
                size, context = size
            if size == "scalable":
                lines += [f"[{d}]", "Size=48", "Type=Scalable", "MinSize=8", "MaxSize=512"]
            else:
                lines += [f"[{d}]", f"Size={size}", "Type=Fixed"]
            if context:
                lines.append(f"Context={context}")
            os.makedirs(os.path.join(base, d), exist_ok=True)
        with open(os.path.join(base, "index.theme"), "w") as f:
            f.write("\n".join(lines) + "\n")
        return base

    def add_icon(self, theme, subdir, name, kind="png", where=None, mono=False):
        d = os.path.join(where or self.sys, "icons", theme, subdir)
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"{name}.{kind}")
        if kind == "png" and mono:
            plate_icon_png(path, plate=(230, 230, 230), glyph=(40, 40, 40))
        elif kind == "png":
            plate_icon_png(path)
        else:
            with open(path, "w") as f:
                f.write(PLATE_SVG)
        return path

    def add_app(self, desktop_id, icon, name=None, local=False, extra=""):
        d = os.path.join(os.environ["XDG_DATA_HOME"] if local else self.sys, "applications")
        path = os.path.join(d, desktop_id + ".desktop")
        with open(path, "w") as f:
            f.write(f"[Desktop Entry]\nType=Application\nName={name or desktop_id}\n"
                    f"Exec=true\nIcon={icon}\n{extra}")
        return path


class FakeSettings:
    """In-memory stand-in for gsettings."""

    def __init__(self, values=None):
        default = {
            ("org.cinnamon.desktop.interface", "icon-theme"): "Papirus-Dark",
            ("org.gnome.desktop.interface", "icon-theme"): "Adwaita",
        }
        self.values = dict(default if values is None else values)

    def available(self, schema):
        return any(s == schema for s, _ in self.values)

    def get(self, schema, key):
        return self.values.get((schema, key))

    def set(self, schema, key, value):
        self.values[(schema, key)] = value
