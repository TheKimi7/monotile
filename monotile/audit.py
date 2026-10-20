"""Check that every icon name resolves inside the generated theme.

Looks up every non-symbolic name of the source theme, every installed app's icon
and every menu category icon through GTK, exactly as the desktop would, and reports
names that still come from another theme."""
import os

from . import config as C
from .lookup import Theme, installed_apps, menu_category_icons


def audit(theme_name, source, manifest_keys_kept, size=48):
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    gtk = Gtk.IconTheme.new()
    gtk.set_custom_theme(theme_name)
    src = Theme(source)
    names = set()
    for _, _, ctx in src.dirs:
        if ctx:
            names |= {n for n in src.index(ctx) if not n.endswith("-symbolic")}
    names |= {a.icon_name for a in installed_apps() if a.icon_name}
    names |= menu_category_icons()
    ours = os.path.join(C.icons_dir(), "") 
    result = {"ours": 0, "kept": [], "outside": [], "missing": []}
    for n in sorted(names):
        info = gtk.lookup_icon(n, size, 0)
        if not info or not info.get_filename():
            result["missing"].append(n)
            continue
        path = info.get_filename()
        theme_dir = path.split("/icons/", 1)[-1].split("/", 1)[0]
        if path.startswith(ours) and theme_dir.startswith(theme_name.split("-")[0]):
            result["ours"] += 1
        elif n in manifest_keys_kept:
            result["kept"].append(n)
        else:
            result["outside"].append((n, path))
    result["total"] = len(names)
    return result
