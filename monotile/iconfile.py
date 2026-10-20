"""Render icon files (SVG, SVGZ, PNG, XPM) to RGBA images."""
from PIL import Image


def render(path, size):
    """Render an icon file to a size x size RGBA image, aspect ratio preserved."""
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
        k = size / float(max(im.size))
        im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(im, ((size - im.width) // 2, (size - im.height) // 2))
    return canvas
