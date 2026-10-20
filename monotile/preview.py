"""Contact sheet: original icon above, converted icon below, app name under both."""
from PIL import Image, ImageDraw, ImageFont

from .iconfile import preview_pair

CELL_W, ICON, PAD = 132, 64, 14


def _font(size):
    for name in ("DejaVuSans.ttf", "NotoSans-Regular.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def contact_sheet(items, tone, columns=10, bg=(0, 0, 0)):
    """items: list of (label, icon_path). Returns (sheet image, failed count)."""
    rows = (len(items) + columns - 1) // columns
    cell_h = PAD + ICON + 8 + ICON + 6 + 26
    sheet = Image.new("RGB", (columns * CELL_W, max(1, rows) * cell_h), bg)
    d = ImageDraw.Draw(sheet)
    font = _font(11)
    failed = 0
    for i, (label, path) in enumerate(items):
        x = (i % columns) * CELL_W + (CELL_W - ICON) // 2
        y = (i // columns) * cell_h + PAD
        try:
            orig, conv = preview_pair(path, tone, ICON)
            sheet.paste(orig, (x, y), orig)
            sheet.paste(conv, (x, y + ICON + 8), conv)
        except Exception:
            failed += 1
        text = label if len(label) <= 18 else label[:17] + "…"
        tw = d.textlength(text, font=font)
        d.text(((i % columns) * CELL_W + (CELL_W - tw) / 2, y + 2 * ICON + 14), text,
               fill=(170, 170, 170), font=font)
    return sheet, failed
