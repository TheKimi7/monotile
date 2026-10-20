"""Turn a coloured app icon into a flat monochrome icon on a dark tile.

1. The icon is reduced to its flat colour regions (gradients and antialiasing merge).
2. A plain background plate (circle, squircle, rectangle) is detected and becomes the tile.
3. Every other region is drawn in flat tones:
   tones=2 (default)  white stencil: parts separated by thin dark cuts; a large grey
                      body carrying other symbols becomes an outline so they stay visible
   tones=3            as 2, but such bodies are filled mid-grey instead of outlined
   tones=4            white / light grey / mid grey ranked by contrast with the background
4. The result is centred on a circle or squircle tile and rendered at each size.

Pure Pillow; deterministic (same input and settings give byte-identical output).
"""
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageStat

from .iconfile import render

ALGO_VERSION = 5
WORK = 512
STAT = 128

TILE = (30, 30, 30)
TONES = [(242, 242, 242), (168, 168, 168), (100, 100, 100)]   # white, light, mid
BODY_GREY = (120, 120, 120)                                      # 3-tone mix body fill
SHAPES = ("circle", "squircle")


# ------------------------------------------------------------------ small helpers

def _bin(mask, t=128):
    return mask.point(lambda v: 255 if v >= t else 0)


def _erode(mask, px):
    """Square erosion of radius px. Repeated 3x3 min filters give exactly the same
    result as one (2px+1)-wide filter at a fraction of the cost for large px."""
    for _ in range(px):
        mask = mask.filter(ImageFilter.MinFilter(3))
    return mask


def _area(mask):
    return mask.histogram()[255]


def _lum(c):
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _dist(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]), abs(a[2] - b[2]))


def tile_mask(size, shape):
    m = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(m)
    pad = round(size * 0.03)
    if shape == "circle":
        d.ellipse((pad, pad, size - pad - 1, size - pad - 1), fill=255)
    else:
        d.rounded_rectangle((pad, pad, size - pad - 1, size - pad - 1), radius=round(size * 0.27), fill=255)
    return m


def _shape_fit(small_a):
    """Best IoU of the outline against an ellipse, rounded square or rectangle."""
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


def _holes(alpha_small):
    w, h = alpha_small.size
    pad = Image.new("L", (w + 2, h + 2), 0)
    pad.paste(alpha_small, (1, 1))
    ImageDraw.floodfill(pad, (0, 0), 128)
    return pad.crop((1, 1, w + 1, h + 1)).point(lambda v: 255 if v == 0 else 0)


# ------------------------------------------------------------------ analysis

def _plate(icon, alpha):
    """Return the plate colour if the icon sits on a plain plate, else None."""
    small_a = _bin(alpha.resize((STAT, STAT), Image.BILINEAR))
    box = alpha.getbbox()
    if (box[2] - box[0]) * (box[3] - box[1]) < 0.25 * WORK * WORK or _shape_fit(small_a) < 0.92:
        return None
    band = ImageChops.subtract(small_a, _erode(small_a, 3))
    if not _area(band):
        return None
    st = ImageStat.Stat(icon.convert("RGB").resize((STAT, STAT), Image.BILINEAR), band)
    if sum(st.stddev) / 3 > 40:
        return None
    return tuple(int(v) for v in st.median)


def _groups(keys):
    """Split sorted-descending contrast keys into at most 3 groups at the biggest gaps."""
    if len(keys) <= 3:
        return [[i] for i in range(len(keys))]
    gaps = sorted(range(1, len(keys)), key=lambda i: keys[i - 1] - keys[i], reverse=True)[:2]
    cuts = sorted(gaps)
    out, start = [], 0
    for c in cuts + [len(keys)]:
        out.append(list(range(start, c)))
        start = c
    return out


def poster(icon, colours=10, tones=2, native=False, weight=1.0):
    """Return (RGBA artwork at WORK size with plate removed, plate_bbox or None, mode)."""
    alpha = _bin(icon.getchannel("A"))
    if not alpha.getbbox():
        return None, None, "empty"
    plate = _plate(icon, alpha)

    base = Image.new("RGB", icon.size, plate or (0, 0, 0))
    base.paste(icon.convert("RGB"), (0, 0), alpha)
    q = base.quantize(colors=colours, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()[: colours * 3]
    counts = dict((idx, n) for n, idx in q.getcolors(colours * 4))
    entries = [(i, tuple(pal[i * 3:i * 3 + 3])) for i in counts]

    total = _area(alpha)
    holes = None
    if plate:
        background = [i for i, c in entries if _dist(c, plate) < 48]
        ref = _lum(plate)
        hs = _holes(_bin(alpha.resize((STAT, STAT), Image.BILINEAR)))
        holes = _bin(hs.resize(alpha.size, Image.BILINEAR))
    else:
        background = []
        ref = None

    fg = [(i, c) for i, c in entries if i not in background and counts[i] > 0.002 * total]
    if ref is None:                                   # free-standing logo: brightest = white
        keyed = sorted(fg, key=lambda e: _lum(e[1]), reverse=True)
        keys = [_lum(c) for _, c in keyed]
    else:                                             # plate: most contrast = white
        keyed = sorted(fg, key=lambda e: abs(_lum(e[1]) - ref) + 0.25 * _dist(e[1], plate), reverse=True)
        keys = [abs(_lum(c) - ref) + 0.25 * _dist(c, plate) for _, c in keyed]

    tone_of = {}
    for t, grp in enumerate(_groups(keys)):
        for k in grp:
            tone_of[keyed[k][0]] = TONES[min(t, 2)]
    # tiny clusters and anything unassigned follow their nearest assigned neighbour
    colour = dict(entries)
    for i, c in entries:
        if i in background or i in tone_of:
            continue
        near = min(tone_of, key=lambda j: _dist(colour[j], c)) if tone_of else None
        tone_of[i] = tone_of[near] if near is not None else TONES[0]

    lut = []
    for i in range(256):
        if i in background:
            lut += [0, 0, 0]
        else:
            lut += list(tone_of.get(i, TONES[0]))
    q.putpalette(lut)
    art = q.convert("RGB")
    mask = alpha
    if background:                      # drop pixels whose cluster is the plate
        keep = bytes(0 if i in background else 255 for i in range(256))
        idx = Image.frombytes("L", q.size, q.tobytes().translate(keep))
        mask = ImageChops.multiply(alpha, idx)
    if holes is not None:
        art.paste(TONES[0], (0, 0), holes)
        mask = ImageChops.lighter(mask, holes)
    if tones in (2, 3):
        art, mask = _two_tone(q, entries, background, mask, counts, total,
                              grey_bodies=(tones == 3), weight=weight)
    if native and plate:                 # no tile to stand in for the plate: keep its outline
        ring = ImageChops.subtract(alpha, _erode(alpha, max(2, round(WORK * 0.022 * weight))))
        mask = ImageChops.lighter(mask, ring)
        art.paste(TONES[0], (0, 0), ring)
    out = art.convert("RGBA")
    out.putalpha(mask)
    return out, (alpha.getbbox() if plate else None), ("plate" if plate else "logo")


def _two_tone(q, entries, background, mask, counts, total, grey_bodies=False, weight=1.0):
    """Everything white; where two genuinely different parts meet, cut a dark gap
    so they stay separate shapes (a stencil). Similar colours (gradient bands) are
    merged first so they do not produce false cuts.

    A large colourless body carrying other symbols (a grey drive under a wrench,
    a metal cabinet) would swallow those symbols as one white block, so it becomes
    negative space with a thin white outline instead, and the symbols on it stay solid.
    With grey_bodies (the 3-tone mix) such a body is filled mid-grey instead."""
    # Major colours (>= 3% of the icon) are the real parts; tiny ones are edge
    # antialiasing and gradient steps. Tiny colours attach to their nearest major
    # so they can never chain two different parts together; majors only merge
    # with each other when they are bands of the same gradient.
    fg = [(i, c) for i, c in entries if i not in background]
    majors = [(i, c) for i, c in fg if counts.get(i, 0) >= 0.03 * total] or fg
    parent = {i: i for i, _ in entries}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for a_i, a_c in majors:
        for b_i, b_c in majors:
            if a_i < b_i and _dist(a_c, b_c) < 36:
                parent[find(a_i)] = find(b_i)
    major_ids = {i for i, _ in majors}
    for i, c in fg:
        if i not in major_ids:
            parent[i] = find(min(majors, key=lambda m: _dist(m[1], c))[0])

    colour = dict(entries)
    groups = {}
    for i, _ in entries:
        if i not in background:
            groups.setdefault(find(i), []).append(i)
    fg_area = sum(counts.get(i, 0) for m in groups.values() for i in m)
    bodies = []
    for root, members in groups.items():
        area = sum(counts.get(i, 0) for i in members)
        avg = [sum(colour[i][k] * counts.get(i, 0) for i in members) / float(area or 1) for k in range(3)]
        neutral = max(avg) - min(avg) < 40
        if neutral and area > 0.40 * total and fg_area - area > 0.03 * total:
            bodies.append(root)

    group = bytes((find(i) * 23 + 7) % 256 if i in parent else 0 for i in range(256))
    regions = Image.frombytes("L", q.size, q.tobytes().translate(group))
    edges = regions.filter(ImageFilter.FIND_EDGES).point(lambda v: 255 if v else 0)
    gap = max(1, round(WORK * 0.008 * min(weight, 2.0)))
    edges = edges.filter(ImageFilter.MaxFilter(gap * 2 + 1))
    inside = _erode(mask, gap + 2)                      # never nibble the outer silhouette
    mask = ImageChops.subtract(mask, ImageChops.multiply(edges, inside))

    art = Image.new("RGB", q.size, TONES[0])
    for root in bodies:
        sel = bytes(255 if (i in parent and find(i) == root) else 0 for i in range(256))
        body = Image.frombytes("L", q.size, q.tobytes().translate(sel))
        if grey_bodies:                                 # body -> solid mid grey
            art.paste(BODY_GREY, (0, 0), body)
            continue
        small = _bin(body.resize((STAT, STAT), Image.BILINEAR))   # body -> outline only
        filled = _bin(ImageChops.lighter(small, _holes(small)).resize(q.size, Image.BILINEAR))
        ring = ImageChops.subtract(filled, _erode(filled, round(WORK * 0.022 * weight)))
        mask = ImageChops.lighter(ImageChops.subtract(mask, body), ring)
    return art, mask


# ------------------------------------------------------------------ compose

def compose(art, plate_box, size, shape="circle"):
    ss = 4 if size < 128 else 2
    S = size * ss
    tile = tile_mask(S, shape)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(Image.new("RGBA", (S, S), TILE + (255,)), (0, 0), tile)
    if art is not None and art.getbbox():
        if plate_box:                       # plate fills the tile; keep glyph proportions
            crop = art.crop(plate_box)
            target = S * (0.80 if shape == "circle" else 0.88)
        else:                               # free logo sits inside the tile
            crop = art.crop(art.getbbox())
            target = S * 0.60
        k = target / max(crop.size)
        crop = crop.resize((max(1, round(crop.width * k)), max(1, round(crop.height * k))), Image.LANCZOS)
        layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        layer.paste(crop, ((S - crop.width) // 2, (S - crop.height) // 2))
        layer.putalpha(ImageChops.multiply(layer.getchannel("A"), tile))
        out.alpha_composite(layer)
    return out.resize((size, size), Image.LANCZOS)


def compose_native(art, size):
    """No tile: the icon keeps its own shape and position, drawn in the flat tones."""
    if art is None:
        return Image.new("RGBA", (size, size), (0, 0, 0, 0))
    return art.resize((size, size), Image.LANCZOS)


SMALL = 32          # native icons at or below this size get heavier lines


def convert(path, sizes=(256,), shape="circle", tones=2):
    """Convert one icon file. Returns ({size: RGBA image}, mode).

    shape: circle / squircle put the icon on a dark tile (apps, menu categories);
    native keeps the icon's own silhouette (folders, file types, devices, status)."""
    if shape not in SHAPES + ("native",) or tones not in (2, 3, 4):
        raise ValueError("unsupported shape or tones")
    icon = render(path, WORK)
    if shape != "native":
        art, box, mode = poster(icon, tones=tones)
        return {s: compose(art, box, s, shape) for s in sizes}, mode
    out, mode = {}, "empty"
    for group, weight in (([s for s in sizes if s <= SMALL], 2.6), ([s for s in sizes if s > SMALL], 1.0)):
        if group:
            art, _, mode = poster(icon, tones=tones, native=True, weight=weight)
            out.update({s: compose_native(art, s) for s in group})
    return out, mode
