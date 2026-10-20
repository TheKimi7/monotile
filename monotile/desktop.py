"""Activate / deactivate the theme on the running desktop.

Cinnamon reads org.cinnamon.desktop.interface; GTK4/libadwaita and Flatpak apps
read org.gnome.desktop.interface. Both are set, and both previous values are saved
once so `revert` restores exactly what the user had.
"""
import os
import shutil
import subprocess

from . import config as C

KEYS = [("org.cinnamon.desktop.interface", "icon-theme"),
        ("org.gnome.desktop.interface", "icon-theme")]


class GSettings:
    """Thin wrapper around the gsettings CLI (argument lists only, no shell)."""

    def __init__(self):
        self.exe = shutil.which("gsettings")

    def available(self, schema):
        if not self.exe:
            return False
        r = subprocess.run([self.exe, "list-keys", schema], capture_output=True, text=True)
        return r.returncode == 0

    def get(self, schema, key):
        r = subprocess.run([self.exe, "get", schema, key], capture_output=True, text=True)
        return r.stdout.strip().strip("'") if r.returncode == 0 else None

    def set(self, schema, key, value):
        subprocess.run([self.exe, "set", schema, key, value], check=True)


def desktop_name():
    return os.environ.get("XDG_CURRENT_DESKTOP", "") or "unknown"


def current_theme(backend=None):
    b = backend or GSettings()
    for schema, key in KEYS:
        if b.available(schema):
            return b.get(schema, key)
    return None


def apply(name, backend=None):
    """Switch the icon theme to `name`. Returns the list of keys changed."""
    b = backend or GSettings()
    keys = [(s, k) for s, k in KEYS if b.available(s)]
    if not keys:
        raise RuntimeError(f"no supported icon-theme setting found on {desktop_name()}; "
                           f"select the '{name}' icon theme in your desktop settings instead")
    state = C.load_state()
    if "previous" not in state:                      # save only once: a second apply keeps the original
        state["previous"] = {f"{s} {k}": b.get(s, k) for s, k in keys}
        C.save_state(state)
    for s, k in keys:
        b.set(s, k, name)
    return keys


def revert(backend=None):
    """Restore the icon themes saved by apply(). Returns the restored mapping."""
    b = backend or GSettings()
    state = C.load_state()
    prev = state.get("previous")
    if not prev:
        return {}
    for sk, value in prev.items():
        schema, key = sk.split(" ", 1)
        if value and b.available(schema):
            b.set(schema, key, value)
    del state["previous"]
    C.save_state(state)
    return prev


def is_active(name, backend=None):
    return current_theme(backend) == name


def refresh(name, fallback, backend=None):
    """Make the shell reload icons after regeneration: flip to the fallback theme and
    back. Cinnamon's panel otherwise keeps already-loaded icons until restarted."""
    b = backend or GSettings()
    keys = [(s, k) for s, k in KEYS if b.available(s)]
    for s, k in keys:
        b.set(s, k, fallback)
    for s, k in keys:
        b.set(s, k, name)
