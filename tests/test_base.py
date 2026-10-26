import os
import unittest

from monotile import base, config as C, theme
from monotile.lookup import IconResolver

from helpers import FakeDesktop


class Base(FakeDesktop):
    """monotile works without any icon theme installed: it carries its own."""

    def setUp(self):
        super().setUp()
        self.tdir = os.path.join(C.icons_dir(), "Monotile-Circle-Dark")
        os.makedirs(os.path.join(self.tdir, "48x48", "apps"))
        cfg = C.validate({"sizes": [48]})
        theme.write_index(dict(cfg, name="Monotile-Circle-Dark", embed="dark"), self.tdir, "hicolor", {"apps"})

    def dirs(self, tdir):
        return [d for d, _ in base.sections(os.path.join(tdir, "index.theme"))]

    def test_app_icons_resolve_from_the_bundled_copy(self):
        path = IconResolver(theme.default_source("Monotile")).resolve("firefox")
        self.assertTrue(path and path.startswith(base.BUNDLED), path)

    def test_embedded_after_own_icons_and_copied_once(self):
        self.assertTrue(base.embed(self.tdir, "dark"))
        self.assertFalse(base.embed(self.tdir, "dark"))
        dirs = self.dirs(self.tdir)
        self.assertEqual(dirs[0], "48x48/apps")
        dark = dirs.index("_base/dark/16x16/panel")
        self.assertLess(dark, dirs.index("_base/src/64x64/apps"))
        for d in dirs[1:]:
            self.assertTrue(os.path.isdir(os.path.join(self.tdir, d)), d)
        with open(os.path.join(self.tdir, "index.theme")) as f:
            self.assertIn("Inherits=hicolor\n", f.read())

    def test_one_copy_of_every_icon_name(self):
        """Toolkits break ties between same-size folders differently, so no name may appear twice."""
        open(os.path.join(self.tdir, "48x48", "apps", "firefox.png"), "w").close()
        base.embed(self.tdir, "dark")
        e = os.path.join(self.tdir, base.EMBED)
        self.assertFalse(os.path.exists(os.path.join(e, "src", "64x64", "apps", "firefox.svg")))
        self.assertTrue(os.path.exists(os.path.join(e, "dark", "16x16", "actions", "edit-copy.svg")))
        self.assertFalse(os.path.exists(os.path.join(e, "src", "16x16", "actions", "edit-copy.svg")))
        self.assertTrue(os.path.exists(os.path.join(e, "src", "16x16", "status", "dialog-error.svg"))
                        or os.path.exists(os.path.join(e, "src", "22x22", "status")))
        dangling = [os.path.join(d, f) for d, _, fs in os.walk(e) for f in fs
                    if os.path.islink(os.path.join(d, f)) and not os.path.exists(os.path.join(d, f))]
        self.assertEqual(dangling, [])

    def test_symbolic_links_follow_the_dark_set(self):
        base.embed(self.tdir, "dark")
        link = os.path.join(self.tdir, base.EMBED, "src", "16x16", "symbolic", "actions", "go-next-symbolic.svg")
        self.assertTrue(os.path.exists(link))
        self.assertEqual(os.path.realpath(link),
                         os.path.realpath(os.path.join(self.tdir, base.EMBED, "dark", "16x16", "actions", "go-next.svg")))

    def test_icon_comes_back_when_the_theme_stops_drawing_it(self):
        own = os.path.join(self.tdir, "48x48", "apps", "firefox.png")
        open(own, "w").close()
        base.embed(self.tdir, "dark")
        os.unlink(own)
        self.assertTrue(base.embed(self.tdir, "dark"))
        self.assertTrue(os.path.exists(os.path.join(self.tdir, base.EMBED, "src", "64x64", "apps", "firefox.svg")))

    def test_light_theme_gets_dark_glyphs_and_is_not_inverted(self):
        base.embed(self.tdir, "dark")
        light = os.path.join(C.icons_dir(), "Monotile-Circle-Light")
        theme.derive_light("Monotile-Circle-Dark", "Monotile-Circle-Light", "hicolor", embed="light")
        dirs = self.dirs(light)
        self.assertIn("_base/light/16x16/panel", dirs)
        self.assertFalse([d for d in dirs if d.startswith("_base/dark/")])
        src = "_base/src/64x64/places/folder.svg"
        with open(os.path.join(light, src), "rb") as a, open(os.path.join(base.BUNDLED, base.SOURCE, "64x64/places/folder.svg"), "rb") as b:
            self.assertEqual(a.read(), b.read())

    def test_index_only_rewritten_when_it_changes(self):
        cfg = dict(C.validate({"sizes": [48]}), name="Monotile-Circle-Dark", embed="dark")
        self.assertFalse(theme.write_index(cfg, self.tdir, "hicolor", {"apps"}))

    def test_separate_base_themes_from_earlier_versions_are_removed(self):
        old = os.path.join(C.icons_dir(), base.SOURCE)
        os.makedirs(old)
        open(os.path.join(old, base.LEGACY_STAMP), "w").close()
        base.remove_legacy()
        self.assertFalse(os.path.exists(old))

    def test_old_papirus_settings_move_to_the_bundled_icons(self):
        cfg = C.validate({"source": "Papirus", "fallback": "Papirus-Dark"})
        self.assertEqual((cfg["source"], cfg["fallback"]), (None, None))


if __name__ == "__main__":
    unittest.main()
