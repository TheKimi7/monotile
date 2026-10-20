"""Find installed applications and resolve their icon files.

Implements the parts of the freedesktop Desktop Entry and Icon Theme specs
that matter here: XDG data dirs, local overrides, theme inheritance and
directory sizes, plus Flatpak/Snap export locations and /usr/share/pixmaps.
"""
import configparser
import os
import re
from dataclasses import dataclass

ICON_EXTS = (".svg", ".png", ".xpm")
SAFE_NAME = re.compile(r"^[A-Za-z0-9._+@-]+$")


def data_dirs():
    home = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    dirs = [home]
    dirs += (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":")
    dirs += [os.path.expanduser("~/.local/share/flatpak/exports/share"),
             "/var/lib/flatpak/exports/share", "/var/lib/snapd/desktop"]
    seen, out = set(), []
    for d in dirs:
        d = os.path.realpath(d) if d else ""
        if d and d not in seen and os.path.isdir(d):
            seen.add(d)
            out.append(d)
    return out


def icon_base_dirs():
    out = [os.path.expanduser("~/.icons")]
    out += [os.path.join(d, "icons") for d in data_dirs()]
    return [d for d in out if os.path.isdir(d)]


# ---------------------------------------------------------------- apps

@dataclass
class App:
    desktop_id: str      # e.g. "firefox-esr.desktop"
    name: str
    icon: str            # Icon= value as written
    hidden: bool         # NoDisplay/Hidden

    @property
    def icon_is_path(self):
        return os.path.isabs(self.icon)

    @property
    def icon_name(self):
        """Themeable icon name, or None if the entry uses an unsafe value."""
        if self.icon_is_path:
            return None
        n = self.icon
        for ext in ICON_EXTS:
            if n.endswith(ext):
                n = n[: -len(ext)]
        return n if SAFE_NAME.match(n) and ".." not in n else None


def installed_apps():
    """Desktop entries in precedence order; the first file with an ID wins."""
    found = {}
    for d in data_dirs():
        appdir = os.path.join(d, "applications")
        if not os.path.isdir(appdir):
            continue
        for root, _, files in os.walk(appdir):
            for f in files:
                if not f.endswith(".desktop"):
                    continue
                rel = os.path.relpath(os.path.join(root, f), appdir)
                did = rel.replace(os.sep, "-")
                if did in found:
                    continue
                entry = _read_entry(os.path.join(root, f))
                if entry is not None:
                    found[did] = App(did, entry.get("Name", did), entry["Icon"],
                                     entry.get("NoDisplay") == "true" or entry.get("Hidden") == "true")
    return sorted(found.values(), key=lambda a: a.name.lower())


def _read_entry(path):
    cp = configparser.RawConfigParser(strict=False, interpolation=None)
    cp.optionxform = str
    try:
        cp.read(path, encoding="utf-8")
        sec = cp["Desktop Entry"]
    except Exception:
        return None
    if sec.get("Type", "Application") != "Application" or not sec.get("Icon"):
        return None
    return dict(sec)


# ---------------------------------------------------------------- icon themes

class Theme:
    def __init__(self, name):
        self.name = name
        # a theme's files may be spread over several base dirs; only one needs index.theme
        self.roots = [os.path.join(b, name) for b in icon_base_dirs()
                      if os.path.isdir(os.path.join(b, name))]
        indexes = [os.path.join(r, "index.theme") for r in self.roots
                   if os.path.isfile(os.path.join(r, "index.theme"))]
        self.inherits, self.dirs = [], []
        if not indexes:
            self.roots = []
        if self.roots:
            cp = configparser.RawConfigParser(strict=False, interpolation=None)
            cp.optionxform = str
            cp.read(indexes[0], encoding="utf-8")
            main = cp["Icon Theme"] if cp.has_section("Icon Theme") else {}
            self.inherits = [t.strip() for t in main.get("Inherits", "").split(",") if t.strip()]
            names = (main.get("Directories", "") + "," + main.get("ScaledDirectories", "")).split(",")
            for d in filter(None, (n.strip() for n in names)):
                if not cp.has_section(d):
                    continue
                s = cp[d]
                size = int(s.get("Size", "0") or 0) * int(s.get("Scale", "1") or 1)
                scalable = s.get("Type", "Threshold") == "Scalable"
                self.dirs.append((d, 10_000 if scalable else size))
        self._index = None

    @property
    def exists(self):
        return bool(self.roots)

    def index(self):
        """name -> (score, path), best (largest / scalable) file per name."""
        if self._index is None:
            idx = {}
            for root in self.roots:
                for d, score in self.dirs:
                    full = os.path.realpath(os.path.join(root, d))
                    try:
                        files = os.listdir(full)
                    except OSError:
                        continue
                    for f in files:
                        base, ext = os.path.splitext(f)
                        if ext in ICON_EXTS:
                            cur = idx.get(base)
                            if cur is None or score > cur[0]:
                                idx[base] = (score, os.path.join(full, f))
            self._index = idx
        return self._index


class IconResolver:
    """Resolve icon names through a theme chain, ending at hicolor and pixmaps."""

    def __init__(self, source_theme, skip=()):
        self.chain, seen = [], set(skip)
        self._walk(source_theme, seen)
        if "hicolor" not in seen:
            self._walk("hicolor", seen)

    def _walk(self, name, seen):
        if name in seen:
            return
        seen.add(name)
        t = Theme(name)
        if t.exists:
            self.chain.append(t)
            for parent in t.inherits:
                self._walk(parent, seen)

    def resolve(self, name):
        for t in self.chain:
            hit = t.index().get(name)
            if hit:
                return hit[1]
        for d in data_dirs():
            for ext in ICON_EXTS:
                p = os.path.join(d, "pixmaps", name + ext)
                if os.path.isfile(p):
                    return p
        return None
