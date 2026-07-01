import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALL_PY = ROOT / "install.py"
BASE_INSTALLER = ROOT / "system_base" / "install_base.sh"


class PackageCategoriesTests(unittest.TestCase):
    def test_base_installs_filesystem_and_zram_tools(self):
        install_py = INSTALL_PY.read_text(encoding="utf-8")
        base_script = BASE_INSTALLER.read_text(encoding="utf-8")

        for package in ["dosfstools", "exfatprogs", "zram-generator"]:
            with self.subTest(package=package):
                self.assertIn(package, install_py)
                self.assertIn(package, base_script)

    def test_fonts_include_symbol_and_cjk_fonts(self):
        source = INSTALL_PY.read_text(encoding="utf-8")

        for package in [
            "ttf-nerd-fonts-symbols",
            "ttf-nerd-fonts-symbols-mono",
            "adobe-source-han-sans-otc-fonts",
        ]:
            with self.subTest(package=package):
                self.assertIn(package, source)

    def test_printing_includes_pdf_font_helpers(self):
        source = INSTALL_PY.read_text(encoding="utf-8")

        for package in ["ghostscript", "gsfonts"]:
            with self.subTest(package=package):
                self.assertIn(package, source)


if __name__ == "__main__":
    unittest.main()
