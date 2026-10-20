import os
import tempfile
import unittest

from PIL import Image

from monotile import poster

from helpers import PLATE_SVG, plate_icon_png


class Conversion(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="monotile-poster-")
        self.png = plate_icon_png(os.path.join(self.dir, "plate.png"))
        self.svg = os.path.join(self.dir, "plate.svg")
        with open(self.svg, "w") as f:
            f.write(PLATE_SVG)

    def test_plate_becomes_tile_and_glyph_white(self):
        out, mode = poster.convert(self.png, (64,))
        im = out[64]
        self.assertEqual(mode, "plate")
        self.assertEqual(im.size, (64, 64))
        cx = im.getpixel((32, 32))
        self.assertGreater(min(cx[:3]), 220)                        # white glyph in the middle
        ring = im.getpixel((32, 4))
        self.assertLess(max(ring[:3]), 60)                          # dark tile near the edge
        self.assertEqual(im.getpixel((0, 0))[3], 0)                 # transparent outside the circle

    def test_svg_input(self):
        out, mode = poster.convert(self.svg, (32, 48))
        self.assertEqual(sorted(out), [32, 48])
        self.assertEqual(mode, "plate")

    def test_deterministic(self):
        a, _ = poster.convert(self.png, (48, 128), "squircle", 2)
        b, _ = poster.convert(self.png, (48, 128), "squircle", 2)
        for s in (48, 128):
            self.assertEqual(a[s].tobytes(), b[s].tobytes())

    def test_all_tone_modes_and_shapes(self):
        for tones in (2, 3, 4):
            for shape in poster.SHAPES:
                out, _ = poster.convert(self.png, (24,), shape, tones)
                self.assertEqual(out[24].mode, "RGBA")

    def test_empty_icon_does_not_crash(self):
        path = os.path.join(self.dir, "empty.png")
        Image.new("RGBA", (64, 64), (0, 0, 0, 0)).save(path)
        out, mode = poster.convert(path, (32,))
        self.assertEqual(mode, "empty")
        self.assertEqual(out[32].size, (32, 32))

    def test_rejects_bad_options(self):
        with self.assertRaises(ValueError):
            poster.convert(self.png, (32,), "hexagon")
        with self.assertRaises(ValueError):
            poster.convert(self.png, (32,), "circle", 5)


if __name__ == "__main__":
    unittest.main()
