"""Settings, state and file locations (XDG base directories)."""
import json
import os
import re
import tempfile

THEME_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._+-]{0,63}$")

DEFAULTS = {
    "name": "Monotile",            # icon theme name (folder under ~/.local/share/icons)
    "source": None,                # theme to read app icons from; None = auto (Papirus if present)
    "fallback": None,              # theme to inherit everything else from; None = current theme at first run
    "shape": "circle",             # circle | squircle
    "tones": 2,                    # 2 | 3 | 4
    "file_style": "grey",          # folders and file types: grey (source icon without colour) | native (line art)
    "sizes": [16, 22, 24, 32, 48, 64, 96, 128, 256],
    # which kinds of icons to convert (apps and categories get the tile, the rest stay
    # their own shape): apps categories places mimetypes devices status emblems
    "contexts": ["apps", "categories", "places", "mimetypes", "devices", "status", "emblems", "actions"],
}
# the full list before "actions" existed: a config saved with it means "everything"
_OLD_ALL_CONTEXTS = {"apps", "categories", "places", "mimetypes", "devices", "status", "emblems"}


def _xdg(var, default):
    v = os.environ.get(var)
    return v if v and os.path.isabs(v) else os.path.expanduser(default)


def config_dir():
    return os.path.join(_xdg("XDG_CONFIG_HOME", "~/.config"), "monotile")


def cache_dir():
    return os.path.join(_xdg("XDG_CACHE_HOME", "~/.cache"), "monotile")


def icons_dir():
    return os.path.join(_xdg("XDG_DATA_HOME", "~/.local/share"), "icons")


def overrides_dir():
    return os.path.join(config_dir(), "overrides")


def theme_dir(cfg):
    return os.path.join(icons_dir(), cfg["name"])


def atomic_write(path, data, mode="w"):
    """Write via a temp file in the same directory, then rename over the target."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-")
    try:
        with os.fdopen(fd, mode) as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def validate(cfg):
    """Return a clean config dict, raising ValueError on bad values."""
    out = dict(DEFAULTS)
    out.update({k: v for k, v in cfg.items() if k in DEFAULTS})
    if not isinstance(out["name"], str) or not THEME_NAME_RE.match(out["name"]):
        raise ValueError("name: letters, digits, space . _ + - only (max 64)")
    for key in ("source", "fallback"):
        v = out[key]
        if v is not None and (not isinstance(v, str) or not THEME_NAME_RE.match(v)):
            raise ValueError(f"{key}: not a valid icon theme name")
    own = {out["name"], out["name"] + "-Circle", out["name"] + "-Squircle"}
    if out["fallback"] in own or out["source"] in own:
        raise ValueError("source/fallback cannot be one of the generated themes")
    if out["shape"] not in ("circle", "squircle"):
        raise ValueError("shape: circle or squircle")
    if out["tones"] not in (2, 3, 4):
        raise ValueError("tones: 2, 3 or 4")
    if out["file_style"] not in ("grey", "native"):
        raise ValueError("file_style: grey or native")
    sizes = out["sizes"]
    if not (isinstance(sizes, list) and sizes and all(isinstance(s, int) and 8 <= s <= 512 for s in sizes)):
        raise ValueError("sizes: list of integers between 8 and 512")
    out["sizes"] = sorted(set(sizes))
    known = DEFAULTS["contexts"]
    ctxs = out["contexts"]
    if isinstance(ctxs, list) and set(ctxs) == _OLD_ALL_CONTEXTS:
        ctxs = list(known)
    if not (isinstance(ctxs, list) and ctxs and all(c in known for c in ctxs)):
        raise ValueError("contexts: a non-empty list from " + ", ".join(known))
    out["contexts"] = [c for c in known if c in ctxs]
    return out


def load():
    return validate(_load_json(os.path.join(config_dir(), "config.json")))


def save(cfg):
    atomic_write(os.path.join(config_dir(), "config.json"), json.dumps(validate(cfg), indent=2) + "\n")


def load_state():
    return _load_json(os.path.join(config_dir(), "state.json"))


def save_state(state):
    atomic_write(os.path.join(config_dir(), "state.json"), json.dumps(state, indent=2) + "\n")
