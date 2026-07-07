import tempfile
import unittest
from pathlib import Path

from installer_lib.config_sync import compare_paths, apply_sync_plan, ConfigTarget, DEFAULT_CONFIG_TARGETS


class ConfigSyncTests(unittest.TestCase):
    def test_identical_directories_are_skipped_without_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "repo" / "hyprland"
            dest = root / "home" / "hyprland"
            backup_root = root / "backups"
            source.mkdir(parents=True)
            dest.mkdir(parents=True)
            (source / "config.jsonc").write_text("same", encoding="utf-8")
            (dest / "config.jsonc").write_text("same", encoding="utf-8")

            plan = compare_paths("hyprland", source, dest)
            self.assertEqual(plan.status, "identical")
            result = apply_sync_plan(plan, backup_root=backup_root, confirmed=True, timestamp="2026-01-02_030405")

            self.assertEqual(result.action, "skipped")
            self.assertFalse(backup_root.exists())
            self.assertEqual((dest / "config.jsonc").read_text(encoding="utf-8"), "same")

    def test_missing_destination_is_copied_without_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "repo" / "rofi"
            dest = root / "home" / "rofi"
            backup_root = root / "backups"
            source.mkdir(parents=True)
            (source / "config.conf").write_text("repo", encoding="utf-8")

            plan = compare_paths("rofi", source, dest)
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

    def test_different_destination_is_backed_up_then_mirrored_exactly_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "repo" / "swaync"
            dest = root / "home" / "swaync"
            backup_root = root / "backups"
            source.mkdir(parents=True)
            dest.mkdir(parents=True)
            (source / "settings.json").write_text('{"theme":"repo"}', encoding="utf-8")
            (source / "nested").mkdir()
            (source / "nested" / "enabled.conf").write_text("yes", encoding="utf-8")
            (dest / "settings.json").write_text('{"theme":"local"}', encoding="utf-8")
            (dest / "local-only.json").write_text("remove from destination", encoding="utf-8")
            (dest / "old-dir").mkdir()
            (dest / "old-dir" / "old.conf").write_text("remove", encoding="utf-8")
            original_inode = (dest / "settings.json").stat().st_ino

            plan = compare_paths("swaync", source, dest)
            self.assertEqual(plan.status, "different")
            self.assertEqual(plan.changed_count, 1)
            self.assertEqual(plan.added_count, 1)
            self.assertEqual(plan.removed_count, 2)
            result = apply_sync_plan(plan, backup_root=backup_root, confirmed=True, timestamp="2026-01-02_030405")

            self.assertEqual(result.action, "updated")
            self.assertIsNotNone(result.backup_path)
            backup_path = Path(result.backup_path)
            self.assertTrue((backup_path / "settings.json").exists())
            self.assertTrue((backup_path / "local-only.json").exists())
            self.assertTrue((backup_path / "old-dir" / "old.conf").exists())
            self.assertEqual((dest / "settings.json").read_text(encoding="utf-8"), '{"theme":"repo"}')
            self.assertEqual((dest / "settings.json").stat().st_ino, original_inode)
            self.assertEqual((dest / "nested" / "enabled.conf").read_text(encoding="utf-8"), "yes")
            self.assertFalse((dest / "local-only.json").exists())
            self.assertFalse((dest / "old-dir").exists())

    def test_destination_only_ignored_name_is_still_removed_for_exact_mirror(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "repo" / "eww"
            dest = root / "home" / "eww"
            source.mkdir(parents=True)
            dest.mkdir(parents=True)
            (source / "eww.yuck").write_text("repo", encoding="utf-8")
            (dest / "eww.yuck").write_text("repo", encoding="utf-8")
            (dest / "node_modules").mkdir()
            (dest / "node_modules" / "local-only.js").write_text("remove", encoding="utf-8")

            plan = compare_paths("eww", source, dest)
            self.assertEqual(plan.status, "different")
            self.assertEqual(plan.removed_count, 1)
            apply_sync_plan(plan, backup_root=root / "backups", confirmed=True, timestamp="2026-01-02_030405")

            self.assertFalse((dest / "node_modules").exists())

    def test_config_target_resolves_repo_and_home_paths(self):
        root = Path("/repo")
        home = Path("/home/user")
        target = ConfigTarget("rofi", "Rofi", "rofi/configs", ".config/rofi")

        self.assertEqual(target.repo_path(root), Path("/repo/rofi/configs"))
        self.assertEqual(target.home_path(home), Path("/home/user/.config/rofi"))

    def test_default_targets_include_eww_config_sync(self):
        targets = {target.key: target for target in DEFAULT_CONFIG_TARGETS}

        self.assertIn("eww", targets)
        self.assertEqual(targets["eww"].repo_relative, "eww/configs")
        self.assertEqual(targets["eww"].home_relative, ".config/eww")
        self.assertEqual(targets["eww"].commands, ("eww",))

    def test_default_targets_include_ghostty_config_sync(self):
        targets = {target.key: target for target in DEFAULT_CONFIG_TARGETS}

        self.assertIn("ghostty", targets)
        self.assertEqual(targets["ghostty"].repo_relative, "ghostty/configs")
        self.assertEqual(targets["ghostty"].home_relative, ".config/ghostty")
        self.assertEqual(targets["ghostty"].commands, ("ghostty",))


if __name__ == "__main__":
    unittest.main()
