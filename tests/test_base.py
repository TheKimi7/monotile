import os
import unittest

from monotile import base, config as C, theme
from monotile.lookup import IconResolver

from helpers import FakeDesktop


class Base(FakeDesktop):
    """monotile works without any icon theme installed: it ships and installs its own."""

    def test_app_icons_resolve_from_the_bundled_copy(self):
        path = IconResolver(theme.default_source("Monotile")).resolve("firefox")
        self.assertTrue(path and path.startswith(base.BUNDLED), path)

    def test_install_once_and_remove(self):
        base.install(log=lambda *a: None)
        for name in base.NAMES:
            self.assertTrue(os.path.isfile(os.path.join(C.icons_dir(), name, "index.theme")))
        stamp = os.path.join(C.icons_dir(), base.SOURCE, base.STAMP)
        before = os.stat(stamp).st_mtime_ns
        base.install(log=lambda *a: self.fail("reinstalled"))
        self.assertEqual(os.stat(stamp).st_mtime_ns, before)
        base.remove()
        self.assertFalse(any(os.path.exists(os.path.join(C.icons_dir(), n)) for n in base.NAMES))

    def test_light_fallback_of_the_bundled_theme(self):
        self.assertEqual(theme.light_fallback(base.DARK), base.LIGHT)

    def test_old_papirus_settings_move_to_the_bundled_themes(self):
        cfg = C.validate({"source": "Papirus", "fallback": "Papirus-Dark"})
        self.assertEqual((cfg["source"], cfg["fallback"]), (None, None))


if __name__ == "__main__":
    unittest.main()
