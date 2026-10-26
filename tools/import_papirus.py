#!/usr/bin/env python3
"""Rebuild base/ (monotile's own copy of the Papirus icons it needs) from a Papirus install.

    python3 tools/import_papirus.py /usr/share/icons [papirus-version]

base/Monotile-Base        the source monotile converts (64 px apps, devices, file types, folders)
                          plus the small icons every theme needs (toolbar, status, symbolic)
base/Monotile-Base-Dark   light glyphs for dark desktops: toolbar icons and panel/tray icons
base/Monotile-Base-Light  dark glyphs for light desktops: panel/tray icons and spinners

Folders keep only the default and black colours. Links whose target is left out become
copies, so the result never depends on the original install.
"""
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "base")
SMALL = ("16x16", "22x22", "24x24")

# theme name -> [(Papirus variant, size dir, context dir)]
SPEC = {
    "Monotile-Base": [("Papirus", "64x64", c) for c in ("apps", "devices", "mimetypes", "places")]
    + [("Papirus", s, c) for s in SMALL for c in ("actions", "status", "emblems", "emotes", "animations", "symbolic")],
    "Monotile-Base-Dark": [("Papirus-Dark", s, "actions") for s in SMALL]
    + [("Papirus", s, "panel") for s in SMALL],
    "Monotile-Base-Light": [("Papirus-Light", s, "panel") for s in SMALL]
    + [("Papirus-Light", s, "animations") for s in ("22x22", "24x24")],
}
INHERITS = {"Monotile-Base": "hicolor", "Monotile-Base-Dark": "Monotile-Base,hicolor",
            "Monotile-Base-Light": "Monotile-Base,hicolor"}

COLOUR = re.compile(
    r"^(folder|user)-(adwaita|blue|bluegrey|breeze|brown|carmine|cyan|darkcyan|deeporange|"
    r"green|grey|indigo|magenta|nordic|orange|palebrown|paleorange|pink|red|teal|violet|white|"
    r"yaru|yellow)(-|\.|$)")


def keep(context, name):
    return not (context == "places" and COLOUR.match(name))


def sections(index_path):
    """{directory: [lines]} from an index.theme."""
    out, cur = {}, None
    for line in open(index_path, encoding="utf-8"):
        line = line.rstrip("\n")
        m = re.match(r"^\[(.+)\]$", line)
        if m:
            cur = m.group(1)
            out[cur] = []
        elif cur and line.strip():
            out[cur].append(line)
    return out


def copy_context(src, dst, context):
    """Real files first, then links that still resolve inside the copy; the rest become files."""
    links = []
    for root, dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        for d in list(dirs):
            if os.path.islink(os.path.join(root, d)):
                links.append(os.path.join(rel, d))
                dirs.remove(d)
        for f in files:
            if not keep(context, f):
                continue
            p = os.path.join(root, f)
            if os.path.islink(p):
                links.append(os.path.join(rel, f))
            else:
                os.makedirs(os.path.join(dst, rel), exist_ok=True)
                shutil.copy2(p, os.path.join(dst, rel, f))
    pending = sorted(links)
    while pending:
        left = []
        for rel in pending:
            target = os.readlink(os.path.join(src, rel))
            d = os.path.join(dst, rel)
            os.makedirs(os.path.dirname(d), exist_ok=True)
            if os.path.exists(os.path.join(os.path.dirname(d), target)) and not os.path.isabs(target):
                os.symlink(target, d)
            else:
                left.append(rel)
        if len(left) == len(pending):          # nothing more resolves: copy what the links point to
            for rel in left:
                real, d = os.path.realpath(os.path.join(src, rel)), os.path.join(dst, rel)
                if os.path.isdir(real):
                    shutil.copytree(real, d)
                elif os.path.exists(real):
                    shutil.copy2(real, d)
            break
        pending = left


def build(icons, version):
    shutil.rmtree(OUT, ignore_errors=True)
    for name, parts in SPEC.items():
        tdir = os.path.join(OUT, name)
        dirs = {}
        for variant, size, context in parts:
            src = os.path.realpath(os.path.join(icons, variant, size, context))
            copy_context(src, os.path.join(tdir, size, context), context)
            idx = sections(os.path.join(icons, variant, "index.theme"))
            for d, lines in idx.items():
                if d == f"{size}/{context}" or d.startswith(f"{size}/{context}/"):
                    dirs[d] = lines
        if name == "Monotile-Base":                # Papirus files menu categories with the apps
            for size in ("64x64",):
                os.symlink("apps", os.path.join(tdir, size, "categories"))
                dirs[f"{size}/categories"] = [l.replace("Applications", "Categories") for l in dirs[f"{size}/apps"]]
        lines = ["[Icon Theme]", f"Name={name}", f"Comment=Icons from Papirus {version} used by monotile",
                 f"Inherits={INHERITS[name]}", "Hidden=true", "Directories=" + ",".join(sorted(dirs)), ""]
        for d in sorted(dirs):
            lines += [f"[{d}]"] + dirs[d] + [""]
        with open(os.path.join(tdir, "index.theme"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    for cand in (os.path.join(icons, "Papirus", "LICENSE"), "/usr/share/doc/papirus-icon-theme/copyright"):
        if os.path.exists(cand):                  # Papirus's licence and authors
            shutil.copy(cand, os.path.join(OUT, "PAPIRUS-COPYRIGHT"))
            break
    with open(os.path.join(OUT, "VERSION"), "w") as f:
        f.write(f"Papirus {version}\n")


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "unknown")
    print("written", OUT)
