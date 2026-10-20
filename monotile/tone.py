"""Colour -> grey mapping for icons: a dark, high-contrast black & white look.

Every colour becomes its own shade. Plain luminance would merge colours of equal
brightness (red and green often land on the same grey), so the grey value is
CIE lightness plus a chroma term that leans warm colours lighter and cool colours
darker, much like a colour filter in black & white film photography. A tone curve
then sinks the mids and shadows towards black while keeping near-whites white,
so symbols drawn in white stay crisp.

SVG colours are rewritten in place (lossless); raster pixels go through a 3D LUT.
"""
import base64
import io
import math
import re

ALGO_VERSION = 1


class Tone:
    def __init__(self, darkness=1.0, contrast=1.0, separation=1.0, ceiling=0.86, floor=0.0):
        self.gamma = 1.0 + 0.45 * darkness        # >1 darkens mids
        self.contrast = contrast
        self.separation = separation
        self.ceiling = ceiling                    # brightest a coloured area may get
        self.floor = floor                        # darkest any opaque colour may get
        self._cache = {}

    # -------------------------------------------------------------- core map

    def grey(self, r, g, b):
        """sRGB 0-255 -> grey 0-255."""
        key = (r, g, b)
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        L, C, h = _lch(r, g, b)
        warm = math.cos(math.radians(h - 50))           # +1 orange/red ... -1 blue
        v = L + self.separation * C * (0.10 + 0.12 * warm)
        v = min(max(v / 100.0, 0.0), 1.0)
        if not (C < 12 and v >= 0.93):                   # near-neutral whites stay white
            v = v ** self.gamma
            v = 0.5 + (v - 0.5) * self.contrast          # simple contrast around mid
            # colours never reach white, so they can't merge with white symbols
            top = self.ceiling if C >= 12 else 0.93
            v = min(max(v, 0.0), 1.0)
            v = self.floor + (top - self.floor) * v      # squeeze into [floor, top]
        out = int(round(v * 255))
        self._cache[key] = out
        return out

    # -------------------------------------------------------------- raster

    def lut(self, size=33):
        from PIL import ImageFilter

        def f(r, g, b):
            v = self.grey(int(r * 255), int(g * 255), int(b * 255)) / 255.0
            return v, v, v
        return ImageFilter.Color3DLUT.generate(size, f)

    def image(self, im):
        """Convert a PIL image, alpha preserved."""
        im = im.convert("RGBA")
        rgb = im.convert("RGB").filter(self.lut())
        rgb.putalpha(im.getchannel("A"))
        return rgb

    # -------------------------------------------------------------- svg

    def svg(self, text):
        """Rewrite every colour literal in an SVG document."""
        text = _COLOUR.sub(self._sub, text)
        return _DATA_IMG.sub(self._sub_embedded, text)

    def _hex(self, r, g, b):
        v = self.grey(r, g, b)
        return "#%02x%02x%02x" % (v, v, v)

    def _sub(self, m):
        if m.group("keep"):
            return m.group(0)
        if m.group("hex"):
            x = m.group("hex")
            if len(x) in (3, 4):
                r, g, b = (int(c * 2, 16) for c in x[:3])
                a = x[3] * 2 if len(x) == 4 else ""
            else:
                r, g, b = (int(x[i:i + 2], 16) for i in (0, 2, 4))
                a = x[6:8]
            return self._hex(r, g, b) + a
        if m.group("fn"):
            parts = [p.strip() for p in m.group("args").split(",")]
            try:
                rgb = [round(float(p[:-1]) * 2.55) if p.endswith("%") else int(float(p)) for p in parts[:3]]
            except ValueError:
                return m.group(0)
            v = self.grey(*rgb)
            rest = (", " + ", ".join(parts[3:])) if len(parts) > 3 else ""
            return f"{m.group('fn')}({v}, {v}, {v}{rest})"
        rgb = NAMED.get(m.group("name").lower())
        return m.group("pre") + self._hex(*rgb) if rgb else m.group(0)

    def _sub_embedded(self, m):
        from PIL import Image
        try:
            im = Image.open(io.BytesIO(base64.b64decode(m.group(2))))
            buf = io.BytesIO()
            self.image(im).save(buf, "PNG")
            return m.group(1) + base64.b64encode(buf.getvalue()).decode()
        except Exception:
            return m.group(0)


# ------------------------------------------------------------------ colour maths

def _lin(c):
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _lch(r, g, b):
    R, G, B = _lin(r), _lin(g), _lin(b)
    X = (0.4124 * R + 0.3576 * G + 0.1805 * B) / 0.95047
    Y = 0.2126 * R + 0.7152 * G + 0.0722 * B
    Z = (0.0193 * R + 0.1192 * G + 0.9505 * B) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    fx, fy, fz = f(X), f(Y), f(Z)
    L = 116 * fy - 16
    a, bb = 500 * (fx - fy), 200 * (fy - fz)
    return L, math.hypot(a, bb), math.degrees(math.atan2(bb, a)) % 360


# ------------------------------------------------------------------ svg patterns

NAMED = {  # CSS colour keywords that actually show up in icon SVGs
    "black": (0, 0, 0), "white": (255, 255, 255), "red": (255, 0, 0), "green": (0, 128, 0),
    "blue": (0, 0, 255), "yellow": (255, 255, 0), "orange": (255, 165, 0), "purple": (128, 0, 128),
    "gray": (128, 128, 128), "grey": (128, 128, 128), "silver": (192, 192, 192), "lime": (0, 255, 0),
    "navy": (0, 0, 128), "teal": (0, 128, 128), "maroon": (128, 0, 0), "olive": (128, 128, 0),
    "aqua": (0, 255, 255), "cyan": (0, 255, 255), "fuchsia": (255, 0, 255), "magenta": (255, 0, 255),
    "pink": (255, 192, 203), "brown": (165, 42, 42), "gold": (255, 215, 0), "darkgray": (169, 169, 169),
    "darkgrey": (169, 169, 169), "lightgray": (211, 211, 211), "lightgrey": (211, 211, 211),
    "dimgray": (105, 105, 105), "whitesmoke": (245, 245, 245), "gainsboro": (220, 220, 220),
    "crimson": (220, 20, 60), "tomato": (255, 99, 71), "coral": (255, 127, 80),
    "skyblue": (135, 206, 235), "royalblue": (65, 105, 225), "steelblue": (70, 130, 180),
    "dodgerblue": (30, 144, 255), "limegreen": (50, 205, 50), "forestgreen": (34, 139, 34),
    "darkgreen": (0, 100, 0), "darkred": (139, 0, 0), "darkblue": (0, 0, 139), "indigo": (75, 0, 130),
    "violet": (238, 130, 238), "orchid": (218, 112, 214), "salmon": (250, 128, 114),
    "khaki": (240, 230, 140), "beige": (245, 245, 220), "ivory": (255, 255, 240), "tan": (210, 180, 140),
}

# url(#id) and href="#id" are references, not colours: matched first and kept as-is.
_COLOUR = re.compile(
    r"(?P<keep>url\(\s*#[^)]*\)|href=\"#[^\"]*\"|href='#[^']*')"
    r"|#(?P<hex>[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![0-9a-fA-F\w-])"
    r"|(?P<fn>rgba?)\(\s*(?P<args>[^)]*)\)"
    r"|(?P<pre>(?:fill|stroke|stop-color|flood-color|lighting-color|color)\s*[:=]\s*[\"']?)"
    r"(?P<name>" + "|".join(sorted(NAMED, key=len, reverse=True)) + r")(?=[\"';\s/>]|$)",
    re.I,
)
_DATA_IMG = re.compile(r"(data:image/(?:png|jpeg|jpg);base64,)([A-Za-z0-9+/=\s]+)")
