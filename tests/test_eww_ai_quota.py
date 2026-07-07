import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EWW = ROOT / "eww" / "configs"
YUCK = EWW / "eww.yuck"
SCSS = EWW / "eww.scss"
SCRIPTS = EWW / "scripts"
KEYBINDS = ROOT / "hyprland" / "configs" / "keybinds.conf"
CHEATSHEET = SCRIPTS / "hypr-keybinds-cheatsheet"


class EwwAiQuotaTests(unittest.TestCase):
    def test_super_o_uses_ai_quota_carousel(self):
        source = KEYBINDS.read_text(encoding="utf-8")

        self.assertIn("bind = $mainMod, O, exec, $HOME/.config/eww/scripts/toggle-ai-quota", source)
        self.assertNotIn("bind = $mainMod, O, exec, $HOME/.config/eww/scripts/toggle-chatgpt-usage", source)

    def test_gemini_quota_widget_and_polls_exist(self):
        source = YUCK.read_text(encoding="utf-8")

        for expected in [
            "(defpoll agy_gemini_5h",
            "(defpoll agy_gemini_weekly",
            "(defpoll agy_3p_5h",
            "(defpoll agy_3p_weekly",
            "(defwidget gemini-usage []",
            "(defwindow gemini-usage",
            ":text \"GEMINI QUOTA\"",
        ]:
            with self.subTest(expected=expected):
                self.assertIn(expected, source)

    def test_ai_quota_scripts_exist_and_are_executable(self):
        for script in ["agy-usage-info", "toggle-ai-quota"]:
            path = SCRIPTS / script
            with self.subTest(script=script):
                self.assertTrue(path.exists())
                self.assertTrue(path.stat().st_mode & 0o111)

    def test_styles_and_cheatsheet_reference_ai_quota(self):
        scss = SCSS.read_text(encoding="utf-8")
        cheatsheet = CHEATSHEET.read_text(encoding="utf-8")

        self.assertIn(".gemini-usage", scss)
        self.assertIn("toggle-ai-quota", cheatsheet)
        self.assertNotIn("toggle-chatgpt-usage", cheatsheet)


if __name__ == "__main__":
    unittest.main()
