import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALL_PY = ROOT / "install.py"
INSTALLER = ROOT / "homebrew" / "install_homebrew.sh"
OFFICIAL_INSTALL_COMMAND = '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'


class HomebrewInstallerTests(unittest.TestCase):
    def test_homebrew_installer_only_runs_official_install_command(self):
        script = INSTALLER.read_text(encoding="utf-8")

        self.assertIn(OFFICIAL_INSTALL_COMMAND, script)
        for forbidden in [
            "pacman",
            "base-devel",
            "procps-ng",
            "USER_BREW_PREFIX",
            "SYSTEM_BREW_PREFIX",
            "install_system_brew",
            "install_user_brew",
            "configure_shell",
            "shellenv",
            "tar xz",
            "mkdir -p",
            "/home/linuxbrew/.linuxbrew",
            "~/.linuxbrew",
        ]:
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, script)

    def test_homebrew_menu_description_does_not_claim_global_or_user_install(self):
        source = INSTALL_PY.read_text(encoding="utf-8")

        self.assertIn('Category("homebrew", "Homebrew", "Instala Homebrew", "Ejecuta el instalador oficial de Homebrew."', source)
        self.assertNotIn("Instala Homebrew global y de usuario", source)


if __name__ == "__main__":
    unittest.main()
