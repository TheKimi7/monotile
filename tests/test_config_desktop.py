import unittest

from monotile import config as C
from monotile import desktop

from helpers import FakeDesktop, FakeSettings

CIN = ("org.cinnamon.desktop.interface", "icon-theme")
GNO = ("org.gnome.desktop.interface", "icon-theme")


class Config(FakeDesktop):
    def test_defaults(self):
        cfg = C.load()
        self.assertEqual((cfg["name"], cfg["shape"], cfg["tones"]), ("Monotile", "circle", 2))

    def test_validation(self):
        for bad in ({"shape": "hexagon"}, {"tones": 5}, {"name": "../x"}, {"name": "a/b"},
                    {"fallback": "Monotile"}, {"source": "Monotile"}, {"sizes": [4]}, {"sizes": []}):
            with self.assertRaises(ValueError, msg=bad):
                C.validate(bad)

    def test_round_trip(self):
        C.save({"shape": "squircle", "tones": 3})
        cfg = C.load()
        self.assertEqual((cfg["shape"], cfg["tones"]), ("squircle", 3))


class ApplyRevert(FakeDesktop):
    def test_apply_then_revert_restores_both_keys(self):
        b = FakeSettings()
        desktop.apply("Monotile", b)
        self.assertEqual((b.get(*CIN), b.get(*GNO)), ("Monotile", "Monotile"))
        desktop.revert(b)
        self.assertEqual((b.get(*CIN), b.get(*GNO)), ("Papirus-Dark", "Adwaita"))

    def test_second_apply_keeps_original_values(self):
        b = FakeSettings()
        desktop.apply("Monotile", b)
        desktop.apply("Monotile", b)                 # must not save "Monotile" as the previous theme
        desktop.revert(b)
        self.assertEqual(b.get(*CIN), "Papirus-Dark")

    def test_revert_without_apply_is_harmless(self):
        b = FakeSettings()
        self.assertEqual(desktop.revert(b), {})
        self.assertEqual(b.get(*CIN), "Papirus-Dark")

    def test_unsupported_desktop_raises(self):
        with self.assertRaises(RuntimeError):
            desktop.apply("Monotile", FakeSettings(values={}))

    def test_refresh_ends_on_the_theme(self):
        b = FakeSettings()
        desktop.refresh("Monotile", "Papirus-Dark", b)
        self.assertEqual(b.get(*CIN), "Monotile")


if __name__ == "__main__":
    unittest.main()
