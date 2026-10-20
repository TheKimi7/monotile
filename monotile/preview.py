"""Contact sheet: original icon above, converted icon below, app name under both."""
from PIL import Image, ImageDraw, ImageFont

from .convert import convert, load_icon

CELL_W, ICON, PAD = 132, 64, 14


def _font(size):
    for name in ("DejaVuSans.ttf", "NotoSans-Regular.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def contact_sheet(items, style="dark", shape="circle", columns=10, bg=(0, 0, 0)):
    """items: list of (label, icon_path). Returns (sheet image, stats dict)."""
    rows = (len(items) + columns - 1) // columns
    cell_h = PAD + ICON + 8 + ICON + 6 + 28
    sheet = Image.new("RGB", (columns * CELL_W, max(1, rows) * cell_h), bg)
    d = ImageDraw.Draw(sheet)
    font = _font(11)
    stats = {"plate": 0, "logo": 0, "failed": 0}
    for i, (label, path) in enumerate(items):
        x = (i % columns) * CELL_W + (CELL_W - ICON) // 2
        y = (i // columns) * cell_h + PAD
        try:
            orig = load_icon(path, ICON)
            out, mode = convert(path, sizes=(ICON,), style=style, shape=shape)
            stats[mode if mode in stats else "failed"] += 1
        except Exception:
            orig, out, mode = None, {}, "failed"
            stats["failed"] += 1
        if orig is not None:
            sheet.paste(orig, (x, y), orig)
        if ICON in out:
            sheet.paste(out[ICON], (x, y + ICON + 8), out[ICON])
        text = label if len(label) <= 18 else label[:17] + "…"
        tw = d.textlength(text, font=font)
        d.text(((i % columns) * CELL_W + (CELL_W - tw) / 2, y + 2 * ICON + 14), text,
               fill=(170, 170, 170), font=font)
        d.text(((i % columns) * CELL_W + 4, y - 12), mode[0], fill=(70, 70, 70), font=font)
    return sheet, stats
