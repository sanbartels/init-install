import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KEYBINDS = ROOT / "hyprland" / "configs" / "keybinds.conf"


class HyprlandKeybindsTests(unittest.TestCase):
    def test_mainmod_shift_t_opens_ghostty(self):
        source = KEYBINDS.read_text(encoding="utf-8")

        self.assertIn("bind = $mainMod SHIFT, T, exec, ghostty", source)
        self.assertNotIn("bind = CTRL SHIFT, T, exec, ghostty", source)


if __name__ == "__main__":
    unittest.main()
