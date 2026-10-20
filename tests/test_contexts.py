import os
import unittest

from monotile import config as C
from monotile import theme

from helpers import FakeDesktop


class AllIcons(FakeDesktop):
    def setUp(self):
        super().setUp()
        self.make_theme("Full", dirs={
            "48x48/apps": (48, "Applications"), "48x48/places": (48, "Places"),
            "48x48/mimetypes": (48, "MimeTypes"), "48x48/status": (48, "Status"),
            "symbolic/status": ("scalable", "Status")})
        self.add_icon("Full", "48x48/apps", "calc")
        self.add_app("calc", "calc")
        self.add_icon("Full", "48x48/places", "folder")
        self.add_icon("Full", "48x48/places", "folder-red-documents")          # colour variant
        doc = self.add_icon("Full", "48x48/mimetypes", "text-plain")
        os.symlink(os.path.basename(doc), os.path.join(os.path.dirname(doc), "text-x-log.png"))
        self.add_icon("Full", "48x48/status", "battery-low")                    # coloured
        self.add_icon("Full", "48x48/status", "network-idle", mono=True)        # already mono
        self.add_icon("Full", "symbolic/status", "volume-symbolic")
        ddir = os.path.join(self.sys, "desktop-directories")
        os.makedirs(ddir)
        with open(os.path.join(ddir, "Office.directory"), "w") as f:
            f.write("[Desktop Entry]\nType=Directory\nName=Office\nIcon=calc\n")
        self.cfg = C.validate({"source": "Full", "fallback": "Full", "sizes": [24, 48], "shape": "squircle"})
        self.tdir = C.theme_dir(self.cfg)

    def out(self, ctx, name, size=48):
        return os.path.join(self.tdir, f"{size}x{size}", ctx, name + ".png")

    def test_every_context_is_written(self):
        s = theme.generate(self.cfg, "Full", workers=1)
        self.assertEqual(s["failed"], [])
        for ctx, name in (("apps", "calc"), ("categories", "calc"), ("places", "folder"),
                          ("mimetypes", "text-plain"), ("status", "battery-low")):
            self.assertTrue(os.path.exists(self.out(ctx, name)), (ctx, name))
        with open(os.path.join(self.tdir, "index.theme")) as f:
            index = f.read()
        for ctx in ("Applications", "Categories", "Places", "MimeTypes", "Status"):
            self.assertIn(f"Context={ctx}", index)

    def test_aliases_are_symlinks(self):
        theme.generate(self.cfg, "Full", workers=1)
        self.assertTrue(os.path.islink(self.out("mimetypes", "text-x-log")) or
                        os.path.islink(self.out("mimetypes", "text-plain")))
        self.assertTrue(os.path.exists(self.out("mimetypes", "text-x-log")))

    def test_skips_colour_variants_and_symbolic(self):
        theme.generate(self.cfg, "Full", workers=1)
        self.assertFalse(os.path.exists(self.out("places", "folder-red-documents")))
        self.assertFalse(os.path.exists(self.out("status", "volume-symbolic")))

    def test_monochrome_status_icons_are_inherited(self):
        s = theme.generate(self.cfg, "Full", workers=1)
        self.assertEqual(s["kept"], 1)
        self.assertFalse(os.path.exists(self.out("status", "network-idle")))
        again = theme.generate(self.cfg, "Full", workers=1)
        self.assertEqual((again["converted"], again["kept"]), (0, 0))

    def test_native_icons_have_no_tile(self):
        from PIL import Image
        theme.generate(self.cfg, "Full", workers=1)
        corner = Image.open(self.out("places", "folder")).convert("RGBA").getpixel((24, 24))
        tile = Image.open(self.out("apps", "calc")).convert("RGBA").getpixel((24, 6))
        self.assertGreater(min(corner[:3]), 200)        # centre of the native icon is white glyph
        self.assertLess(max(tile[:3]), 60)              # app icons sit on the dark tile

    def test_contexts_setting_limits_output(self):
        cfg = dict(self.cfg, contexts=["apps"])
        theme.generate(cfg, "Full", workers=1)
        self.assertTrue(os.path.exists(self.out("apps", "calc")))
        self.assertFalse(os.path.exists(os.path.join(self.tdir, "48x48", "places")))


if __name__ == "__main__":
    unittest.main()


class ScalingAndSystemIcons(FakeDesktop):
    def setUp(self):
        super().setUp()
        self.make_theme("Sys", dirs={"48x48/apps": (48, "Applications"), "24x24/actions": (24, "Actions")})
        self.add_icon("Sys", "48x48/apps", "system-shutdown")
        self.add_icon("Sys", "48x48/apps", "random-unused-app")
        self.add_icon("Sys", "24x24/actions", "edit-delete")                 # coloured
        self.add_icon("Sys", "24x24/actions", "go-next", mono=True)          # already mono
        self.cfg = C.validate({"source": "Sys", "fallback": "Sys", "sizes": [16, 48, 256]})
        self.tdir = C.theme_dir(self.cfg)

    def test_system_icons_converted_without_an_app(self):
        theme.generate(self.cfg, "Sys", workers=1)
        apps = os.path.join(self.tdir, "48x48", "apps")
        self.assertTrue(os.path.exists(os.path.join(apps, "system-shutdown.png")))
        self.assertFalse(os.path.exists(os.path.join(apps, "random-unused-app.png")))

    def test_actions_keep_monochrome(self):
        s = theme.generate(self.cfg, "Sys", workers=1)
        acts = os.path.join(self.tdir, "48x48", "actions")
        self.assertTrue(os.path.exists(os.path.join(acts, "edit-delete.png")))
        self.assertFalse(os.path.exists(os.path.join(acts, "go-next.png")))
        self.assertEqual(s["kept"], 1)

    def test_index_sizes_are_scalable_ranges(self):
        theme.generate(self.cfg, "Sys", workers=1)
        import configparser
        cp = configparser.RawConfigParser()
        cp.read(os.path.join(self.tdir, "index.theme"))
        got = {d: (cp[d]["Type"], int(cp[d]["MinSize"]), int(cp[d]["MaxSize"]))
               for d in ("16x16/apps", "48x48/apps", "256x256/apps")}
        self.assertEqual(got, {"16x16/apps": ("Scalable", 8, 16), "48x48/apps": ("Scalable", 17, 48),
                               "256x256/apps": ("Scalable", 49, 512)})

    def test_old_saved_context_list_means_everything(self):
        cfg = C.validate({"contexts": ["apps", "categories", "places", "mimetypes", "devices", "status", "emblems"]})
        self.assertIn("actions", cfg["contexts"])
