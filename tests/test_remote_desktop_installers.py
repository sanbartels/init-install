import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import install


ROOT = Path(__file__).resolve().parents[1]
SUNSHINE_INSTALLER = ROOT / "remote_desktop" / "install_sunshine.sh"
WAYVNC_INSTALLER = ROOT / "remote_desktop" / "install_wayvnc.sh"
README = ROOT / "README.md"


class RemoteDesktopInstallerTests(unittest.TestCase):
    def test_remote_desktop_options_are_desktop_menu_entries(self):
        categories = {category.key: category for category in install.DESKTOP_SECTION.categories}
        main_action_keys = [action.key for action in install.MAIN_ACTIONS]

        self.assertNotIn("remote_desktop", main_action_keys)
        self.assertIn("sunshine", categories)
        self.assertIn("wayvnc", categories)
        self.assertEqual(categories["sunshine"].scripts, install.scripts("remote_desktop/install_sunshine.sh"))
        self.assertEqual(categories["wayvnc"].scripts, install.scripts("remote_desktop/install_wayvnc.sh"))

    def test_sunshine_installer_fails_fast_without_yay(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"PATH": tmp}
            result = subprocess.run(["/bin/bash", str(SUNSHINE_INSTALLER)], env=env, text=True, capture_output=True)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing required command: yay", result.stderr)

    def test_sunshine_installer_sudo_preflight_fails_before_privileged_installs(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            calls = bin_dir / "calls.log"
            self._write_mock(bin_dir / "yay", f"#!/bin/bash\necho yay $@ >> {calls}\nexit 0\n")
            self._write_mock(
                bin_dir / "sudo",
                f"#!/bin/bash\necho sudo $@ >> {calls}\nif [ \"$1\" = \"-n\" ] && [ \"$2\" = \"true\" ]; then exit 1; fi\nexit 0\n",
            )
            self._write_mock(bin_dir / "pacman", f"#!/bin/bash\necho pacman $@ >> {calls}\nexit 0\n")
            env = {"PATH": str(bin_dir), "USER": "tester"}

            result = subprocess.run(["/bin/bash", str(SUNSHINE_INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sudo credentials are not available", result.stderr)
        self.assertIn("sudo -v", result.stderr)
        self.assertIn("init-install menu", result.stderr)
        self.assertIn("sudo -n true", log)
        self.assertNotIn("yay -S", log)
        self.assertNotIn("sudo pacman", log)
        self.assertNotIn("pacman -S", log)

    def test_sunshine_installer_fails_clearly_when_sudo_cache_expires_before_pacman(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            calls = bin_dir / "calls.log"
            state = bin_dir / "sudo-preflight-count"
            self._write_mock(bin_dir / "yay", f"#!/bin/bash\necho yay $@ >> {calls}\nexit 0\n")
            self._write_mock(
                bin_dir / "sudo",
                f"""#!/bin/bash
echo sudo $@ >> {calls}
if [ "$1" = "-n" ] && [ "$2" = "true" ]; then
  count=0
  if [ -f {state} ]; then IFS= read -r count < {state}; fi
  count=$((count + 1))
  printf '%s\n' "$count" > {state}
  if [ "$count" -eq 2 ]; then exit 1; fi
  exit 0
fi
exit 0
""",
            )
            self._write_mock(bin_dir / "pacman", "#!/bin/bash\nexit 0\n")
            env = {"PATH": str(bin_dir), "USER": "tester"}

            result = subprocess.run(["/bin/bash", str(SUNSHINE_INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sudo credentials are not available", result.stderr)
        self.assertIn("sudo -v", result.stderr)
        self.assertIn("init-install menu", result.stderr)
        self.assertEqual(log.count("sudo -n true"), 2)
        self.assertIn("yay -S --needed --noconfirm sunshine", log)
        self.assertNotIn("sudo -n pacman", log)
        self.assertNotIn("pacman -S", log)

    def test_sunshine_installer_fails_clearly_when_sudo_cache_expires_before_loginctl(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            calls = bin_dir / "calls.log"
            state = bin_dir / "sudo-preflight-count"
            self._write_mock(bin_dir / "yay", f"#!/bin/bash\necho yay $@ >> {calls}\nexit 0\n")
            self._write_mock(
                bin_dir / "sudo",
                f"""#!/bin/bash
echo sudo $@ >> {calls}
if [ "$1" = "-n" ] && [ "$2" = "true" ]; then
  count=0
  if [ -f {state} ]; then IFS= read -r count < {state}; fi
  count=$((count + 1))
  printf '%s\n' "$count" > {state}
  if [ "$count" -eq 3 ]; then exit 1; fi
  exit 0
fi
exit 0
""",
            )
            self._write_mock(bin_dir / "pacman", "#!/bin/bash\nexit 0\n")
            self._write_mock(bin_dir / "loginctl", "#!/bin/bash\nexit 0\n")
            env = {"PATH": str(bin_dir), "USER": "tester"}

            result = subprocess.run(["/bin/bash", str(SUNSHINE_INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sudo credentials are not available", result.stderr)
        self.assertIn("sudo -v", result.stderr)
        self.assertIn("init-install menu", result.stderr)
        self.assertEqual(log.count("sudo -n true"), 3)
        self.assertIn("yay -S --needed --noconfirm sunshine", log)
        self.assertIn("sudo -n pacman -S --needed --noconfirm pipewire wireplumber xdg-desktop-portal xdg-desktop-portal-hyprland", log)
        self.assertNotIn("sudo -n loginctl", log)

    def test_sunshine_installer_uses_arch_user_unit_and_capture_stack(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            runtime_root = bin_dir / "run-user"
            runtime_dir = runtime_root / "1000"
            calls = bin_dir / "calls.log"
            runtime_dir.mkdir(parents=True)
            (runtime_dir / "bus").touch()
            self._write_mock(bin_dir / "id", "#!/bin/bash\nif [ \"$1\" = \"-u\" ]; then printf '1000\\n'; else /usr/bin/id \"$@\"; fi\n")
            self._write_mock(bin_dir / "yay", f"#!/bin/bash\necho yay $@ >> {calls}\nexit 0\n")
            self._write_mock(bin_dir / "sudo", f"#!/bin/bash\necho sudo $@ >> {calls}\nexit 0\n")
            self._write_mock(bin_dir / "pacman", "#!/bin/bash\nexit 0\n")
            self._write_mock(
                bin_dir / "systemctl",
                f"#!/bin/bash\necho systemctl $@ XDG_RUNTIME_DIR=${{XDG_RUNTIME_DIR:-}} DBUS_SESSION_BUS_ADDRESS=${{DBUS_SESSION_BUS_ADDRESS:-}} >> {calls}\nif [ \"$1\" = \"--user\" ] && [ \"$2\" = \"cat\" ] && [ \"$3\" = \"app-dev.lizardbyte.app.Sunshine.service\" ]; then exit 0; fi\nexit 0\n",
            )
            self._write_mock(bin_dir / "ss", "#!/bin/bash\nprintf 'LISTEN 0 4096 100.88.77.66:47990 0.0.0.0:*\n'\n")
            self._write_mock(bin_dir / "tailscale", "#!/bin/bash\nif [ \"$1\" = \"ip\" ] && [ \"$2\" = \"-4\" ]; then printf '100.88.77.66\n'; fi\n")
            env = {"PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin", "USER": "tester", "SUNSHINE_RUNTIME_ROOT": str(runtime_root)}

            result = subprocess.run(["/bin/bash", str(SUNSHINE_INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("sudo -n true", log)
        self.assertIn("yay -S --needed --noconfirm sunshine", log)
        self.assertIn("sudo -n pacman -S --needed --noconfirm pipewire wireplumber xdg-desktop-portal xdg-desktop-portal-hyprland", log)
        self.assertIn(f"XDG_RUNTIME_DIR={runtime_dir}", log)
        self.assertIn(f"DBUS_SESSION_BUS_ADDRESS=unix:path={runtime_dir / 'bus'}", log)
        self.assertIn(f"Auto-detected XDG_RUNTIME_DIR: {runtime_dir}", result.stdout)
        self.assertIn(f"Auto-detected DBUS_SESSION_BUS_ADDRESS: unix:path={runtime_dir / 'bus'}", result.stdout)
        self.assertIn("systemctl --user restart xdg-desktop-portal-hyprland.service", log)
        self.assertIn("systemctl --user is-active --quiet xdg-desktop-portal-hyprland.service", log)
        self.assertIn("systemctl --user enable --now app-dev.lizardbyte.app.Sunshine.service", log)
        self.assertIn("Moonlight", result.stdout)
        self.assertIn("47990", result.stdout)
        self.assertIn("Remote access status: READY", result.stdout)
        self.assertIn("Tailscale-only remote access was verified", result.stdout)

    def test_sunshine_installer_writes_csrf_allowed_origins_from_tailscale_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            home = root / "home"
            calls = root / "calls.log"
            config = home / ".config" / "sunshine" / "sunshine.conf"
            bin_dir.mkdir()
            home.mkdir()
            self._write_sunshine_ready_mocks(bin_dir, calls, "100.66.222.119")
            self._write_mock(
                bin_dir / "tailscale",
                """#!/bin/bash
if [ "$1" = "ip" ] && [ "$2" = "-4" ]; then printf '100.66.222.119\n'; exit 0; fi
if [ "$1" = "status" ] && [ "$2" = "--json" ]; then
  printf '{"Self":{"HostName":"vmi3058231","DNSName":"vmi3058231.tailnet.ts.net."}}\n'
  exit 0
fi
exit 0
""",
            )
            env = {"PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin", "HOME": str(home), "USER": "tester"}

            result = subprocess.run(["/bin/bash", str(SUNSHINE_INSTALLER)], env=env, text=True, capture_output=True)
            source = config.read_text(encoding="utf-8")
            config_mode = config.stat().st_mode & 0o777
            config_dir_mode = config.parent.stat().st_mode & 0o777

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("csrf_allowed_origins = ", source)
        self.assertIn("https://arch:47990", source)
        self.assertIn("https://100.66.222.119:47990", source)
        self.assertIn("https://vmi3058231:47990", source)
        self.assertIn("https://vmi3058231.tailnet.ts.net:47990", source)
        self.assertEqual(config_mode, 0o600)
        self.assertEqual(config_dir_mode, 0o700)
        self.assertIn("Configured Sunshine CSRF allowed origins", result.stdout)

    def test_sunshine_installer_preserves_safe_existing_csrf_origins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            home = root / "home"
            calls = root / "calls.log"
            config_dir = home / ".config" / "sunshine"
            config = config_dir / "sunshine.conf"
            bin_dir.mkdir()
            config_dir.mkdir(parents=True)
            config.write_text(
                "origin_web_ui_allowed = lan\n"
                "csrf_allowed_origins = https://localhost:47990, https://arch:47990\n",
                encoding="utf-8",
            )
            self._write_sunshine_ready_mocks(bin_dir, calls, "100.66.222.119")
            self._write_mock(
                bin_dir / "tailscale",
                """#!/bin/bash
if [ "$1" = "ip" ] && [ "$2" = "-4" ]; then printf '100.66.222.119\n'; exit 0; fi
if [ "$1" = "status" ] && [ "$2" = "--json" ]; then printf '{"Self":{"HostName":"arch"}}\n'; exit 0; fi
exit 0
""",
            )
            env = {"PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin", "HOME": str(home), "USER": "tester"}

            result = subprocess.run(["/bin/bash", str(SUNSHINE_INSTALLER)], env=env, text=True, capture_output=True)
            source = config.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("origin_web_ui_allowed = lan", source)
        self.assertNotIn("origin_web_ui_allowed = wan", source)
        self.assertEqual(source.count("https://localhost:47990"), 1)
        self.assertEqual(source.count("https://arch:47990"), 1)
        self.assertEqual(source.count("https://100.66.222.119:47990"), 1)
        self.assertEqual(source.count("csrf_allowed_origins = "), 1)

    def test_sunshine_installer_drops_unsafe_existing_csrf_origins_with_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            home = root / "home"
            calls = root / "calls.log"
            config_dir = home / ".config" / "sunshine"
            config = config_dir / "sunshine.conf"
            bin_dir.mkdir()
            config_dir.mkdir(parents=True)
            config.write_text(
                "csrf_allowed_origins = https://foreign.example:47990, https://*.example:47990\n"
                "csrf_allowed_origins = http://localhost:47990, https://arch:47990\n",
                encoding="utf-8",
            )
            self._write_sunshine_ready_mocks(bin_dir, calls, "100.66.222.119")
            self._write_mock(
                bin_dir / "tailscale",
                """#!/bin/bash
if [ "$1" = "ip" ] && [ "$2" = "-4" ]; then printf '100.66.222.119\n'; exit 0; fi
if [ "$1" = "status" ] && [ "$2" = "--json" ]; then printf '{"Self":{"HostName":"arch"}}\n'; exit 0; fi
exit 0
""",
            )
            env = {"PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin", "HOME": str(home), "USER": "tester"}

            result = subprocess.run(["/bin/bash", str(SUNSHINE_INSTALLER)], env=env, text=True, capture_output=True)
            source = config.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("https://foreign.example:47990", source)
        self.assertNotIn("https://*.example:47990", source)
        self.assertNotIn("http://localhost:47990", source)
        self.assertEqual(source.count("https://arch:47990"), 1)
        self.assertIn("Dropping unsafe or malformed Sunshine csrf_allowed_origins entry: https://foreign.example:47990", result.stdout)
        self.assertIn("Dropping unsafe or malformed Sunshine csrf_allowed_origins entry: https://*.example:47990", result.stdout)
        self.assertIn("Dropping unsafe or malformed Sunshine csrf_allowed_origins entry: http://localhost:47990", result.stdout)

    def test_sunshine_installer_deduplicates_existing_csrf_origins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            home = root / "home"
            calls = root / "calls.log"
            config_dir = home / ".config" / "sunshine"
            config = config_dir / "sunshine.conf"
            bin_dir.mkdir()
            config_dir.mkdir(parents=True)
            config.write_text(
                "csrf_allowed_origins = https://localhost:47990, https://localhost:47990\n"
                "csrf_allowed_origins = https://100.66.222.119:47990\n",
                encoding="utf-8",
            )
            self._write_sunshine_ready_mocks(bin_dir, calls, "100.66.222.119")
            self._write_mock(
                bin_dir / "tailscale",
                """#!/bin/bash
if [ "$1" = "ip" ] && [ "$2" = "-4" ]; then printf '100.66.222.119\n'; exit 0; fi
if [ "$1" = "status" ] && [ "$2" = "--json" ]; then printf '{"Self":{"HostName":"arch"}}\n'; exit 0; fi
exit 0
""",
            )
            env = {"PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin", "HOME": str(home), "USER": "tester"}

            result = subprocess.run(["/bin/bash", str(SUNSHINE_INSTALLER)], env=env, text=True, capture_output=True)
            source = config.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(source.count("https://localhost:47990"), 1)
        self.assertEqual(source.count("https://100.66.222.119:47990"), 1)
        self.assertEqual(source.count("https://arch:47990"), 1)
        self.assertEqual(source.count("csrf_allowed_origins = "), 1)

    def test_sunshine_installer_continues_with_arch_csrf_origin_without_tailscale_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            home = root / "home"
            calls = root / "calls.log"
            config = home / ".config" / "sunshine" / "sunshine.conf"
            bin_dir.mkdir()
            home.mkdir()
            self._write_core_command_wrappers_without_tailscale(bin_dir)
            self._write_sunshine_ready_mocks(bin_dir, calls, "100.66.222.119")
            self._write_mock(bin_dir / "ss", "#!/bin/bash\nprintf 'LISTEN 0 4096 100.66.222.119:47990 0.0.0.0:*\n'\n")
            env = {"PATH": str(bin_dir), "HOME": str(home), "USER": "tester"}

            result = subprocess.run(["/bin/bash", str(SUNSHINE_INSTALLER)], env=env, text=True, capture_output=True)
            source = config.read_text(encoding="utf-8")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("csrf_allowed_origins = https://arch:47990", source)
        self.assertNotIn("Missing required command: tailscale", result.stderr)
        self.assertIn("Sunshine listeners exist, but Tailscale IP could not be detected", result.stdout)

    def test_sunshine_installer_auto_exports_user_bus_from_runtime_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            runtime_root = bin_dir / "run-user"
            runtime_dir = runtime_root / "1000"
            calls = bin_dir / "calls.log"
            runtime_dir.mkdir(parents=True)
            (runtime_dir / "bus").touch()
            self._write_mock(bin_dir / "id", "#!/bin/bash\nif [ \"$1\" = \"-u\" ]; then printf '1000\\n'; else /usr/bin/id \"$@\"; fi\n")
            self._write_mock(bin_dir / "yay", f"#!/bin/bash\necho yay $@ >> {calls}\nexit 0\n")
            self._write_mock(bin_dir / "sudo", f"#!/bin/bash\necho sudo $@ >> {calls}\nexit 0\n")
            self._write_mock(bin_dir / "pacman", "#!/bin/bash\nexit 0\n")
            self._write_mock(
                bin_dir / "systemctl",
                f"#!/bin/bash\necho systemctl $@ XDG_RUNTIME_DIR=${{XDG_RUNTIME_DIR:-}} DBUS_SESSION_BUS_ADDRESS=${{DBUS_SESSION_BUS_ADDRESS:-}} >> {calls}\nif [ \"$1\" = \"--user\" ] && [ \"$2\" = \"show-environment\" ]; then exit 1; fi\nexit 0\n",
            )
            env = {"PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin", "USER": "tester", "SUNSHINE_RUNTIME_ROOT": str(runtime_root)}

            result = subprocess.run(["/bin/bash", str(SUNSHINE_INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"Auto-detected XDG_RUNTIME_DIR: {runtime_dir}", result.stdout)
        self.assertIn(f"Auto-detected DBUS_SESSION_BUS_ADDRESS: unix:path={runtime_dir / 'bus'}", result.stdout)
        self.assertIn(f"XDG_RUNTIME_DIR={runtime_dir}", log)
        self.assertIn(f"DBUS_SESSION_BUS_ADDRESS=unix:path={runtime_dir / 'bus'}", log)
        self.assertIn("User systemd bus is not available", result.stdout)

    def test_sunshine_installer_uses_sudo_user_uid_for_user_bus_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            runtime_root = bin_dir / "run-user"
            desktop_runtime_dir = runtime_root / "1000"
            root_runtime_dir = runtime_root / "0"
            calls = bin_dir / "calls.log"
            desktop_runtime_dir.mkdir(parents=True)
            root_runtime_dir.mkdir(parents=True)
            (desktop_runtime_dir / "bus").touch()
            (root_runtime_dir / "bus").touch()
            self._write_mock(
                bin_dir / "id",
                f"""#!/bin/bash
echo id $@ >> {calls}
if [ "$1" = "-u" ] && [ "$2" = "santiago" ]; then printf '1000\n'; exit 0; fi
if [ "$1" = "-u" ]; then printf '0\n'; exit 0; fi
/usr/bin/id "$@"
""",
            )
            self._write_mock(bin_dir / "yay", f"#!/bin/bash\necho yay $@ >> {calls}\nexit 0\n")
            self._write_mock(bin_dir / "sudo", f"#!/bin/bash\necho sudo $@ >> {calls}\nexit 0\n")
            self._write_mock(bin_dir / "pacman", "#!/bin/bash\nexit 0\n")
            self._write_mock(
                bin_dir / "systemctl",
                f"#!/bin/bash\necho systemctl $@ XDG_RUNTIME_DIR=${{XDG_RUNTIME_DIR:-}} DBUS_SESSION_BUS_ADDRESS=${{DBUS_SESSION_BUS_ADDRESS:-}} >> {calls}\nif [ \"$1\" = \"--user\" ] && [ \"$2\" = \"show-environment\" ]; then exit 1; fi\nexit 0\n",
            )
            env = {
                "PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin",
                "SUDO_USER": "santiago",
                "USER": "root",
                "SUNSHINE_RUNTIME_ROOT": str(runtime_root),
            }

            result = subprocess.run(["/bin/bash", str(SUNSHINE_INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("id -u santiago", log)
        self.assertIn(f"Auto-detected XDG_RUNTIME_DIR: {desktop_runtime_dir}", result.stdout)
        self.assertIn(f"Auto-detected DBUS_SESSION_BUS_ADDRESS: unix:path={desktop_runtime_dir / 'bus'}", result.stdout)
        self.assertIn("Target user: santiago", result.stdout)
        self.assertIn("Target UID: 1000", result.stdout)
        self.assertIn(f"XDG_RUNTIME_DIR={desktop_runtime_dir}", log)
        self.assertIn(f"DBUS_SESSION_BUS_ADDRESS=unix:path={desktop_runtime_dir / 'bus'}", log)
        self.assertNotIn(f"XDG_RUNTIME_DIR={root_runtime_dir}", log)
        self.assertNotIn(f"DBUS_SESSION_BUS_ADDRESS=unix:path={root_runtime_dir / 'bus'}", log)
        self.assertNotIn(f"Auto-detected XDG_RUNTIME_DIR: {root_runtime_dir}", result.stdout)

    def test_sunshine_installer_stays_not_ready_when_user_bus_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            runtime_root = bin_dir / "run-user"
            runtime_dir = runtime_root / "1000"
            calls = bin_dir / "calls.log"
            runtime_dir.mkdir(parents=True)
            self._write_mock(bin_dir / "id", "#!/bin/bash\nif [ \"$1\" = \"-u\" ]; then printf '1000\\n'; else /usr/bin/id \"$@\"; fi\n")
            self._write_mock(bin_dir / "yay", f"#!/bin/bash\necho yay $@ >> {calls}\nexit 0\n")
            self._write_mock(bin_dir / "sudo", f"#!/bin/bash\necho sudo $@ >> {calls}\nexit 0\n")
            self._write_mock(bin_dir / "pacman", "#!/bin/bash\nexit 0\n")
            self._write_mock(
                bin_dir / "systemctl",
                f"#!/bin/bash\necho systemctl $@ XDG_RUNTIME_DIR=${{XDG_RUNTIME_DIR:-}} DBUS_SESSION_BUS_ADDRESS=${{DBUS_SESSION_BUS_ADDRESS:-}} >> {calls}\nif [ \"$1\" = \"--user\" ] && [ \"$2\" = \"show-environment\" ]; then exit 1; fi\nexit 0\n",
            )
            env = {"PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin", "USER": "tester", "SUNSHINE_RUNTIME_ROOT": str(runtime_root)}

            result = subprocess.run(["/bin/bash", str(SUNSHINE_INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"Auto-detected XDG_RUNTIME_DIR: {runtime_dir}", result.stdout)
        self.assertIn(f"user bus socket was not found: {runtime_dir / 'bus'}", result.stdout)
        self.assertIn(f"XDG_RUNTIME_DIR={runtime_dir}", log)
        self.assertIn("DBUS_SESSION_BUS_ADDRESS=", log)
        self.assertIn("User systemd bus is not available", result.stdout)
        self.assertIn("Remote access status: NOT READY", result.stdout)
        self.assertIn("auto-detects the desktop user's /run/user/<uid>/bus", result.stdout)
        self.assertIn("Remote access verification failed", result.stderr)
        self.assertNotIn("systemctl --user enable --now app-dev.lizardbyte.app.Sunshine.service", log)

    def test_sunshine_installer_marks_not_ready_when_hyprland_portal_is_inactive(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            calls = bin_dir / "calls.log"
            self._write_mock(bin_dir / "yay", f"#!/bin/bash\necho yay $@ >> {calls}\nexit 0\n")
            self._write_mock(bin_dir / "sudo", f"#!/bin/bash\necho sudo $@ >> {calls}\nexit 0\n")
            self._write_mock(bin_dir / "pacman", "#!/bin/bash\nexit 0\n")
            self._write_mock(
                bin_dir / "systemctl",
                f"""#!/bin/bash
echo systemctl $@ >> {calls}
if [ "$1" = "--user" ] && [ "$2" = "show-environment" ]; then exit 0; fi
if [ "$1" = "--user" ] && [ "$2" = "restart" ] && [ "$3" = "xdg-desktop-portal-hyprland.service" ]; then exit 0; fi
if [ "$1" = "--user" ] && [ "$2" = "is-active" ] && [ "$3" = "--quiet" ]; then exit 3; fi
if [ "$1" = "--user" ] && [ "$2" = "is-active" ] && [ "$3" = "xdg-desktop-portal-hyprland.service" ]; then printf 'inactive\n'; exit 3; fi
if [ "$1" = "--user" ] && [ "$2" = "status" ] && [ "$3" = "xdg-desktop-portal-hyprland.service" ]; then printf 'Active: inactive (dead)\n'; exit 3; fi
exit 0
""",
            )
            env = {"PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin", "USER": "tester"}

            result = subprocess.run(["/bin/bash", str(SUNSHINE_INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("systemctl --user restart xdg-desktop-portal-hyprland.service", log)
        self.assertIn("systemctl --user is-active --quiet xdg-desktop-portal-hyprland.service", log)
        self.assertNotIn("systemctl --user enable --now app-dev.lizardbyte.app.Sunshine.service", log)
        self.assertIn("Hyprland portal is not active", result.stdout)
        self.assertIn("Remote access status: NOT READY", result.stdout)
        self.assertIn("xdg-desktop-portal-hyprland.service", result.stdout)
        self.assertIn("journalctl --user -u xdg-desktop-portal-hyprland.service", result.stdout)
        self.assertIn("Active: inactive (dead)", result.stdout)
        self.assertIn("Remote access verification failed", result.stderr)

    def test_sunshine_installer_fails_when_listener_is_not_tailscale_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            calls = bin_dir / "calls.log"
            self._write_mock(bin_dir / "yay", f"#!/bin/bash\necho yay $@ >> {calls}\nexit 0\n")
            self._write_mock(bin_dir / "sudo", f"#!/bin/bash\necho sudo $@ >> {calls}\nexit 0\n")
            self._write_mock(bin_dir / "pacman", "#!/bin/bash\nexit 0\n")
            self._write_mock(
                bin_dir / "systemctl",
                f"#!/bin/bash\necho systemctl $@ >> {calls}\nif [ \"$1\" = \"--user\" ] && [ \"$2\" = \"cat\" ] && [ \"$3\" = \"app-dev.lizardbyte.app.Sunshine.service\" ]; then exit 0; fi\nexit 0\n",
            )
            self._write_mock(bin_dir / "ss", "#!/bin/bash\nprintf 'LISTEN 0 4096 0.0.0.0:47990 0.0.0.0:*\n'\n")
            self._write_mock(bin_dir / "tailscale", "#!/bin/bash\nif [ \"$1\" = \"ip\" ] && [ \"$2\" = \"-4\" ]; then printf '100.88.77.66\n'; fi\n")
            env = {"PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin", "USER": "tester"}

            result = subprocess.run(["/bin/bash", str(SUNSHINE_INSTALLER)], env=env, text=True, capture_output=True)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not bound to the Tailscale IP only", result.stdout)
        self.assertIn("Remote access status: NOT READY", result.stdout)
        self.assertIn("0.0.0.0:47990", result.stdout)
        self.assertIn("Sunshine installed, but remote access is NOT READY/VERIFIED", result.stdout)
        self.assertIn("Remote access verification failed", result.stderr)
        self.assertIn("install completed, but remote access is not verified/safe yet", result.stderr)

    def test_sunshine_installer_prints_listener_diagnostics_when_ports_are_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            calls = bin_dir / "calls.log"
            self._write_mock(bin_dir / "yay", f"#!/bin/bash\necho yay $@ >> {calls}\nexit 0\n")
            self._write_mock(bin_dir / "sudo", f"#!/bin/bash\necho sudo $@ >> {calls}\nexit 0\n")
            self._write_mock(bin_dir / "pacman", "#!/bin/bash\nexit 0\n")
            self._write_mock(
                bin_dir / "systemctl",
                f"#!/bin/bash\necho systemctl $@ >> {calls}\nif [ \"$1\" = \"--user\" ] && [ \"$2\" = \"cat\" ] && [ \"$3\" = \"app-dev.lizardbyte.app.Sunshine.service\" ]; then exit 0; fi\nexit 0\n",
            )
            self._write_mock(bin_dir / "ss", "#!/bin/bash\nexit 0\n")
            env = {"PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin", "USER": "tester"}

            result = subprocess.run(["/bin/bash", str(SUNSHINE_INSTALLER)], env=env, text=True, capture_output=True)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no TCP listener was found", result.stdout)
        self.assertIn("Remote access status: NOT READY", result.stdout)
        self.assertIn("journalctl --user -u app-dev.lizardbyte.app.Sunshine.service", result.stdout)
        self.assertIn("Sunshine installed, but remote access is NOT READY/VERIFIED", result.stdout)
        self.assertIn("Remote access verification failed", result.stderr)
        self.assertIn("install completed, but remote access is not verified/safe yet", result.stderr)

    def test_wayvnc_installer_uses_pacman_through_sudo(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            calls = bin_dir / "calls.log"
            self._write_mock(bin_dir / "sudo", f"#!/bin/bash\necho sudo $@ >> {calls}\nexit 0\n")
            self._write_mock(bin_dir / "pacman", "#!/bin/bash\nexit 0\n")
            env = {"PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin"}

            result = subprocess.run(["/bin/bash", str(WAYVNC_INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("sudo pacman -S --needed --noconfirm wayvnc", log)
        self.assertIn("Tailscale", result.stdout)
        self.assertIn("fallback", result.stdout)
        self.assertIn("wayvnc --keyboard=us <tailscale-ip>:5900", result.stdout)
        self.assertNotIn("wayvnc --keyboard=us <tailscale-ip> 5900", result.stdout)
        self.assertIn("XDG_RUNTIME_DIR", result.stdout)
        self.assertIn("WAYLAND_DISPLAY", result.stdout)
        self.assertIn("nano", result.stdout)
        self.assertIn("Ghostty", result.stdout)

    def test_remote_desktop_docs_use_wayvnc_address_port_and_exposure_warning(self):
        readme = README.read_text(encoding="utf-8")

        self.assertIn("wayvnc --keyboard=us <tailscale-ip>:5900", readme)
        self.assertNotIn("wayvnc --keyboard=us <tailscale-ip> 5900", readme)
        self.assertIn("Do not treat Sunshine as remotely usable until listeners exist and are private to Tailscale", readme)

    @staticmethod
    def _write_mock(path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)

    def _write_sunshine_ready_mocks(self, bin_dir: Path, calls: Path, tailscale_ip: str) -> None:
        self._write_mock(bin_dir / "id", "#!/bin/bash\nif [ \"$1\" = \"-u\" ]; then printf '1000\\n'; else /usr/bin/id \"$@\"; fi\n")
        self._write_mock(bin_dir / "yay", f"#!/bin/bash\necho yay $@ >> {calls}\nexit 0\n")
        self._write_mock(bin_dir / "sudo", f"#!/bin/bash\necho sudo $@ >> {calls}\nexit 0\n")
        self._write_mock(bin_dir / "pacman", "#!/bin/bash\nexit 0\n")
        self._write_mock(bin_dir / "loginctl", f"#!/bin/bash\necho loginctl $@ >> {calls}\nexit 0\n")
        self._write_mock(
            bin_dir / "systemctl",
            f"#!/bin/bash\necho systemctl $@ >> {calls}\nif [ \"$1\" = \"--user\" ] && [ \"$2\" = \"cat\" ] && [ \"$3\" = \"app-dev.lizardbyte.app.Sunshine.service\" ]; then exit 0; fi\nexit 0\n",
        )
        self._write_mock(bin_dir / "ss", f"#!/bin/bash\nprintf 'LISTEN 0 4096 {tailscale_ip}:47990 0.0.0.0:*\n'\n")

    def _write_core_command_wrappers_without_tailscale(self, bin_dir: Path) -> None:
        for command, target in {
            "awk": "/usr/bin/awk",
            "grep": "/usr/bin/grep",
            "dirname": "/usr/bin/dirname",
            "mkdir": "/bin/mkdir",
            "chmod": "/bin/chmod",
            "mv": "/bin/mv",
        }.items():
            self._write_mock(bin_dir / command, f"#!/bin/bash\nexec {target} \"$@\"\n")


if __name__ == "__main__":
    unittest.main()
