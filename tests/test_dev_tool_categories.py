import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALL_PY = ROOT / "install.py"


class DevToolCategoriesTests(unittest.TestCase):
    def test_development_tools_are_split_by_runtime(self):
        source = INSTALL_PY.read_text(encoding="utf-8")

        expected_categories = {
            'Category("dev_tools", "Dev tools"': ["github-cli", "lazygit", "git", "curl", "jq"],
            'Category("node_tools", "Node.js LTS"': ["nodejs-lts-krypton", "npm", "pnpm", "yarn"],
            'Category("python_tools", "Python tools"': ["python", "python-pip", "uv", "python-pynvim", "pipx"],
            'Category("java_tools", "Java tools"': ["jdk-openjdk", "maven", "gradle"],
            'Category("go_rust_tools", "Go / Rust tools"': ["go", "rustup"],
        }

        for category_marker, packages in expected_categories.items():
            with self.subTest(category=category_marker):
                self.assertIn(category_marker, source)
                for package in packages:
                    self.assertIn(package, source)

        self.assertNotIn('install_pacman_packages("Dev tools", ["github-cli", "lazygit", "jdk-openjdk", "nodejs", "npm", "uv"]', source)


if __name__ == "__main__":
    unittest.main()
