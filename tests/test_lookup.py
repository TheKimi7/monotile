import os
import unittest

from monotile.lookup import IconResolver, installed_apps

from helpers import FakeDesktop


class DesktopEntries(FakeDesktop):
    def test_local_entry_overrides_system(self):
        self.add_app("editor", "system-icon")
        self.add_app("editor", "local-icon", local=True)
        apps = {a.desktop_id: a for a in installed_apps()}
        self.assertEqual(apps["editor.desktop"].icon, "local-icon")

    def test_hidden_and_extension_stripping(self):
        self.add_app("helper", "helper.png", extra="NoDisplay=true\n")
        app = {a.desktop_id: a for a in installed_apps()}["helper.desktop"]
        self.assertTrue(app.hidden)
        self.assertEqual(app.icon_name, "helper")

    def test_unsafe_and_absolute_icon_names_are_not_themeable(self):
        self.add_app("evil", "../../etc/passwd")
        self.add_app("slash", "a/b")
        self.add_app("abs", "/opt/app/icon.png")
        apps = {a.desktop_id: a for a in installed_apps()}
        self.assertIsNone(apps["evil.desktop"].icon_name)
        self.assertIsNone(apps["slash.desktop"].icon_name)
        self.assertIsNone(apps["abs.desktop"].icon_name)
        self.assertTrue(apps["abs.desktop"].icon_is_path)

    def test_non_application_entries_ignored(self):
        path = self.add_app("link", "x")
        with open(path, "w") as f:
            f.write("[Desktop Entry]\nType=Link\nName=x\nIcon=x\nURL=https://example.org\n")
        self.assertNotIn("link.desktop", {a.desktop_id for a in installed_apps()})


class IconLookup(FakeDesktop):
    def test_inherited_theme_and_best_size(self):
        self.make_theme("Child", inherits="Base")
        small = self.add_icon("Base", "48x48/apps", "app")
        big = self.add_icon("Base", "scalable/apps", "app", kind="svg")
        self.assertEqual(IconResolver("Child").resolve("app"), big)
        self.assertNotEqual(small, big)

    def test_symlinked_size_directory(self):
        self.make_theme("Linked", inherits="Base", dirs={"48x48/apps": 48})
        target = os.path.join(self.sys, "icons", "Base", "48x48")
        link = os.path.join(self.sys, "icons", "Linked", "48x48")
        os.rename(link, link + ".old")
        os.symlink(os.path.relpath(target, os.path.dirname(link)), link)
        self.add_icon("Base", "48x48/apps", "shared")
        self.assertTrue(IconResolver("Linked").resolve("shared").endswith("shared.png"))

    def test_theme_split_across_base_dirs(self):
        # the user's ~/.local/share/icons/hicolor usually has no index.theme of its own
        self.make_theme("hicolor", dirs={"48x48/apps": 48})
        self.add_icon("hicolor", "48x48/apps", "webapp", where=os.environ["XDG_DATA_HOME"])
        self.assertIsNotNone(IconResolver("Base").resolve("webapp"))

    def test_pixmaps_fallback_and_missing(self):
        os.makedirs(os.path.join(self.sys, "pixmaps"))
        from helpers import plate_icon_png
        plate_icon_png(os.path.join(self.sys, "pixmaps", "legacy.png"))
        r = IconResolver("Base")
        self.assertTrue(r.resolve("legacy").endswith("legacy.png"))
        self.assertIsNone(r.resolve("nope"))

    def test_skip_excludes_a_theme(self):
        self.make_theme("Out", inherits="Base")
        self.add_icon("Out", "48x48/apps", "only-in-out")
        self.assertIsNone(IconResolver("Out", skip=("Out",)).resolve("only-in-out"))


if __name__ == "__main__":
    unittest.main()
