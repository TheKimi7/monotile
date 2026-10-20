"""Turn a coloured app icon into a monochrome glyph on a tile.

Pure Pillow (+ GdkPixbuf for SVG/XPM rendering); no numpy.

Two cases:
  plate  - the icon is a coloured shape (circle, squircle...) carrying a symbol,
           which is how most Papirus app icons are drawn. The plate colour is
           sampled just inside the outline; everything far from it, plus any
           transparent holes, is the glyph.
  logo   - a free-standing logo (no plate). Its silhouette is the glyph, with
           strongly contrasting interior parts cut out so details survive.
"""
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageStat

ALGO_VERSION = 5
WORK = 512          # glyph extraction resolution
STAT = 128          # resolution for statistics / flood fills

STYLES = {
    "dark":  {"tile": (30, 30, 30, 255), "glyph": (242, 242, 242, 255)},
    "light": {"tile": (238, 238, 238, 255), "glyph": (17, 17, 17, 255)},
}


# ------------------------------------------------------------------ loading

def load_icon(path, size=WORK):
    """Render any icon file to a size x size RGBA image, aspect preserved."""
    if path.lower().endswith((".svg", ".svgz", ".xpm")):
        import gi
        gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import GdkPixbuf
        pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, size, size, True)
        if not pb.get_has_alpha():
            pb = pb.add_alpha(False, 0, 0, 0)
        im = Image.frombytes("RGBA", (pb.get_width(), pb.get_height()),
                             pb.get_pixels(), "raw", "RGBA", pb.get_rowstride())
    else:
        im = Image.open(path).convert("RGBA")
        im.thumbnail((size, size), Image.LANCZOS)
        if max(im.size) < size:                       # small PNGs: upscale
            s = size / max(im.size)
            im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(im, ((size - im.width) // 2, (size - im.height) // 2))
    return canvas


# ------------------------------------------------------------------ helpers

def _bin(mask, t=128):
    return mask.point(lambda v: 255 if v >= t else 0)


def _erode(mask, px):
    return mask.filter(ImageFilter.MinFilter(px * 2 + 1)) if px > 0 else mask


def _dilate(mask, px):
    return mask.filter(ImageFilter.MaxFilter(px * 2 + 1)) if px > 0 else mask


def _area(mask):
    return mask.histogram()[255]


def _holes(alpha_bin_small):
    """Transparent regions fully enclosed by the icon (not reachable from outside)."""
    w, h = alpha_bin_small.size
    pad = Image.new("L", (w + 2, h + 2), 0)
    pad.paste(alpha_bin_small, (1, 1))
    ImageDraw.floodfill(pad, (0, 0), 128)            # outside -> 128
    pad = pad.crop((1, 1, w + 1, h + 1))
    return pad.point(lambda v: 255 if v == 0 else 0)  # still 0 => enclosed hole


def _channel_distance(rgb, colour):
    """Per-pixel max channel distance from a solid colour (L image)."""
    d = ImageChops.difference(rgb, Image.new("RGB", rgb.size, colour))
    r, g, b = d.split()
    return ImageChops.lighter(ImageChops.lighter(r, g), b)


# ------------------------------------------------------------------ extraction

def extract_glyph(icon):
    """Return (mask L-image at WORK size, mode) where 255 = glyph."""
    alpha = _bin(icon.getchannel("A"))
    bbox = alpha.getbbox()
    if not bbox:
        return None, "empty"
    rgb = icon.convert("RGB")

    small_a = _bin(alpha.resize((STAT, STAT), Image.BILINEAR))
    band = ImageChops.subtract(small_a, _erode(small_a, 3))   # thin ring inside outline
    small_rgb = rgb.resize((STAT, STAT), Image.BILINEAR)
    band_px = _area(band)
    bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]

    if band_px > 0:
        st = ImageStat.Stat(small_rgb, band)
        plate = tuple(int(v) for v in st.median)
        spread = sum(st.stddev) / 3
    else:
        plate, spread = (0, 0, 0), 999

    if spread < 40 and bw * bh > 0.25 * WORK * WORK and _plate_shape_fit(small_a) >= 0.92:
        mask = _plate_glyph(rgb, alpha, [plate])
        if mask is not None:
            return _clean(mask), "plate"
    return _clean(_logo_glyph(rgb, alpha)), "logo"


def _plate_shape_fit(small_a):
    """Best IoU of the outline against a circle/ellipse, rounded square or rectangle."""
    box = small_a.getbbox()
    best = 0.0
    for kind in ("ellipse", "round", "rect"):
        ref = Image.new("L", small_a.size, 0)
        d = ImageDraw.Draw(ref)
        x0, y0, x1, y1 = box[0], box[1], box[2] - 1, box[3] - 1
        if kind == "ellipse":
            d.ellipse((x0, y0, x1, y1), fill=255)
        elif kind == "round":
            d.rounded_rectangle((x0, y0, x1, y1), radius=round(min(x1 - x0, y1 - y0) * 0.22), fill=255)
        else:
            d.rectangle((x0, y0, x1, y1), fill=255)
        inter = _area(ImageChops.multiply(ref, small_a))
        union = _area(ImageChops.lighter(ref, small_a))
        best = max(best, inter / float(union or 1))
    return best


def _far_from(rgb, colour, within, t=64):
    return ImageChops.multiply(within, _channel_distance(rgb, colour).point(lambda v: 255 if v > t else 0))


def _plate_glyph(rgb, alpha, plates):
    """Glyph = everything far from the plate colour, plus see-through holes.

    If that region covers most of the plate it is an inner panel (a white face on
    an orange ring, a page on a squircle): the panel becomes the glyph and the
    details drawn on it are cut out of it."""
    plate = plates[0]
    inner = _erode(alpha, 6)                                  # skip the plate's AA rim
    holes = _holes(_bin(alpha.resize((STAT, STAT), Image.BILINEAR)))
    holes = _bin(holes.resize(alpha.size, Image.BILINEAR))
    total = _area(alpha)
    far = _far_from(rgb, plate, inner)
    a = _area(far)
    if a < 0.01 * total:
        return None
    if a < 0.5 * total:
        glyph = ImageChops.lighter(far, holes)
        # a real glyph sits inside its plate; one hugging the outline means the
        # "plate" is really the logo's own frame
        sa = _bin(alpha.resize((STAT, STAT), Image.BILINEAR))
        sg = _bin(glyph.resize((STAT, STAT), Image.BILINEAR))
        rim = ImageChops.subtract(sa, _erode(sa, 6))
        if _area(ImageChops.multiply(sg, rim)) > 0.4 * max(1, _area(sg)):
            return None
        return glyph
    panel = _dilate(_erode(far, 3), 3)                        # inner panel, specks removed
    colour = tuple(int(v) for v in ImageStat.Stat(rgb, panel).median)
    details = _far_from(rgb, colour, _erode(panel, 3))
    if _area(details) > 0.85 * _area(panel):
        return details
    return ImageChops.subtract(panel, _dilate(details, 3))


def _logo_glyph(rgb, alpha):
    """Silhouette with contrasting interior parts cut out; if the parts that
    contrast are the majority, they are the logo's real shape and become the glyph."""
    lum = rgb.convert("L")
    med = ImageStat.Stat(lum, alpha).median[0]
    contrast = lum.point(lambda v: 255 if abs(v - med) > 64 else 0)
    cut = ImageChops.multiply(contrast, _erode(alpha, 4))
    total, c = _area(alpha), _area(cut)
    if c > 0.85 * total:
        return cut
    return ImageChops.subtract(alpha, _dilate(cut, 3))


def _clean(mask):
    mask = _dilate(_erode(mask, 2), 2)                        # drop specks
    mask = _erode(_dilate(mask, 2), 2)                        # close pin-holes
    return _bin(mask.filter(ImageFilter.GaussianBlur(1.6)))


# ------------------------------------------------------------------ compose

def compose(mask, size, style="dark", shape="circle", glyph_scale=0.58):
    """Build the final icon at `size` px from a WORK-size glyph mask."""
    colours = STYLES[style]
    ss = 4 if size < 128 else 2                     # supersample for clean edges
    S = size * ss
    box = mask.getbbox()
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    tile = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(tile)
    m = round(S * 0.03)
    if shape == "circle":
        d.ellipse((m, m, S - m, S - m), fill=255)
    elif shape == "squircle":
        d.rounded_rectangle((m, m, S - m, S - m), radius=round(S * 0.28), fill=255)
    if shape != "none":
        out.paste(Image.new("RGBA", (S, S), colours["tile"]), (0, 0), tile)

    if box:
        g = mask.crop(box)
        target = S * (glyph_scale if shape != "none" else 0.9)
        k = target / max(g.width, g.height)
        g = g.resize((max(1, round(g.width * k)), max(1, round(g.height * k))), Image.LANCZOS)
        if size <= 24:                                  # thicken so it survives tiny sizes
            g = _dilate(g, max(1, round(ss * (1.0 if size <= 16 else 0.6))))
        layer = Image.new("L", (S, S), 0)
        layer.paste(g, ((S - g.width) // 2, (S - g.height) // 2))
        out.paste(Image.new("RGBA", (S, S), colours["glyph"]), (0, 0), layer)

    return out.resize((size, size), Image.LANCZOS)


def convert(path, sizes=(256,), style="dark", shape="circle"):
    """Convert one icon file. Returns ({size: RGBA image}, mode)."""
    mask, mode = extract_glyph(load_icon(path))
    if mask is None:
        return {}, mode
    return {s: compose(mask, s, style, shape) for s in sizes}, mode
