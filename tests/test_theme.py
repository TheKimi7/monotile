import os
import unittest

from monotile import config as C
from monotile import theme

from helpers import FakeDesktop, plate_icon_png


class Generate(FakeDesktop):
    def setUp(self):
        super().setUp()
        self.add_icon("Base", "48x48/apps", "calc")
        self.add_icon("Base", "scalable/apps", "editor", kind="svg")
        self.add_app("calc", "calc")
        self.app = self.add_app("editor", "editor")
        self.add_app("broken", "does-not-exist")
        self.cfg = C.validate({"source": "Base", "fallback": "Base", "sizes": [24, 48]})
        self.tdir = C.theme_dir(self.cfg)

    def outputs(self, name):
        return [os.path.join(self.tdir, f"{s}x{s}", "apps", name + ".png") for s in self.cfg["sizes"]]

    def mtimes(self):
        return {p: os.stat(p).st_mtime_ns for n in ("calc", "editor") for p in self.outputs(n)}

    def test_first_run_writes_theme(self):
        s = theme.generate(self.cfg, "Base", log=lambda *a: None)
        self.assertEqual(s["converted"], 2)
        self.assertEqual([d for d, _ in s["skipped"]], ["broken.desktop"])
        for n in ("calc", "editor"):
            for p in self.outputs(n):
                self.assertTrue(os.path.isfile(p), p)
        with open(os.path.join(self.tdir, "index.theme")) as f:
            index = f.read()
        self.assertIn("Inherits=Base,hicolor", index)
        self.assertIn("[24x24/apps]", index)
        self.assertTrue(os.path.exists(os.path.join(self.tdir, theme.MARKER)))

    def test_second_run_is_a_noop(self):
        theme.generate(self.cfg, "Base")
        before = self.mtimes()
        s = theme.generate(self.cfg, "Base")
        self.assertEqual((s["converted"], s["unchanged"], s["changed"]), (0, 2, False))
        self.assertEqual(before, self.mtimes())

    def test_settings_change_regenerates(self):
        theme.generate(self.cfg, "Base")
        cfg2 = dict(self.cfg, shape="squircle")
        s = theme.generate(cfg2, "Base")
        self.assertEqual(s["converted"], 2)

    def test_changed_source_regenerates_only_that_icon(self):
        theme.generate(self.cfg, "Base")
        src = os.path.join(self.sys, "icons", "Base", "48x48", "apps", "calc.png")
        st = os.stat(src)
        os.utime(src, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
        s = theme.generate(self.cfg, "Base")
        self.assertEqual((s["converted"], s["unchanged"]), (1, 1))

    def test_removed_app_deletes_its_icons(self):
        theme.generate(self.cfg, "Base")
        os.unlink(self.app)
        s = theme.generate(self.cfg, "Base")
        self.assertEqual(s["removed"], 1)
        self.assertFalse(any(os.path.exists(p) for p in self.outputs("editor")))
        self.assertTrue(all(os.path.exists(p) for p in self.outputs("calc")))

    def test_override_wins(self):
        os.makedirs(C.overrides_dir())
        plate_icon_png(os.path.join(C.overrides_dir(), "calc.png"), plate=(200, 0, 0))
        s = theme.generate(self.cfg, "Base")
        self.assertEqual((s["overrides"], s["converted"]), (1, 1))
        from PIL import Image
        px = Image.open(self.outputs("calc")[1]).convert("RGB").getpixel((24, 6))
        self.assertGreater(px[0], 150)                     # the red override, not a converted tile

    def test_unsafe_override_names_ignored(self):
        os.makedirs(C.overrides_dir())
        plate_icon_png(os.path.join(C.overrides_dir(), "..evil.png"))
        self.assertNotIn("..evil", theme.find_overrides())

    def test_dry_run_writes_nothing(self):
        s = theme.generate(self.cfg, "Base", dry_run=True)
        self.assertEqual(s["converted"], 2)
        self.assertFalse(os.path.exists(self.tdir))

    def test_refuses_foreign_theme_folder(self):
        os.makedirs(self.tdir)
        open(os.path.join(self.tdir, "someone-elses-file"), "w").close()
        with self.assertRaises(RuntimeError):
            theme.generate(self.cfg, "Base")

    def test_remove_only_deletes_own_theme(self):
        theme.generate(self.cfg, "Base")
        theme.remove(self.cfg)
        self.assertFalse(os.path.exists(self.tdir))

    def test_light_fallback_prefers_light_panel_icons(self):
        self.make_theme("Pap")
        self.make_theme("Pap-Dark")
        self.assertEqual(theme.light_fallback("Pap-Dark"), "Pap")
        self.make_theme("Pap-Light")
        self.assertEqual(theme.light_fallback("Pap-Dark"), "Pap-Light,Pap")
        self.assertEqual(theme.light_fallback("Base"), "Base")

    def test_light_scheme_flips_tones_and_shares_folders(self):
        self.make_theme("Base", dirs={"48x48/apps": (48, "Applications"), "scalable/apps": ("scalable", "Applications"),
                                      "48x48/places": (48, "Places")})
        self.add_icon("Base", "48x48/places", "folder")
        theme.generate_all(self.cfg, "Base")
        dark = os.path.join(C.icons_dir(), "Monotile-Circle")
        light = os.path.join(C.icons_dir(), "Monotile-Light-Circle")
        from PIL import Image
        d = Image.open(os.path.join(dark, "48x48", "apps", "calc.png")).convert("RGBA")
        lt = Image.open(os.path.join(light, "48x48", "apps", "calc.png")).convert("RGBA")
        self.assertEqual(d.getchannel("A").tobytes(), lt.getchannel("A").tobytes())
        self.assertGreater(lt.getpixel((24, 4))[0], 200)          # light tile edge
        self.assertLess(d.getpixel((24, 4))[0], 60)
        places = os.path.join(light, "48x48", "places")
        self.assertTrue(os.path.islink(places))
        self.assertEqual(os.path.realpath(places), os.path.realpath(os.path.join(dark, "48x48", "places")))
        with open(os.path.join(light, "index.theme")) as f:
            self.assertIn("Inherits=Base,hicolor", f.read())
        with open(os.path.join(C.icons_dir(), "Monotile-Light-Squircle", "index.theme")) as f:
            self.assertIn("Inherits=Monotile-Light-Circle,Base,hicolor", f.read())
        before = os.stat(os.path.join(light, "48x48", "apps", "calc.png")).st_mtime_ns
        self.assertEqual(theme.derive_light("Monotile-Circle", "Monotile-Light-Circle", "Base")["redrawn"], 0)
        self.assertEqual(before, os.stat(os.path.join(light, "48x48", "apps", "calc.png")).st_mtime_ns)
        theme.remove_all(self.cfg)
        self.assertFalse(os.path.exists(light))


if __name__ == "__main__":
    unittest.main()
