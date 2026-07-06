import unittest
from unittest.mock import patch

import install
from installer_lib.config_sync import ConfigTarget, ConfigTargetState, SyncPlan


class InstallerMenuBadgesTests(unittest.TestCase):
    def test_package_categories_are_installed_when_all_packages_exist(self):
        category = install.Category(
            "demo_tools",
            "Demo tools",
            "Demo",
            install.package_text("one", "two"),
        )

        with patch("install.pacman_package_installed", side_effect=lambda package: package in {"one", "two"}):
            self.assertTrue(install.category_is_installed(category))

        with patch("install.pacman_package_installed", side_effect=lambda package: package == "one"):
            self.assertFalse(install.category_is_installed(category))

    def test_installed_category_badges_are_disabled_and_marked_installed(self):
        installed = install.Category("installed", "Installed", "Demo", "", install_detector=lambda: True)
        pending = install.Category("pending", "Pending", "Demo", "", install_detector=lambda: False)

        disabled_keys, badges = install.installed_category_menu_state((installed, pending))

        self.assertEqual(disabled_keys, {"installed"})
        self.assertEqual(badges, {"installed": "(installed)"})

    def test_sync_badges_are_added_for_default_selected_config_states(self):
        target = ConfigTarget("kitty", "Kitty", "kitty/configs", ".config/kitty")
        needs_sync = ConfigTargetState(
            target=target,
            direction="import",
            plan=SyncPlan("kitty", source="repo", destination="home", status="different"),
            program_detected=True,
            source_exists=True,
            destination_exists=True,
            default_selected=True,
        )
        already_synced = ConfigTargetState(
            target=ConfigTarget("rofi", "Rofi", "rofi/configs", ".config/rofi"),
            direction="import",
            plan=SyncPlan("rofi", source="repo", destination="home", status="identical"),
            program_detected=True,
            source_exists=True,
            destination_exists=True,
            default_selected=False,
        )

        badges = install.sync_category_badges("import", [needs_sync, already_synced])

        self.assertEqual(badges, {"config_import_kitty": "(sync)"})


if __name__ == "__main__":
    unittest.main()
