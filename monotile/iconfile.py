"""Read, convert and render individual icon files."""
import gzip
import os

from PIL import Image


def read_svg(path):
    raw = open(path, "rb").read()
    if path.endswith(".svgz") or raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw.decode("utf-8", errors="surrogateescape")


def render(path=None, size=64, svg_text=None):
    """Render an icon (file path, or SVG text) to a size x size RGBA image."""
    if svg_text is not None or path.lower().endswith((".svg", ".svgz", ".xpm")):
        import gi
        gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import GdkPixbuf, GLib
        if svg_text is not None:
            loader = GdkPixbuf.PixbufLoader.new_with_type("svg")
            loader.set_size(size, size)
            loader.write(svg_text.encode("utf-8", errors="surrogateescape"))
            loader.close()
            pb = loader.get_pixbuf()
        else:
            pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, size, size, True)
        if not pb.get_has_alpha():
            pb = pb.add_alpha(False, 0, 0, 0)
        im = Image.frombytes("RGBA", (pb.get_width(), pb.get_height()),
                             pb.get_pixels(), "raw", "RGBA", pb.get_rowstride())
    else:
        im = Image.open(path).convert("RGBA")
        im = im.resize(_fit(im.size, size), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(im, ((size - im.width) // 2, (size - im.height) // 2))
    return canvas


def _fit(wh, size):
    k = size / float(max(wh))
    return max(1, round(wh[0] * k)), max(1, round(wh[1] * k))


def convert_file(src, dst_noext, tone, raster_size=256):
    """Write a converted copy of `src`. Returns the written path.

    SVG(Z) stays vector (colours rewritten); PNG/XPM become PNG."""
    low = src.lower()
    if low.endswith((".svg", ".svgz")):
        dst = dst_noext + ".svg"
        with open(dst, "w", encoding="utf-8", errors="surrogateescape") as f:
            f.write(tone.svg(read_svg(src)))
    else:
        dst = dst_noext + ".png"
        im = render(src, raster_size) if low.endswith(".xpm") else Image.open(src)
        tone.image(im).save(dst)
    return dst


def preview_pair(path, tone, size=64):
    """(original, converted) RGBA images for the preview sheet."""
    orig = render(path, size)
    if path.lower().endswith((".svg", ".svgz")):
        conv = render(size=size, svg_text=tone.svg(read_svg(path)))
    else:
        conv = tone.image(orig)
    return orig, conv


def exists(p):
    return p is not None and os.path.isfile(p)
