import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "nvim" / "install.sh"


class NvimInstallerTests(unittest.TestCase):
    def test_installs_neovim_from_pacman_instead_of_github_tarball(self):
        script = INSTALLER.read_text(encoding="utf-8")

        self.assertIn("sudo pacman -S --needed --noconfirm", script)
        self.assertIn("    neovim \\", script)
        self.assertNotIn("api.github.com/repos/neovim/neovim/releases", script)
        self.assertNotIn("nvim-linux-x86_64.tar.gz", script)
        self.assertNotIn("/opt/nvim-linux-x86_64", script)
        self.assertNotIn("sudo npm install -g neovim", script)


if __name__ == "__main__":
    unittest.main()
