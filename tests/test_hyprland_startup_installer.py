import os
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path

import install


ROOT = Path(__file__).resolve().parents[1]
INSTALL_PY = ROOT / "install.py"
STARTUP_INSTALLER = ROOT / "hyprland" / "configure_hyprland_startup.sh"
HYPRLAND_INSTALLER = ROOT / "hyprland" / "install_hyprland.sh"
KEYBINDS = ROOT / "hyprland" / "configs" / "keybinds.conf"
README = ROOT / "README.md"


class HyprlandStartupInstallerTests(unittest.TestCase):
    def test_menu_exposes_rerunnable_greetd_startup_independent_from_hyprland_binary(self):
        categories = {category.key: category for category in install.DESKTOP_SECTION.categories}

        self.assertIn("hyprland_startup", categories)
        self.assertEqual(categories["hyprland_startup"].scripts, install.scripts("hyprland/configure_hyprland_startup.sh"))
        self.assertFalse(categories["hyprland_startup"].install_detector())
        self.assertEqual(categories["hyprland"].scripts, install.scripts("hyprland/install_hyprland.sh"))

    def test_startup_installer_uses_noninteractive_sudo_and_installs_greetd_packages(self):
        source = STARTUP_INSTALLER.read_text(encoding="utf-8")

        self.assertIn("sudo -n true", source)
        self.assertIn("sudo -n pacman -S --needed --noconfirm", source)
        self.assertIn("greetd-agreety", source)
        self.assertIn("sudo -n systemctl enable --now greetd.service", source)
        self.assertIn("Run 'sudo -v' in an interactive SSH session", source)
        self.assertNotIn("sudo pacman -S", source)

    def test_startup_installer_fails_before_privileged_mutation_when_sudo_is_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            home = root / "home"
            config = root / "etc" / "greetd" / "config.toml"
            calls = root / "calls.log"
            bin_dir.mkdir()
            home.mkdir()
            self._write_base_mocks(bin_dir, calls, home, sudo_preflight_status=1)
            env = self._env(bin_dir, home, config)

            result = subprocess.run(["/bin/bash", str(STARTUP_INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("non-interactive sudo", result.stderr)
        self.assertIn("sudo -n true", log)
        self.assertNotIn("sudo -n pacman", log)
        self.assertNotIn("systemctl enable --now greetd.service", log)
        self.assertFalse((home / ".local" / "bin" / "init-install-start-hyprland").exists())
        self.assertFalse(config.exists())

    def test_startup_installer_rejects_unsafe_config_path_before_sudo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            home = root / "home"
            calls = root / "calls.log"
            bin_dir.mkdir()
            home.mkdir()
            self._write_base_mocks(bin_dir, calls, home)
            env = self._env(bin_dir, home, Path(tmp) / "bad path" / "config.toml")

            result = subprocess.run(["/bin/bash", str(STARTUP_INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8") if calls.exists() else ""

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsupported TOML/shell-special characters", result.stderr)
        self.assertNotIn("sudo -n true", log)
        self.assertNotIn("systemctl", log)

    def test_startup_installer_rejects_root_autologin_user(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            home = root / "home"
            config = root / "etc" / "greetd" / "config.toml"
            calls = root / "calls.log"
            bin_dir.mkdir()
            home.mkdir()
            self._write_base_mocks(bin_dir, calls, home, current_uid="0", current_user="root")
            env = self._env(bin_dir, home, config)
            env["USER"] = "root"
            env["SUDO_USER"] = "root"

            result = subprocess.run(["/bin/bash", str(STARTUP_INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refusing to configure root autologin", result.stderr)
        self.assertNotIn("systemctl enable --now greetd.service", log)
        self.assertFalse(config.exists())

    def test_startup_installer_writes_launcher_and_managed_greetd_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            home = root / "home"
            config = root / "etc" / "greetd" / "config.toml"
            calls = root / "calls.log"
            bin_dir.mkdir()
            home.mkdir()
            self._write_base_mocks(bin_dir, calls, home)
            env = self._env(bin_dir, home, config)

            result = subprocess.run(["/bin/bash", str(STARTUP_INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8")
            launcher = home / ".local" / "bin" / "init-install-start-hyprland"
            launcher_source = launcher.read_text(encoding="utf-8")
            config_source = config.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("sudo -n true", log)
        self.assertIn("sudo -n systemctl enable --now greetd.service", log)
        self.assertIn("# init-install managed Hyprland startup", config_source)
        self.assertIn("[terminal]", config_source)
        self.assertIn("vt = 1", config_source)
        self.assertIn("[default_session]", config_source)
        self.assertIn('command = "agreety --cmd /bin/bash"', config_source)
        self.assertIn("[initial_session]", config_source)
        self.assertIn(f'command = "{launcher}"', config_source)
        self.assertIn('user = "tester"', config_source)
        for expected in [
            "XDG_SESSION_TYPE=wayland",
            "XDG_CURRENT_DESKTOP=Hyprland",
            "XDG_SESSION_DESKTOP=Hyprland",
            "GNOME_KEYRING_CONTROL",
            "HYPRLAND_START_RETRY_MIN_SECONDS",
            "HYPRLAND_START_RETRY_MAX_SECONDS",
            "trap stop_child INT TERM HUP",
            '"$command_name" &',
            "retrying in ${delay}s",
        ]:
            self.assertIn(expected, launcher_source)
        self.assertIn("Provider console access reaches the autologged-in desktop session", result.stdout)

    def test_startup_installer_rejects_toml_and_shell_special_home_values(self):
        unsafe_homes = [
            '/tmp/bad"home',
            '/tmp/bad\\home',
            '/tmp/bad;home',
            '/tmp/bad\thome',
        ]
        for unsafe_home in unsafe_homes:
            with self.subTest(unsafe_home=unsafe_home):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    bin_dir = root / "bin"
                    home = root / "home"
                    config = root / "etc" / "greetd" / "config.toml"
                    calls = root / "calls.log"
                    bin_dir.mkdir()
                    home.mkdir()
                    self._write_base_mocks(bin_dir, calls, home, passwd_home=unsafe_home)
                    env = self._env(bin_dir, home, config)

                    result = subprocess.run(["/bin/bash", str(STARTUP_INSTALLER)], env=env, text=True, capture_output=True)
                    log = calls.read_text(encoding="utf-8")

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("unsupported TOML/shell-special characters", result.stderr)
                self.assertNotIn("systemctl enable --now greetd.service", log)
                self.assertFalse(config.exists())

    def test_startup_installer_rejects_symlinked_launcher_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            home = root / "home"
            escaped = root / "escaped-local"
            config = root / "etc" / "greetd" / "config.toml"
            calls = root / "calls.log"
            bin_dir.mkdir()
            home.mkdir()
            escaped.mkdir()
            (home / ".local").symlink_to(escaped, target_is_directory=True)
            self._write_base_mocks(bin_dir, calls, home)
            env = self._env(bin_dir, home, config)

            result = subprocess.run(["/bin/bash", str(STARTUP_INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refusing symlinked managed launcher parent", result.stderr)
        self.assertNotIn("systemctl enable --now greetd.service", log)
        self.assertFalse(config.exists())

    def test_startup_installer_backs_up_unmanaged_config_and_is_idempotent_when_managed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            home = root / "home"
            config = root / "etc" / "greetd" / "config.toml"
            calls = root / "calls.log"
            bin_dir.mkdir()
            home.mkdir()
            config.parent.mkdir(parents=True)
            config.write_text("[terminal]\nvt = 2\n", encoding="utf-8")
            self._write_base_mocks(bin_dir, calls, home)
            env = self._env(bin_dir, home, config)

            first = subprocess.run(["/bin/bash", str(STARTUP_INSTALLER)], env=env, text=True, capture_output=True)
            backups_after_first = sorted(config.parent.glob("config.toml.init-install-backup.*"))
            backup_source = backups_after_first[0].read_text(encoding="utf-8") if backups_after_first else ""
            second = subprocess.run(["/bin/bash", str(STARTUP_INSTALLER)], env=env, text=True, capture_output=True)
            backups_after_second = sorted(config.parent.glob("config.toml.init-install-backup.*"))

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(len(backups_after_first), 1)
        self.assertEqual(backups_after_first, backups_after_second)
        self.assertEqual(backup_source, "[terminal]\nvt = 2\n")

    def test_startup_installer_rolls_back_when_greetd_start_fails_after_config_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            home = root / "home"
            config = root / "etc" / "greetd" / "config.toml"
            calls = root / "calls.log"
            bin_dir.mkdir()
            home.mkdir()
            self._write_base_mocks(bin_dir, calls, home, greetd_start_status=1)
            env = self._env(bin_dir, home, config)

            result = subprocess.run(["/bin/bash", str(STARTUP_INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Failed to enable/start greetd.service", result.stderr)
        self.assertIn("systemctl disable --now greetd.service", log)
        self.assertFalse(config.exists())

    def test_startup_installer_restores_the_prior_greetd_enabled_and_active_state_on_rollback(self):
        for was_enabled, was_active, expected_restore_calls in [
            (True, True, ["systemctl disable --now greetd.service", "systemctl enable --now greetd.service"]),
            (True, False, ["systemctl disable --now greetd.service", "systemctl enable greetd.service", "systemctl stop greetd.service"]),
            (False, True, ["systemctl disable --now greetd.service", "systemctl disable greetd.service", "systemctl start greetd.service"]),
            (False, False, ["systemctl disable --now greetd.service", "systemctl disable --now greetd.service"]),
        ]:
            with self.subTest(was_enabled=was_enabled, was_active=was_active):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    bin_dir = root / "bin"
                    home = root / "home"
                    config = root / "etc" / "greetd" / "config.toml"
                    calls = root / "calls.log"
                    bin_dir.mkdir()
                    home.mkdir()
                    self._write_base_mocks(
                        bin_dir,
                        calls,
                        home,
                        greetd_start_status=1,
                        greetd_was_enabled=was_enabled,
                        greetd_was_active=was_active,
                    )
                    env = self._env(bin_dir, home, config)

                    result = subprocess.run(["/bin/bash", str(STARTUP_INSTALLER)], env=env, text=True, capture_output=True)
                    log = calls.read_text(encoding="utf-8")

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("systemctl is-enabled --quiet greetd.service", log)
                self.assertIn("systemctl is-active --quiet greetd.service", log)
                systemctl_calls = [call for call in log.splitlines() if call.startswith("systemctl ")]
                self.assertEqual(systemctl_calls[-len(expected_restore_calls) :], expected_restore_calls)

    def test_startup_installer_routes_post_install_config_hash_mismatch_through_transactional_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            home = root / "home"
            config = root / "etc" / "greetd" / "config.toml"
            calls = root / "calls.log"
            previous_launcher = home / ".local" / "bin" / "init-install-start-hyprland"
            changed_config = "# init-install managed Hyprland startup\n[foreign]\nowner = \"operator\"\n"
            bin_dir.mkdir()
            home.mkdir()
            config.parent.mkdir(parents=True)
            config.write_text("[terminal]\nvt = 2\n", encoding="utf-8")
            previous_launcher.parent.mkdir(parents=True)
            previous_launcher.write_text("#!/bin/bash\necho previous launcher\n", encoding="utf-8")
            previous_launcher.chmod(0o755)
            self._write_base_mocks(
                bin_dir,
                calls,
                home,
                mutate_config_after_install=True,
                config_path=config,
                mutate_config_content=changed_config,
            )
            env = self._env(bin_dir, home, config)

            result = subprocess.run(["/bin/bash", str(STARTUP_INSTALLER)], env=env, text=True, capture_output=True)
            config_source = config.read_text(encoding="utf-8")
            launcher_source = previous_launcher.read_text(encoding="utf-8")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Managed greetd config hash mismatch after install", result.stderr)
        self.assertIn("no longer matches the exact installed managed content", result.stdout)
        self.assertEqual(config_source, changed_config)
        self.assertEqual(launcher_source, "#!/bin/bash\necho previous launcher\n")

    def test_startup_installer_reports_recovery_evidence_for_post_install_launcher_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            home = root / "home"
            config = root / "etc" / "greetd" / "config.toml"
            calls = root / "calls.log"
            launcher = home / ".local" / "bin" / "init-install-start-hyprland"
            bin_dir.mkdir()
            home.mkdir()
            self._write_base_mocks(bin_dir, calls, home, mutate_launcher_after_install=True)
            env = self._env(bin_dir, home, config)

            result = subprocess.run(["/bin/bash", str(STARTUP_INSTALLER)], env=env, text=True, capture_output=True)
            launcher_source = launcher.read_text(encoding="utf-8")
            config_exists = config.exists()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Managed launcher hash mismatch after install", result.stderr)
        self.assertIn("Recovery evidence commands", result.stderr)
        self.assertEqual(launcher_source, "#!/bin/bash\necho externally changed launcher\n")
        self.assertFalse(config_exists)

    def test_startup_installer_restores_unmanaged_config_when_post_start_validation_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            home = root / "home"
            config = root / "etc" / "greetd" / "config.toml"
            calls = root / "calls.log"
            bin_dir.mkdir()
            home.mkdir()
            config.parent.mkdir(parents=True)
            config.write_text("[terminal]\nvt = 2\n", encoding="utf-8")
            existing_launcher = home / ".local" / "bin" / "init-install-start-hyprland"
            existing_launcher.parent.mkdir(parents=True)
            existing_launcher.write_text("#!/bin/bash\necho previous launcher\n", encoding="utf-8")
            existing_launcher.chmod(0o755)
            self._write_base_mocks(bin_dir, calls, home, validation_has_virtual=False)
            env = self._env(bin_dir, home, config)

            result = subprocess.run(["/bin/bash", str(STARTUP_INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8")
            config_source = config.read_text(encoding="utf-8")
            launcher_source = existing_launcher.read_text(encoding="utf-8")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Hyprland startup validation failed", result.stderr)
        self.assertIn("systemctl disable --now greetd.service", log)
        self.assertEqual(config_source, "[terminal]\nvt = 2\n")
        self.assertEqual(launcher_source, "#!/bin/bash\necho previous launcher\n")

    def test_startup_installer_preserves_changed_config_when_exact_managed_hash_differs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            home = root / "home"
            config = root / "etc" / "greetd" / "config.toml"
            calls = root / "calls.log"
            bin_dir.mkdir()
            home.mkdir()
            changed_content = "# init-install managed Hyprland startup\n[foreign]\nowner = \"operator\"\n"
            self._write_base_mocks(bin_dir, calls, home, greetd_start_status=1, mutate_config_on_enable=True, config_path=config, mutate_config_content=changed_content)
            env = self._env(bin_dir, home, config)

            result = subprocess.run(["/bin/bash", str(STARTUP_INSTALLER)], env=env, text=True, capture_output=True)
            config_source = config.read_text(encoding="utf-8")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no longer matches the exact installed managed content", result.stdout)
        self.assertEqual(config_source, changed_content)

    def test_startup_installer_rejects_root_parent_symlink_before_privileged_launcher_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            home = root / "home"
            escaped = root / "escaped-local"
            config = root / "etc" / "greetd" / "config.toml"
            calls = root / "calls.log"
            bin_dir.mkdir()
            home.mkdir()
            escaped.mkdir()
            (home / ".local").symlink_to(escaped, target_is_directory=True)
            self._write_base_mocks(bin_dir, calls, home, current_uid="0", current_user="tester")
            env = self._env(bin_dir, home, config)
            env["USER"] = "root"
            env["SUDO_USER"] = "tester"

            result = subprocess.run(["/bin/bash", str(STARTUP_INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refusing symlinked managed launcher parent", result.stderr)
        self.assertNotIn("sudo -n -u tester install", log)
        self.assertFalse(config.exists())

    def test_startup_installer_fails_before_config_mutation_when_tty1_conflict_is_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            home = root / "home"
            config = root / "etc" / "greetd" / "config.toml"
            calls = root / "calls.log"
            bin_dir.mkdir()
            home.mkdir()
            self._write_base_mocks(bin_dir, calls, home, include_tty_conflict=False)
            env = self._env(bin_dir, home, config)

            result = subprocess.run(["/bin/bash", str(STARTUP_INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not prove Conflicts=getty@tty1.service", result.stderr)
        self.assertNotIn("systemctl enable --now greetd.service", log)
        self.assertFalse(config.exists())

    def test_managed_launcher_retries_failed_hyprland_start_with_backoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            home = root / "home"
            config = root / "etc" / "greetd" / "config.toml"
            calls = root / "calls.log"
            state = root / "start-count"
            bin_dir.mkdir()
            home.mkdir()
            self._write_base_mocks(bin_dir, calls, home)
            env = self._env(bin_dir, home, config)
            install_result = subprocess.run(["/bin/bash", str(STARTUP_INSTALLER)], env=env, text=True, capture_output=True)
            self.assertEqual(install_result.returncode, 0, install_result.stderr)
            self._write_mock(
                bin_dir / "start-hyprland",
                f"""#!/bin/bash
count=0
if [ -f {state} ]; then IFS= read -r count < {state}; fi
count=$((count + 1))
printf '%s\n' "$count" > {state}
if [ "$count" -eq 1 ]; then exit 9; fi
exit 0
""",
            )

            launcher = home / ".local" / "bin" / "init-install-start-hyprland"
            run_result = subprocess.run(
                [str(launcher)],
                env={**env, "HYPRLAND_START_RETRY_MIN_SECONDS": "1", "HYPRLAND_START_RETRY_MAX_SECONDS": "1"},
                text=True,
                capture_output=True,
                timeout=5,
            )

        self.assertEqual(run_result.returncode, 0, run_result.stderr)
        self.assertIn("Hyprland exited with status 9; retrying in 1s", run_result.stderr)
        self.assertIn("Starting Hyprland with start-hyprland (attempt 2)", run_result.stderr)

    def test_startup_installer_installs_missing_greetd_package_only_after_sudo_preflight(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            home = root / "home"
            config = root / "etc" / "greetd" / "config.toml"
            calls = root / "calls.log"
            bin_dir.mkdir()
            home.mkdir()
            self._write_base_mocks(bin_dir, calls, home, missing_packages=("greetd",))
            env = self._env(bin_dir, home, config)

            result = subprocess.run(["/bin/bash", str(STARTUP_INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("sudo -n true", log)
        self.assertIn("sudo -n pacman -S --needed --noconfirm greetd", log)
        self.assertLess(log.index("sudo -n true"), log.index("sudo -n pacman -S --needed --noconfirm greetd"))

    def test_startup_docs_include_operator_path_tradeoff_pre_reboot_and_rollback(self):
        readme = README.read_text(encoding="utf-8")

        for expected in [
            "Install desktop / bar -> Hyprland startup (greetd)",
            "sudo -v",
            "systemctl status greetd.service --no-pager",
            "journalctl -u greetd.service -b --no-pager",
            "hyprctl instances -j",
            "hyprctl monitors -j",
            "Virtual-1",
            "systemctl --user status wayvnc.service --no-pager",
            "ss -H -ltnp",
            "managed-config-sha256-from-installer-output",
            "backup_path='<printed-backup-path-or-empty-or-__NO_PRIOR_CONFIG__>'",
            "if [ \"$current_config_sha256\" != \"$managed_config_sha256\" ]; then",
            "elif [ -n \"$backup_path\" ] && [ \"$backup_path\" != \"__NO_PRIOR_CONFIG__\" ]; then",
            "elif [ \"$backup_path\" = \"__NO_PRIOR_CONFIG__\" ]; then",
            "prior backup path is unknown; preserving config",
            "sudo systemctl disable --now greetd.service",
            "sudo grep -Fx '# init-install managed Hyprland startup' /etc/greetd/config.toml",
            "Provider console access reaches the autologged-in desktop session",
            "Do not reboot blindly",
        ]:
            self.assertIn(expected, readme)
        self.assertNotIn("grep -Fx '# init-install managed Hyprland startup' /etc/greetd/config.toml &&", readme)
        self.assertNotIn("/etc/greetd/config.toml.init-install-backup.<timestamp>", readme)

    def test_startup_installer_is_executable_for_the_documented_direct_invocation(self):
        self.assertTrue(os.access(STARTUP_INSTALLER, os.X_OK))

    def test_startup_installer_prints_exact_hash_mutually_exclusive_recovery_commands(self):
        source = STARTUP_INSTALLER.read_text(encoding="utf-8")

        for expected in [
            "managed_config_sha256='$MANAGED_CONFIG_HASH'",
            "backup_path='$recovery_backup_path'",
            "if [ \"\\$current_config_sha256\" != \"\\$managed_config_sha256\" ]; then",
            "elif [ -n \"\\$backup_path\" ] && [ \"\\$backup_path\" != '__NO_PRIOR_CONFIG__' ]; then",
            "elif [ \"\\$backup_path\" = '__NO_PRIOR_CONFIG__' ]; then",
            "prior backup path is unknown; preserving config",
        ]:
            self.assertIn(expected, source)
        self.assertNotIn("grep -Fx '$MANAGED_MARKER_LINE' '$GREETD_CONFIG_PATH' && sudo install", source)
        self.assertNotIn("grep -Fx '$MANAGED_MARKER_LINE' '$GREETD_CONFIG_PATH' && sudo rm", source)

    def test_no_kitty_keybind_or_dependency_changes_were_added_for_startup(self):
        install_source = INSTALL_PY.read_text(encoding="utf-8")
        hyprland_installer = HYPRLAND_INSTALLER.read_text(encoding="utf-8")
        startup_source = STARTUP_INSTALLER.read_text(encoding="utf-8")
        keybinds = KEYBINDS.read_text(encoding="utf-8")

        self.assertIn('Category("kitty", "Kitty", "Terminal Kitty"', install_source)
        self.assertNotIn("kitty", hyprland_installer.lower())
        self.assertNotIn("kitty", startup_source.lower())
        self.assertIn("$runOrNotify kitty -- $terminal", keybinds)
        self.assertIn("$runOrNotify kitty yazi -- $fileManager", keybinds)

    @staticmethod
    def _write_mock(path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)

    def _write_base_mocks(
        self,
        bin_dir: Path,
        calls: Path,
        home: Path,
        *,
        current_uid: str = "1000",
        current_user: str = "tester",
        sudo_preflight_status: int = 0,
        missing_packages: tuple[str, ...] = (),
        passwd_home: str | None = None,
        greetd_start_status: int = 0,
        validation_has_virtual: bool = True,
        include_tty_conflict: bool = True,
        mutate_config_on_enable: bool = False,
        mutate_config_after_install: bool = False,
        mutate_launcher_after_install: bool = False,
        config_path: Path | None = None,
        mutate_config_content: str = "[foreign]\nowner = \"operator\"\n",
        greetd_was_enabled: bool = True,
        greetd_was_active: bool = True,
    ) -> None:
        package_state = bin_dir.parent / "packages"
        runtime_dir = bin_dir.parent / "run-user" / "1000"
        runtime_dir.mkdir(parents=True)
        self._create_unix_socket(runtime_dir / "wayland-1")
        passwd_home = passwd_home if passwd_home is not None else str(home)
        escaped_post_install_config = mutate_config_content.replace("'", "'\\''")
        package_state.mkdir()
        for package in ("greetd", "greetd-agreety"):
            if package not in missing_packages:
                (package_state / package).touch()
        self._write_mock(
            bin_dir / "id",
            f"""#!/bin/bash
if [ "$1" = "-u" ] && [ "$#" -eq 1 ]; then printf '{current_uid}\n'; exit 0; fi
if [ "$1" = "-u" ]; then
  case "$2" in root) printf '0\n' ;; *) printf '1000\n' ;; esac
  exit 0
fi
if [ "$1" = "-un" ]; then printf '{current_user}\n'; exit 0; fi
if [ "$1" = "-gn" ]; then printf '{current_user}\n'; exit 0; fi
/usr/bin/id "$@"
""",
        )
        self._write_mock(
            bin_dir / "getent",
            f"#!/bin/bash\nif [ \"$1\" = \"passwd\" ]; then printf '%s:x:1000:1000:Test User:%s:/bin/bash\\n' '{current_user}' '{passwd_home}'; exit 0; fi\nexit 2\n",
        )
        self._write_mock(
            bin_dir / "pacman",
            f"""#!/bin/bash
if [ "$1" = "-Qi" ]; then test -f {package_state}/$2; exit $?; fi
exit 0
""",
        )
        self._write_mock(
            bin_dir / "sudo",
            f"""#!/bin/bash
echo sudo $@ >> {calls}
if [ "$1" = "-n" ] && [ "$2" = "true" ]; then exit {sudo_preflight_status}; fi
if [ "$1" = "-n" ] && [ "$2" = "pacman" ]; then
  shift 2
  for arg in "$@"; do
    case "$arg" in greetd|greetd-agreety) touch {package_state}/$arg ;; esac
  done
  exit 0
fi
if [ "$1" = "-n" ]; then shift; fi
if [ "${{1:-}}" = "mv" ] && [ "${{@: -1}}" = "{config_path}" ] && [ {1 if mutate_config_after_install else 0} -eq 1 ]; then
  "$@"
  status="$?"
  [ "$status" -ne 0 ] || printf '%s' '{escaped_post_install_config}' > {config_path}
  exit "$status"
fi
if [ "$1" = "-u" ]; then shift 2; fi
exec "$@"
""",
        )
        self._write_mock(
            bin_dir / "install",
            f"""#!/bin/bash
/usr/bin/install "$@"
status="$?"
if [ "$status" -eq 0 ] && [ "${{@: -1}}" = "{home / '.local' / 'bin' / 'init-install-start-hyprland'}" ] && [ {1 if mutate_launcher_after_install else 0} -eq 1 ]; then
  printf '%s' '#!/bin/bash\necho externally changed launcher\n' > "${{@: -1}}"
fi
exit "$status"
""",
        )
        tty_conflict_line = "Conflicts=getty@tty1.service" if include_tty_conflict else "After=getty@tty1.service"
        mutation = ""
        if mutate_config_on_enable and config_path is not None:
            escaped_content = mutate_config_content.replace("'", "'\\''")
            mutation = f"printf '%s' '{escaped_content}' > {config_path}\n"
        self._write_mock(
            bin_dir / "systemctl",
            f"""#!/bin/bash
echo systemctl $@ >> {calls}
if [ "$1" = "cat" ] && [ "$2" = "greetd.service" ]; then printf '[Unit]\n{tty_conflict_line}\n'; exit 0; fi
if [ "$1" = "is-enabled" ] && [ "$2" = "--quiet" ] && [ "$3" = "greetd.service" ]; then exit {0 if greetd_was_enabled else 1}; fi
if [ "$1" = "is-active" ] && [ "$2" = "--quiet" ] && [ "$3" = "greetd.service" ]; then exit {0 if greetd_was_active else 1}; fi
if [ "$1" = "enable" ] && [ "$2" = "--now" ] && [ "$3" = "greetd.service" ]; then
  {mutation}  exit {greetd_start_status}
fi
if [ "$1" = "disable" ] && [ "$2" = "--now" ] && [ "$3" = "greetd.service" ]; then exit 0; fi
exit 0
""",
        )
        monitors_output = '[{"name":"Virtual-1"}]' if validation_has_virtual else '[]'
        self._write_mock(
            bin_dir / "hyprctl",
            f"""#!/bin/bash
if [ "$1" = "instances" ] && [ "$2" = "-j" ]; then printf '[{{"instance":"startup-instance","wl_socket":"wayland-1","pid":4242}}]\n'; exit 0; fi
if [ "$1" = "monitors" ] && [ "$2" = "-j" ] && [ "${{HYPRLAND_INSTANCE_SIGNATURE:-}}" = "startup-instance" ] && [ "${{WAYLAND_DISPLAY:-}}" = "wayland-1" ]; then printf '{monitors_output}\n'; exit 0; fi
printf '[]\n'
exit 0
""",
        )
        self._write_mock(bin_dir / "ps", f"#!/bin/bash\nif [ \"${{@: -1}}\" = \"4242\" ]; then printf '{current_user}\\n'; else printf 'otheruser\\n'; fi\n")
        self._write_mock(bin_dir / "start-hyprland", "#!/bin/bash\nexit 0\n")
        self._write_mock(bin_dir / "Hyprland", "#!/bin/bash\nexit 0\n")

    @staticmethod
    def _create_unix_socket(path: Path) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.bind(str(path))
        finally:
            sock.close()

    @staticmethod
    def _env(bin_dir: Path, home: Path, config: Path) -> dict[str, str]:
        return {
            "PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin",
            "HOME": str(home),
            "USER": "tester",
            "INIT_INSTALL_GREETD_CONFIG_PATH": str(config),
            "HYPRLAND_STARTUP_RUNTIME_DIR": str(config.parents[2] / "run-user" / "1000"),
            "HYPRLAND_STARTUP_VALIDATION_ATTEMPTS": "1",
            "HYPRLAND_STARTUP_VALIDATION_DELAY_SECONDS": "1",
        }


if __name__ == "__main__":
    unittest.main()
