import os
import socket
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
        self.assertIn("wayvnc", categories)
        self.assertNotIn("sunshine", categories)
        self.assertEqual(categories["wayvnc"].title, "WayVNC")
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

    def test_wayvnc_installer_creates_managed_tailscale_service_and_retires_sunshine(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            home = root / "home"
            calls = root / "calls.log"
            sunshine_config = home / ".config" / "sunshine" / "sunshine.conf"
            sunshine_alias = home / ".config" / "systemd" / "user" / "sunshine.service"
            runtime_dir = root / "run-user" / "1000"
            bin_dir.mkdir()
            runtime_dir.mkdir(parents=True)
            self._create_unix_socket(runtime_dir / "wayland-1")
            sunshine_alias.parent.mkdir(parents=True)
            sunshine_config.parent.mkdir(parents=True)
            sunshine_config.write_text("credentials-preserved\n", encoding="utf-8")
            sunshine_alias.symlink_to("/usr/lib/systemd/user/app-dev.lizardbyte.app.Sunshine.service")
            self._write_wayvnc_success_mocks(bin_dir, calls, "100.88.77.66")
            env = {"PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin", "HOME": str(home), "USER": "tester", "XDG_RUNTIME_DIR": str(runtime_dir), "HYPRLAND_INSTANCE_SIGNATURE": "stale"}

            result = subprocess.run(["/bin/bash", str(WAYVNC_INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8")
            launcher = home / ".local" / "bin" / "init-install-wayvnc"
            service = home / ".config" / "systemd" / "user" / "wayvnc.service"
            launcher_source = launcher.read_text(encoding="utf-8")
            service_source = service.read_text(encoding="utf-8")
            installer_source = WAYVNC_INSTALLER.read_text(encoding="utf-8")
            sunshine_alias_exists = sunshine_alias.exists()
            sunshine_config_source = sunshine_config.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        for expected in ["sudo pacman -S --needed --noconfirm wayvnc tailscale", "sudo systemctl enable --now tailscaled.service", "systemctl --user disable --now app-dev.lizardbyte.app.Sunshine.service", "systemctl --user disable --now sunshine.service", "systemctl --user enable --now wayvnc.service"]:
            self.assertIn(expected, log)
        self.assertFalse(sunshine_alias_exists)
        self.assertEqual(sunshine_config_source, "credentials-preserved\n")
        self.assertIn("Refusing to remove unexpected sunshine.service symlink target", installer_source)
        self.assertNotIn("pacman -R", installer_source)
        self.assertNotIn("rm -rf", installer_source)
        for expected in ["hyprctl instances -j", "unset HYPRLAND_INSTANCE_SIGNATURE WAYLAND_DISPLAY", "WAYLAND_DISPLAY", "Virtual-1", "--keyboard=us", "--output=\"$output_name\"", "\"${tailscale_ip}:${bind_port}\""]:
            self.assertIn(expected, launcher_source)
        self.assertNotIn("100.66.222.119", launcher_source)
        for expected in ["ExecStart=", "init-install-wayvnc", "Restart=on-failure", "RestartSteps=5", "StartLimitBurst=6"]:
            self.assertIn(expected, service_source)

    def test_wayvnc_installer_rejects_public_or_unexpected_listener_bindings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            home = root / "home"
            calls = root / "calls.log"
            runtime_dir = root / "run-user" / "1000"
            bin_dir.mkdir()
            home.mkdir()
            runtime_dir.mkdir(parents=True)
            self._create_unix_socket(runtime_dir / "wayland-1")
            self._write_wayvnc_success_mocks(bin_dir, calls, "100.88.77.66", listener="0.0.0.0:5900")
            env = {"PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin", "HOME": str(home), "USER": "tester", "XDG_RUNTIME_DIR": str(runtime_dir)}

            result = subprocess.run(["/bin/bash", str(WAYVNC_INSTALLER)], env=env, text=True, capture_output=True)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("listener is not owned by expected PID 4242 on the current Tailscale IPv4 only", result.stderr)
        self.assertIn("0.0.0.0:5900", result.stderr)

    def test_wayvnc_installer_fails_before_retiring_sunshine_when_instance_socket_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            home = root / "home"
            calls = root / "calls.log"
            runtime_dir = root / "run-user" / "1000"
            bin_dir.mkdir()
            home.mkdir()
            runtime_dir.mkdir(parents=True)
            self._write_wayvnc_success_mocks(bin_dir, calls, "100.88.77.66")
            env = {"PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin", "HOME": str(home), "USER": "tester", "XDG_RUNTIME_DIR": str(runtime_dir), "WAYVNC_SESSION_ATTEMPTS": "1"}

            result = subprocess.run(["/bin/bash", str(WAYVNC_INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No active Hyprland instance", result.stderr)
        self.assertNotIn("disable --now app-dev.lizardbyte.app.Sunshine.service", log)

    def test_wayvnc_installer_rejects_managed_service_mainpid_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            home = root / "home"
            calls = root / "calls.log"
            runtime_dir = root / "run-user" / "1000"
            bin_dir.mkdir()
            home.mkdir()
            runtime_dir.mkdir(parents=True)
            self._create_unix_socket(runtime_dir / "wayland-1")
            self._write_wayvnc_success_mocks(bin_dir, calls, "100.88.77.66", managed_listener_pid="9999")
            env = {"PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin", "HOME": str(home), "USER": "tester", "XDG_RUNTIME_DIR": str(runtime_dir)}

            result = subprocess.run(["/bin/bash", str(WAYVNC_INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("listener is not owned by expected PID 4242", result.stderr)
        self.assertIn("systemctl --user disable --now wayvnc.service", log)
        self.assertNotIn("disable --now app-dev.lizardbyte.app.Sunshine.service", log)

    def test_wayvnc_installer_waits_for_delayed_manual_port_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            home = root / "home"
            calls = root / "calls.log"
            runtime_dir = root / "run-user" / "1000"
            bin_dir.mkdir()
            home.mkdir()
            runtime_dir.mkdir(parents=True)
            self._create_unix_socket(runtime_dir / "wayland-1")
            self._write_wayvnc_success_mocks(bin_dir, calls, "100.88.77.66", manual_release_delay_calls=4)
            env = {"PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin", "HOME": str(home), "USER": "tester", "XDG_RUNTIME_DIR": str(runtime_dir), "WAYVNC_PORT_RELEASE_TIMEOUT": "5"}

            result = subprocess.run(["/bin/bash", str(WAYVNC_INSTALLER)], env=env, text=True, capture_output=True)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Stopping current user's manual WayVNC listener on port 5900", result.stdout)

    def test_remote_desktop_docs_lead_with_wayvnc_and_sunshine_preservation(self):
        readme = README.read_text(encoding="utf-8")

        self.assertIn("WayVNC como escritorio remoto normal sobre Tailscale", readme)
        self.assertIn("systemctl --user status wayvnc.service --no-pager", readme)
        self.assertIn("journalctl --user -u wayvnc.service -b --no-pager", readme)
        self.assertIn("WAYVNC_BIND_PORT=5900 ~/.local/bin/init-install-wayvnc", readme)
        self.assertIn("systemctl --user enable --now app-dev.lizardbyte.app.Sunshine.service", readme)
        self.assertIn("0.0.0.0:5900", readme)
        self.assertIn("It does not remove the Sunshine package", readme)
        self.assertNotIn("Sunshine para acceso remoto", readme)

    @staticmethod
    def _write_mock(path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)

    @staticmethod
    def _create_unix_socket(path: Path) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.bind(str(path))
        finally:
            sock.close()

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

    def _write_wayvnc_success_mocks(self, bin_dir: Path, calls: Path, tailscale_ip: str, listener: str | None = None, managed_listener_pid: str = "4242", manual_release_delay_calls: int = 0) -> None:
        listener = listener or f"{tailscale_ip}:5900"
        state_dir = bin_dir.parent
        probe_pid = state_dir / "probe.pid"
        managed_pid = state_dir / "managed.pid"
        ss_count = state_dir / "ss-count"
        self._write_mock(bin_dir / "sudo", f"#!/bin/bash\necho sudo $@ >> {calls}\nexit 0\n")
        self._write_mock(bin_dir / "pacman", "#!/bin/bash\nexit 0\n")
        self._write_mock(
            bin_dir / "systemctl",
            f"""#!/bin/bash
echo systemctl $@ >> {calls}
if [ "$1" = "--user" ] && [ "$2" = "show-environment" ]; then exit 0; fi
if [ "$1" = "--user" ] && [ "$2" = "show" ]; then
  if [ -f {managed_pid} ]; then cat {managed_pid}; else printf '0\n'; fi
  exit 0
fi
if [ "$1" = "--user" ] && [ "$2" = "enable" ] && [ "$3" = "--now" ] && [ "$4" = "wayvnc.service" ]; then printf '4242\n' > {managed_pid}; exit 0; fi
if [ "$1" = "--user" ] && [ "$2" = "stop" ] && [ "$3" = "wayvnc.service" ]; then rm -f {managed_pid}; exit 0; fi
if [ "$1" = "--user" ] && [ "$2" = "disable" ] && [ "$3" = "--now" ] && [ "$4" = "wayvnc.service" ]; then rm -f {managed_pid}; exit 0; fi
if [ "$1" = "--user" ] && [ "$2" = "list-unit-files" ]; then printf '%s enabled\n' "$3"; exit 0; fi
if [ "$1" = "--user" ] && [ "$2" = "status" ]; then exit 0; fi
exit 0
""",
        )
        self._write_mock(bin_dir / "tailscale", f"#!/bin/bash\nif [ \"$1\" = \"ip\" ] && [ \"$2\" = \"-4\" ]; then printf '{tailscale_ip}\\n'; fi\n")
        self._write_mock(
            bin_dir / "hyprctl",
            """#!/bin/bash
if [ "$1" = "instances" ] && [ "$2" = "-j" ]; then printf '[{"instance":"fresh-instance","wl_socket":"wayland-1"}]\n'; exit 0; fi
if [ "$1" = "monitors" ] && [ "$2" = "-j" ] && [ "${HYPRLAND_INSTANCE_SIGNATURE:-}" = "fresh-instance" ] && [ "${WAYLAND_DISPLAY:-}" = "wayland-1" ]; then printf '[{"name":"Virtual-1"}]\n'; exit 0; fi
printf '[]\n'
exit 0
""",
        )
        self._write_mock(
            bin_dir / "wayvnc",
            f"""#!/bin/bash
target="${{@: -1}}"
case "$target" in
  *:5901) printf '%s\n' "$$" > {probe_pid} ;;
esac
exec sleep 300
""",
        )
        self._write_mock(
            bin_dir / "ss",
            f"""#!/bin/bash
count=0
if [ -f {ss_count} ]; then IFS= read -r count < {ss_count}; fi
count=$((count + 1))
printf '%s\n' "$count" > {ss_count}
if [ -f {probe_pid} ]; then printf 'LISTEN 0 4096 {tailscale_ip}:5901 0.0.0.0:* users:(("wayvnc",pid=%s,fd=8))\n' "$(cat {probe_pid})"; fi
if [ ! -f {managed_pid} ] && [ "$count" -le {manual_release_delay_calls} ]; then printf 'LISTEN 0 4096 {tailscale_ip}:5900 0.0.0.0:* users:(("wayvnc",pid=777,fd=8))\n'; fi
if [ -f {managed_pid} ]; then printf 'LISTEN 0 4096 {listener} 0.0.0.0:* users:(("wayvnc",pid={managed_listener_pid},fd=8))\n'; fi
""",
        )
        self._write_mock(bin_dir / "ps", "#!/bin/bash\nif [ \"${@: -1}\" = \"777\" ]; then printf 'tester\\n'; else printf 'otheruser\\n'; fi\n")
        self._write_mock(bin_dir / "id", "#!/bin/bash\nif [ \"$1\" = \"-un\" ]; then printf 'tester\\n'; else /usr/bin/id \"$@\"; fi\n")

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
