import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import install
from installer_lib.config_sync import DEFAULT_CONFIG_TARGETS, ConfigTarget


ROOT = Path(__file__).resolve().parents[1]
INSTALL_PY = ROOT / "install.py"
HYPR_KEYBINDS = ROOT / "hyprland" / "configs" / "keybinds.conf"
HYPR_AUTOSTART = ROOT / "hyprland" / "configs" / "autostart.conf"
HYPR_CONFIGURE = ROOT / "hyprland" / "configure_hyprland.sh"
HYPR_INSTALLER = ROOT / "hyprland" / "install_hyprland.sh"
HYPRPAPER_CONFIG = ROOT / "hyprland" / "configs" / "hyprpaper.conf"


class DesktopConfigTests(unittest.TestCase):
    def test_desktop_menu_exposes_hyprland(self):
        source = INSTALL_PY.read_text(encoding="utf-8")

        self.assertIn('Category("hyprland", "Hyprland"', source)

    def test_config_sync_includes_hyprland(self):
        keys = {target.key for target in DEFAULT_CONFIG_TARGETS}

        self.assertIn("hyprland", keys)

    def test_hyprland_import_triggers_reload_after_sync(self):
        source = INSTALL_PY.read_text(encoding="utf-8")

        self.assertIn("def run_post_config_sync_hook", source)
        self.assertIn('direction == "import"', source)
        self.assertIn('target.key == "hyprland"', source)
        self.assertIn('["hyprctl", "reload"]', source)

    def test_hyprland_reload_failure_is_not_fatal_outside_session(self):
        target = ConfigTarget("hyprland", "Hyprland", "hyprland/configs", ".config/hypr")
        failed_reload = Mock(returncode=1, stdout="", stderr="Couldn't connect to Hyprland")

        with patch("install.command_exists", side_effect=lambda command: command == "hyprctl"):
            with patch("install.subprocess.run", return_value=failed_reload):
                messages = install.run_post_config_sync_hook("import", target)

        self.assertIn("[POST] Hyprland reload", messages)
        self.assertIn("[POST] Hyprland reload skipped: Couldn't connect to Hyprland", messages)

    def test_wallpaper_related_import_restarts_hyprpaper_after_sync(self):
        source = INSTALL_PY.read_text(encoding="utf-8")

        self.assertIn('target.key in {"hyprland", "wallpapers"}', source)
        self.assertIn('command_exists("hyprpaper")', source)
        self.assertIn('["pkill", "hyprpaper"]', source)
        self.assertIn('["hyprpaper"]', source)

    def test_hyprland_keybinds_use_configured_menu(self):
        keybinds = HYPR_KEYBINDS.read_text(encoding="utf-8")

        self.assertIn("$menu", keybinds)

    def test_hyprland_configure_copies_base_config(self):
        source = HYPR_CONFIGURE.read_text(encoding="utf-8")

        self.assertIn("Configuración base de Hyprland copiada", source)

    def test_hyprland_uses_hyprpaper_random_wallpapers(self):
        installer = HYPR_INSTALLER.read_text(encoding="utf-8")
        autostart = HYPR_AUTOSTART.read_text(encoding="utf-8")
        hyprpaper = HYPRPAPER_CONFIG.read_text(encoding="utf-8")

        self.assertIn("hyprpaper", installer)
        self.assertIn("hyprpaper", autostart)
        self.assertIn("swaync", autostart)
        self.assertIn("path = ~/.config/wallpapers", hyprpaper)
        self.assertIn("fit_mode = cover", hyprpaper)
        self.assertIn("timeout = 900", hyprpaper)
        self.assertIn("order = random", hyprpaper)
        self.assertIn("recursive = true", hyprpaper)


if __name__ == "__main__":
    unittest.main()
