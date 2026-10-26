"""monotile's own copy of the Papirus icons it needs (base/, see tools/import_papirus.py).

base/Monotile-Base        what monotile converts, plus the small toolbar, status and symbolic icons
base/Monotile-Base-Dark   light glyphs (toolbar, panel and tray icons) for dark desktops
base/Monotile-Base-Light  dark glyphs (panel and tray icons, spinners) for light desktops

monotile reads Monotile-Base straight from base/. The generated themes carry the rest inside
themselves, in a _base folder listed after their own icons, so nothing else has to be
installed and the desktop's theme list shows only the Monotile themes.
"""
import os
import re
import shutil

from . import config as C

BUNDLED = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "base")
SOURCE, DARK, LIGHT = "Monotile-Base", "Monotile-Base-Dark", "Monotile-Base-Light"
NAMES = (SOURCE, DARK, LIGHT)
EMBED = "_base"
STAMP = "VERSION"
LEGACY_STAMP = ".monotile-base"          # base themes installed on their own by an earlier version


def version():
    with open(os.path.join(BUNDLED, "VERSION"), encoding="utf-8") as f:
        return f.read().strip()


def sections(index_path):
    """[(directory, [lines])] in the order the index lists them."""
    text = open(index_path, encoding="utf-8").read()
    order = re.search(r"(?m)^Directories=(.*)$", text).group(1).split(",")
    found, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^\[(.+)\]$", line)
        if m:
            cur = m.group(1)
            found[cur] = []
        elif cur and line.strip():
            found[cur].append(line)
    return [(d, found.get(d, [])) for d in order if d]


def _parts(variant):
    """(folder inside _base, bundled theme) for a dark or light theme, most specific first."""
    return [(variant, DARK if variant == "dark" else LIGHT), ("src", SOURCE)]


def _own_names(tdir):
    """Icon names the theme draws itself (everything outside _base)."""
    names = set()
    for top in os.listdir(tdir):
        if top == EMBED or not os.path.isdir(os.path.join(tdir, top)):
            continue
        for _, _, files in os.walk(os.path.join(tdir, top)):
            names.update(os.path.splitext(f)[0] for f in files)
    return names


def embed(tdir, variant):
    """Copy the base icons into a generated theme's _base folder and keep exactly one copy of
    every icon name: names the theme converts itself are left out, and the dark or light set
    replaces the source set's icon of the same size and kind. Toolkits break ties between
    folders of the same size differently (GTK 3 and 4 both prefer the bundled SVG), so the
    theme must never offer two. Returns True if anything changed."""
    want = version()
    edir = os.path.join(tdir, EMBED)
    stamp, pruned_file = os.path.join(edir, STAMP), os.path.join(edir, "PRUNED")
    own = _own_names(tdir)
    have = open(stamp, encoding="utf-8").read().strip() if os.path.exists(stamp) else None
    pruned = set(open(pruned_file, encoding="utf-8").read().split()) if os.path.exists(pruned_file) else set()
    fresh = (have != want or pruned - own                # a left-out icon is no longer drawn by the theme
             or not all(os.path.isdir(os.path.join(edir, p)) for p, _ in _parts(variant)))
    if fresh:
        shutil.rmtree(edir, ignore_errors=True)
        for part, name in _parts(variant):
            shutil.copytree(os.path.join(BUNDLED, name), os.path.join(edir, part), symlinks=True,
                            ignore=shutil.ignore_patterns("index.theme"))
        with open(stamp, "w", encoding="utf-8") as f:
            f.write(want + "\n")
        pruned = set()
    over = os.path.join(edir, variant)
    drop, removed = {}, set()                            # path -> replacement (dark/light copy) or None
    for part, _ in _parts(variant):
        root = os.path.join(edir, part)
        for d, _, files in os.walk(root):
            for f in files:
                p = os.path.join(d, f)
                if os.path.islink(p):
                    continue
                name = os.path.splitext(f)[0]
                twin = os.path.join(over, os.path.relpath(p, root)) if part == "src" else None
                if name in own:
                    drop[p] = None
                    removed.add(name)
                elif twin and os.path.lexists(twin):
                    drop[p] = twin
    # links (Papirus's symbolic icons point into actions/) follow their target's replacement,
    # or become a real copy when the theme draws the target itself under another name
    for d, _, files in os.walk(edir):
        for f in files:
            p = os.path.join(d, f)
            if not os.path.islink(p) or os.path.splitext(f)[0] in own:
                continue
            target = os.path.realpath(p)
            if target in drop:
                os.unlink(p)
                if drop[target]:
                    os.symlink(os.path.relpath(drop[target], d), p)
                else:
                    shutil.copy2(target, p)
    for p in drop:
        os.unlink(p)
    for d, _, files in os.walk(edir):                    # aliases of names the theme draws itself
        for f in files:
            p = os.path.join(d, f)
            if os.path.islink(p) and not os.path.exists(p):
                os.unlink(p)
    if removed - pruned or fresh:
        with open(pruned_file, "w", encoding="utf-8") as f:
            f.write("\n".join(sorted(pruned | removed)) + "\n")
    return fresh or bool(removed)


def index_entries(variant):
    """[(directory, [lines])] for a theme's _base folders, to list after its own."""
    return [(f"{EMBED}/{part}/{d}", lines)
            for part, name in _parts(variant)
            for d, lines in sections(os.path.join(BUNDLED, name, "index.theme"))]


def remove_legacy():
    """Delete the separate Monotile-Base themes an earlier version installed."""
    for name in NAMES:
        dest = os.path.join(C.icons_dir(), name)
        if os.path.exists(os.path.join(dest, LEGACY_STAMP)):
            shutil.rmtree(dest)
