import tempfile
import unittest
from pathlib import Path

from installer_lib.config_sync import compare_paths, apply_sync_plan, ConfigTarget


class ConfigSyncTests(unittest.TestCase):
    def test_identical_directories_are_skipped_without_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "repo" / "waybar"
            dest = root / "home" / "waybar"
            backup_root = root / "backups"
            source.mkdir(parents=True)
            dest.mkdir(parents=True)
            (source / "config.jsonc").write_text("same", encoding="utf-8")
            (dest / "config.jsonc").write_text("same", encoding="utf-8")

            plan = compare_paths("waybar", source, dest)
            self.assertEqual(plan.status, "identical")
            result = apply_sync_plan(plan, backup_root=backup_root, confirmed=True, timestamp="2026-01-02_030405")

            self.assertEqual(result.action, "skipped")
            self.assertFalse(backup_root.exists())
            self.assertEqual((dest / "config.jsonc").read_text(encoding="utf-8"), "same")

    def test_missing_destination_is_copied_without_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "repo" / "mango"
            dest = root / "home" / "mango"
            backup_root = root / "backups"
            source.mkdir(parents=True)
            (source / "config.conf").write_text("repo", encoding="utf-8")

            plan = compare_paths("mango", source, dest)
            self.assertEqual(plan.status, "missing_destination")
            result = apply_sync_plan(plan, backup_root=backup_root, confirmed=True, timestamp="2026-01-02_030405")

            self.assertEqual(result.action, "copied")
            self.assertIsNone(result.backup_path)
            self.assertEqual((dest / "config.conf").read_text(encoding="utf-8"), "repo")

    def test_different_destination_requires_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "repo" / "kitty"
            dest = root / "home" / "kitty"
            backup_root = root / "backups"
            source.mkdir(parents=True)
            dest.mkdir(parents=True)
            (source / "kitty.conf").write_text("repo", encoding="utf-8")
            (dest / "kitty.conf").write_text("local", encoding="utf-8")

            plan = compare_paths("kitty", source, dest)
            self.assertEqual(plan.status, "different")
            result = apply_sync_plan(plan, backup_root=backup_root, confirmed=False, timestamp="2026-01-02_030405")

            self.assertEqual(result.action, "cancelled")
            self.assertEqual((dest / "kitty.conf").read_text(encoding="utf-8"), "local")
            self.assertFalse(backup_root.exists())

    def test_different_destination_is_backed_up_then_replaced_exactly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "repo" / "noctalia"
            dest = root / "home" / "noctalia"
            backup_root = root / "backups"
            source.mkdir(parents=True)
            dest.mkdir(parents=True)
            (source / "settings.json").write_text('{"theme":"repo"}', encoding="utf-8")
            (dest / "settings.json").write_text('{"theme":"local"}', encoding="utf-8")
            (dest / "local-only.json").write_text("remove from destination", encoding="utf-8")

            plan = compare_paths("noctalia", source, dest)
            self.assertEqual(plan.status, "different")
            self.assertEqual(plan.changed_count, 1)
            self.assertEqual(plan.removed_count, 1)
            result = apply_sync_plan(plan, backup_root=backup_root, confirmed=True, timestamp="2026-01-02_030405")

            self.assertEqual(result.action, "updated")
            self.assertIsNotNone(result.backup_path)
            backup_path = Path(result.backup_path)
            self.assertTrue((backup_path / "settings.json").exists())
            self.assertTrue((backup_path / "local-only.json").exists())
            self.assertEqual((dest / "settings.json").read_text(encoding="utf-8"), '{"theme":"repo"}')
            self.assertFalse((dest / "local-only.json").exists())

    def test_config_target_resolves_repo_and_home_paths(self):
        root = Path("/repo")
        home = Path("/home/user")
        target = ConfigTarget("mango", "Mango", "mango/configs", ".config/mango")

        self.assertEqual(target.repo_path(root), Path("/repo/mango/configs"))
        self.assertEqual(target.home_path(home), Path("/home/user/.config/mango"))


if __name__ == "__main__":
    unittest.main()
