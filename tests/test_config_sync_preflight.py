import tempfile
import unittest
from pathlib import Path

from installer_lib.config_sync import ConfigTarget, evaluate_config_target


class ConfigSyncPreflightTests(unittest.TestCase):
    def test_import_target_detects_program_config_and_defaults_to_selected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_root = root / "repo"
            home = root / "home"
            (repo_root / "kitty" / "configs").mkdir(parents=True)
            (repo_root / "kitty" / "configs" / "kitty.conf").write_text("repo", encoding="utf-8")
            (home / ".config" / "kitty").mkdir(parents=True)
            (home / ".config" / "kitty" / "kitty.conf").write_text("local", encoding="utf-8")
            target = ConfigTarget("kitty", "Kitty", "kitty/configs", ".config/kitty", commands=("kitty",))

            state = evaluate_config_target(target, "import", repo_root, home, command_exists=lambda command: command == "kitty")

            self.assertTrue(state.program_detected)
            self.assertTrue(state.source_exists)
            self.assertTrue(state.destination_exists)
            self.assertEqual(state.plan.status, "different")
            self.assertTrue(state.default_selected)
            self.assertIn("programa detectado", state.summary)
            self.assertIn("diferente", state.summary)

    def test_import_target_without_program_is_not_selected_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_root = root / "repo"
            home = root / "home"
            (repo_root / "rofi" / "configs").mkdir(parents=True)
            (repo_root / "rofi" / "configs" / "config.rasi").write_text("repo", encoding="utf-8")
            target = ConfigTarget("rofi", "Rofi", "rofi/configs", ".config/rofi", commands=("rofi",))

            state = evaluate_config_target(target, "import", repo_root, home, command_exists=lambda command: False)

            self.assertFalse(state.program_detected)
            self.assertTrue(state.source_exists)
            self.assertFalse(state.default_selected)
            self.assertIn("programa no detectado", state.summary)

    def test_export_target_without_local_config_is_not_selected_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_root = root / "repo"
            home = root / "home"
            target = ConfigTarget("nvim", "Neovim", "nvim/configs", ".config/nvim", commands=("nvim",))

            state = evaluate_config_target(target, "export", repo_root, home, command_exists=lambda command: True)

            self.assertTrue(state.program_detected)
            self.assertFalse(state.source_exists)
            self.assertEqual(state.plan.status, "missing_source")
            self.assertFalse(state.default_selected)
            self.assertIn("config origen no existe", state.summary)


if __name__ == "__main__":
    unittest.main()
