import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "nvim" / "install.sh"


class NvimInstallerTests(unittest.TestCase):
    def test_installs_neovim_from_pacman_instead_of_github_tarball(self):
        script = INSTALLER.read_text(encoding="utf-8")

        self.assertIn("sudo pacman -S --needed --noconfirm", script)
        self.assertIn("    neovim \\", script)
        required_packages = [
            "neovim",
            "git",
            "gcc",
            "make",
            "unzip",
            "curl",
            "ripgrep",
            "fd",
            "fzf",
            "lazygit",
            "nodejs-lts-krypton",
            "npm",
            "pnpm",
            "yarn",
            "bun",
            "python",
            "python-pip",
            "python-pynvim",
            "jdk-openjdk",
            "maven",
            "gradle",
            "tree-sitter",
            "tree-sitter-cli",
            "wl-clipboard",
        ]
        for package in required_packages:
            with self.subTest(package=package):
                self.assertIn(package, script)

        self.assertNotIn("    nodejs npm python python-pip python-pynvim \\", script)
        self.assertNotIn("biome", script)
        self.assertNotIn("api.github.com/repos/neovim/neovim/releases", script)
        self.assertNotIn("nvim-linux-x86_64.tar.gz", script)
        self.assertNotIn("/opt/nvim-linux-x86_64", script)
        self.assertNotIn("sudo npm install -g neovim", script)


if __name__ == "__main__":
    unittest.main()
