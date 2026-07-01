import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFORM = ROOT / "nvim" / "configs" / "lua" / "plugins" / "conform.lua"
LSP = ROOT / "nvim" / "configs" / "lua" / "plugins" / "lsp.lua"


class NvimConfigDependenciesTests(unittest.TestCase):
    def test_biome_formatter_uses_mason_managed_binary(self):
        source = CONFORM.read_text(encoding="utf-8")

        self.assertIn('command = vim.fn.stdpath("data") .. "/mason/bin/biome"', source)
        self.assertNotIn('command = "biome"', source)

    def test_jdtls_is_installed_by_mason_but_not_auto_enabled(self):
        source = LSP.read_text(encoding="utf-8")

        self.assertIn('"jdtls",', source)
        self.assertIn('exclude = { "jdtls" }', source)


if __name__ == "__main__":
    unittest.main()
