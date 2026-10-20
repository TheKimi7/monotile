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

    def test_colour_variants_included_symbolic_skipped(self):
        theme.generate(self.cfg, "Full", workers=1)
        self.assertTrue(os.path.exists(self.out("places", "folder-red-documents")))   # no coloured fallback
        self.assertFalse(os.path.exists(self.out("status", "volume-symbolic")))

    def test_monochrome_status_icons_are_inherited(self):
        s = theme.generate(self.cfg, "Full", workers=1)
        self.assertEqual(s["kept"], 1)
        self.assertFalse(os.path.exists(self.out("status", "network-idle")))
        again = theme.generate(self.cfg, "Full", workers=1)
        self.assertEqual((again["converted"], again["kept"]), (0, 0))

    def test_native_icons_have_no_tile(self):
        from PIL import Image
        theme.generate(dict(self.cfg, file_style="native"), "Full", workers=1)
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

    def test_every_source_app_icon_is_converted(self):
        theme.generate(self.cfg, "Sys", workers=1)
        apps = os.path.join(self.tdir, "48x48", "apps")
        self.assertTrue(os.path.exists(os.path.join(apps, "system-shutdown.png")))
        self.assertTrue(os.path.exists(os.path.join(apps, "random-unused-app.png")))

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


class ThemePair(FakeDesktop):
    def setUp(self):
        super().setUp()
        self.make_theme("Src", dirs={"48x48/apps": (48, "Applications"), "48x48/places": (48, "Places")})
        self.add_icon("Src", "48x48/apps", "calc")
        self.add_icon("Src", "48x48/places", "folder")
        self.add_app("calc", "calc")
        self.cfg = C.validate({"source": "Src", "fallback": "Src", "sizes": [48]})

    def path(self, theme_name, ctx, name):
        return os.path.join(C.icons_dir(), theme_name, "48x48", ctx, name + ".png")

    def test_circle_is_full_and_squircle_only_tiles(self):
        out = theme.generate_all(self.cfg, "Src", workers=1)
        self.assertEqual(sorted(out), ["Monotile-Circle", "Monotile-Squircle"])
        self.assertTrue(os.path.exists(self.path("Monotile-Circle", "places", "folder")))
        self.assertTrue(os.path.exists(self.path("Monotile-Squircle", "apps", "calc")))
        self.assertFalse(os.path.exists(self.path("Monotile-Squircle", "places", "folder")))
        with open(os.path.join(C.icons_dir(), "Monotile-Squircle", "index.theme")) as f:
            self.assertIn("Inherits=Monotile-Circle,Src,hicolor", f.read())

    def test_shapes_differ(self):
        from PIL import Image
        theme.generate_all(self.cfg, "Src", workers=1)
        corner = lambda t: Image.open(self.path(t, "apps", "calc")).convert("RGBA").getpixel((5, 5))[3]
        self.assertLess(corner("Monotile-Circle"), corner("Monotile-Squircle"))   # squircle fills corners more

    def test_variant_names_rejected_as_fallback(self):
        with self.assertRaises(ValueError):
            C.validate({"fallback": "Monotile-Circle"})

    def test_remove_all(self):
        theme.generate_all(self.cfg, "Src", workers=1)
        theme.remove_all(self.cfg)
        self.assertFalse(os.path.exists(os.path.join(C.icons_dir(), "Monotile-Circle")))
        self.assertFalse(os.path.exists(os.path.join(C.icons_dir(), "Monotile-Squircle")))


class AliasRepair(FakeDesktop):
    def test_broken_alias_is_rebuilt(self):
        self.make_theme("Al", dirs={"48x48/mimetypes": (48, "MimeTypes")})
        img = self.add_icon("Al", "48x48/mimetypes", "a-type")
        os.symlink(os.path.basename(img), os.path.join(os.path.dirname(img), "b-type.png"))
        cfg = C.validate({"source": "Al", "fallback": "Al", "sizes": [48], "contexts": ["mimetypes"]})
        theme.generate(cfg, "Al", workers=1)
        d = os.path.join(C.icons_dir(), "Monotile", "48x48", "mimetypes")
        real = [f for f in os.listdir(d) if not os.path.islink(os.path.join(d, f))]
        link = [f for f in os.listdir(d) if os.path.islink(os.path.join(d, f))]
        self.assertEqual((len(real), len(link)), (1, 1))
        os.unlink(os.path.join(d, real[0]))                     # the alias now points nowhere
        theme.generate(cfg, "Al", workers=1)
        for f in ("a-type.png", "b-type.png"):
            self.assertTrue(os.path.exists(os.path.join(d, f)), f)


class NativeNamesStayNative(FakeDesktop):
    def test_app_using_a_folder_icon_gets_no_tile_copy(self):
        self.make_theme("Nv", dirs={"48x48/apps": (48, "Applications"), "48x48/places": (48, "Places")})
        self.add_icon("Nv", "48x48/apps", "folder")
        self.add_icon("Nv", "48x48/places", "folder")
        self.add_app("files", "folder")
        cfg = C.validate({"source": "Nv", "fallback": "Nv", "sizes": [48]})
        theme.generate_all(cfg, "Nv", workers=1)
        for t in ("Monotile-Circle", "Monotile-Squircle"):
            self.assertFalse(os.path.exists(os.path.join(C.icons_dir(), t, "48x48", "apps", "folder.png")))
        self.assertTrue(os.path.exists(os.path.join(C.icons_dir(), "Monotile-Circle", "48x48", "places", "folder.png")))


class DryRunWritesNothing(FakeDesktop):
    def test_generate_dry_run_does_not_save_settings(self):
        from monotile import cli
        self.make_theme("Dr", dirs={"48x48/apps": (48, "Applications")})
        self.add_icon("Dr", "48x48/apps", "calc")
        self.add_app("calc", "calc")
        cli.main(["generate", "--dry-run", "--source", "Dr", "--fallback", "Dr", "--shape", "squircle"])
        self.assertFalse(os.path.exists(os.path.join(C.config_dir(), "config.json")))


class GreyFiles(FakeDesktop):
    def test_folders_and_files_are_greyscale_copies(self):
        from PIL import Image
        self.make_theme("Gr", dirs={"48x48/places": (48, "Places"), "48x48/mimetypes": (48, "MimeTypes"),
                                    "48x48/devices": (48, "Devices")})
        self.add_icon("Gr", "48x48/places", "folder")
        self.add_icon("Gr", "48x48/mimetypes", "text-plain")
        self.add_icon("Gr", "48x48/devices", "drive-harddisk")
        cfg = C.validate({"source": "Gr", "fallback": "Gr", "sizes": [48], "file_style": "grey"})
        theme.generate(cfg, "Gr", workers=1)
        base = os.path.join(C.icons_dir(), "Monotile", "48x48")
        for ctx, name in (("places", "folder"), ("mimetypes", "text-plain")):
            im = Image.open(os.path.join(base, ctx, name + ".png")).convert("RGBA")
            px = [p for p in im.getdata() if p[3] > 0]
            self.assertTrue(px)
            self.assertTrue(all(r == g == b for r, g, b, _ in px), (ctx, name))      # no colour left
            plate = im.getpixel((24, 8))
            self.assertTrue(60 < plate[0] < 200, plate)                              # plate kept as grey
        dev = Image.open(os.path.join(base, "devices", "drive-harddisk.png")).convert("RGBA")
        self.assertGreater(min(dev.getpixel((24, 24))[:3]), 200)                     # devices stay line art


class BlackFolders(FakeDesktop):
    def test_black_variant_used_when_present(self):
        from PIL import Image
        from helpers import plate_icon_png
        self.make_theme("Bk", dirs={"48x48/places": (48, "Places")})
        self.add_icon("Bk", "48x48/places", "folder-music")                       # blue
        d = os.path.join(self.sys, "icons", "Bk", "48x48", "places")
        plate_icon_png(os.path.join(d, "folder-black-music.png"), plate=(40, 40, 40), glyph=(200, 200, 200))
        self.add_icon("Bk", "48x48/places", "folder-special")                     # no black variant
        cfg = C.validate({"source": "Bk", "fallback": "Bk", "sizes": [48]})
        theme.generate(cfg, "Bk", workers=1)
        base = os.path.join(C.icons_dir(), "Monotile", "48x48", "places")
        music = Image.open(os.path.join(base, "folder-music.png")).convert("RGB").getpixel((24, 6))
        special = Image.open(os.path.join(base, "folder-special.png")).convert("RGB").getpixel((24, 6))
        self.assertLess(music[0], 60)                    # the black variant
        self.assertGreater(special[0], 60)               # greyscale fallback
