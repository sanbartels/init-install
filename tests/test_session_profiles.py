import unittest
from pathlib import Path

from installer_lib.config_sync import DEFAULT_CONFIG_TARGETS


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
