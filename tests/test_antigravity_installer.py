import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "antigravity" / "install_antigravity.sh"
INSTALL_PY = ROOT / "install.py"


class AntigravityInstallerTests(unittest.TestCase):
    def test_antigravity_installer_uses_official_cli_install_script(self):
        script = INSTALLER.read_text(encoding="utf-8")

        self.assertIn("curl -fsSL https://antigravity.google/cli/install.sh | bash", script)
        self.assertIn("command -v agy", script)
        self.assertIn("agy --version", script)

    def test_antigravity_installer_is_available_from_software_menu(self):
        source = INSTALL_PY.read_text(encoding="utf-8")

        self.assertIn('Category("antigravity", "Antigravity CLI"', source)
        self.assertIn('scripts("antigravity/install_antigravity.sh")', source)
        self.assertIn('install_detector=lambda: command_exists("agy")', source)


if __name__ == "__main__":
    unittest.main()
