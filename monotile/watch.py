"""Keep the theme up to date with a systemd --user path unit (no root, no daemon).

When a .desktop file is added, changed or removed in an applications folder, or an
override is dropped in, systemd runs `monotile generate --refresh` once.
"""
import os
import shutil
import subprocess
import sys

from . import config as C
from .lookup import data_dirs

UNIT = "monotile"
UNIT_FILES = (f"{UNIT}.path", f"{UNIT}.service")


def unit_dir():
    return os.path.join(os.path.dirname(C.config_dir()), "systemd", "user")


def watched_paths():
    paths = [os.path.join(d, "applications") for d in data_dirs()]
    paths = [p for p in paths if os.path.isdir(p)]
    os.makedirs(C.overrides_dir(), exist_ok=True)
    return paths + [C.overrides_dir()]


def _systemctl(*args):
    exe = shutil.which("systemctl")
    if not exe:
        raise RuntimeError("systemctl not found; run `monotile generate` manually after installing apps")
    return subprocess.run([exe, "--user", *args], capture_output=True, text=True)


def available():
    try:
        return _systemctl("show-environment").returncode == 0
    except RuntimeError:
        return False


def units():
    pkg_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path_unit = "[Unit]\nDescription=Regenerate monotile icons when apps change\n\n[Path]\n"
    path_unit += "".join(f"PathChanged={p}\n" for p in watched_paths())
    path_unit += f"Unit={UNIT}.service\n\n[Install]\nWantedBy=default.target\n"
    service = ("[Unit]\nDescription=Regenerate monotile icons\n"
               "StartLimitIntervalSec=60\nStartLimitBurst=5\n\n"
               "[Service]\nType=oneshot\n"
               f"Environment=PYTHONPATH={pkg_parent}\n"
               f"ExecStart={sys.executable} -m monotile generate --quiet --refresh\n"
               "Nice=10\n")
    return {f"{UNIT}.path": path_unit, f"{UNIT}.service": service}


def enable():
    if not available():
        raise RuntimeError("systemd --user is not reachable from this session")
    for name, text in units().items():
        C.atomic_write(os.path.join(unit_dir(), name), text)
    _systemctl("daemon-reload")
    r = _systemctl("enable", "--now", f"{UNIT}.path")
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "systemctl enable failed")


def disable():
    if available():
        _systemctl("disable", "--now", f"{UNIT}.path")
    removed = False
    for name in UNIT_FILES:
        p = os.path.join(unit_dir(), name)
        if os.path.exists(p):
            os.unlink(p)
            removed = True
    if removed and available():
        _systemctl("daemon-reload")


def status():
    if not available():
        return "unavailable"
    r = _systemctl("is-active", f"{UNIT}.path")
    return r.stdout.strip() or "inactive"
