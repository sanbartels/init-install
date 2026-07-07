import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KEYBINDS = ROOT / "hyprland" / "configs" / "keybinds.conf"
RUN_OR_NOTIFY = ROOT / "hyprland" / "configs" / "run-or-notify"


class HyprlandKeybindsTests(unittest.TestCase):
    def test_mainmod_shift_t_opens_ghostty_with_missing_program_notice(self):
        source = KEYBINDS.read_text(encoding="utf-8")

        self.assertIn("$runOrNotify ghostty -- ghostty", source)
        self.assertNotIn("bind = CTRL SHIFT, T, exec, ghostty", source)

    def test_run_or_notify_helper_exists_and_falls_back_without_notify_send(self):
        source = RUN_OR_NOTIFY.read_text(encoding="utf-8")

        self.assertIn("Missing dependency", source)
        self.assertIn("notify-send", source)
        self.assertIn("echo", source)
        self.assertIn("exec", source)

    def test_optional_keybinds_use_run_or_notify(self):
        source = KEYBINDS.read_text(encoding="utf-8")
        expected_fragments = (
            "$runOrNotify flameshot -- flameshot gui",
            "$runOrNotify rofi -- $menu",
            "$runOrNotify kitty -- $terminal",
            "$runOrNotify kitty yazi -- $fileManager",
            "$runOrNotify discord -- discord",
            "$runOrNotify cliphist rofi wl-copy -- $HOME/.config/hypr/clipboard-history.sh",
            "$runOrNotify rofi xdg-open python3 -- $HOME/.config/hypr/web-spotlight.sh",
            "$runOrNotify fd rg rofi git -- $HOME/.config/hypr/find-open.sh --projects",
            "$runOrNotify eww -- $HOME/.config/eww/scripts/toggle-system-widget",
            "$runOrNotify pavucontrol -- pavucontrol",
            "$runOrNotify wpctl -- wpctl set-volume",
            "$runOrNotify brightnessctl -- brightnessctl",
            "$runOrNotify playerctl -- playerctl play-pause",
        )

        for fragment in expected_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, source)


if __name__ == "__main__":
    unittest.main()
