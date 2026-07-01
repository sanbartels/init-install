import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "pi" / "install_pi.sh"
INSTALL_PY = ROOT / "install.py"


class PiInstallerTests(unittest.TestCase):
    def test_pi_installer_installs_pi_copies_global_config_and_installs_subagents(self):
        script = INSTALLER.read_text(encoding="utf-8")

        self.assertIn("curl -fsSL https://pi.dev/install.sh | sh", script)
        self.assertNotIn("npm install -g --ignore-scripts @earendil-works/pi-coding-agent", script)
        self.assertIn("https://github.com/j0k3r-dev-rgl/j0k3r-pi.git", script)
        self.assertIn("$HOME/.pi/agent", script)
        self.assertIn("git clone --depth 1 \"$REPO_URL\" \"$TARGET_DIR\"", script)
        self.assertIn("git -C \"$TARGET_DIR\" pull --ff-only", script)
        self.assertNotIn("rsync -a", script)
        self.assertIn("pi install npm:pi-subagents-j0k3r", script)

        clone_index = script.index("clone_global_config")
        extension_index = script.index("install_subagents_extension")
        self.assertLess(clone_index, extension_index)

    def test_pi_installer_is_available_from_software_menu(self):
        source = INSTALL_PY.read_text(encoding="utf-8")

        self.assertIn('Category("pi", "Pi Coding Agent"', source)
        self.assertIn('scripts("pi/install_pi.sh")', source)


if __name__ == "__main__":
    unittest.main()
