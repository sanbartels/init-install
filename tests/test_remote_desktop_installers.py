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

    def test_sunshine_installer_uses_arch_user_unit_and_capture_stack(self):
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
            self._write_mock(bin_dir / "ss", "#!/bin/bash\nprintf 'LISTEN 0 4096 100.88.77.66:47990 0.0.0.0:*\n'\n")
            self._write_mock(bin_dir / "tailscale", "#!/bin/bash\nif [ \"$1\" = \"ip\" ] && [ \"$2\" = \"-4\" ]; then printf '100.88.77.66\n'; fi\n")
            env = {"PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin", "USER": "tester"}

            result = subprocess.run(["/bin/bash", str(SUNSHINE_INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("yay -S --needed --noconfirm sunshine", log)
        self.assertIn("sudo pacman -S --needed --noconfirm pipewire wireplumber xdg-desktop-portal xdg-desktop-portal-hyprland", log)
        self.assertIn("systemctl --user enable --now app-dev.lizardbyte.app.Sunshine.service", log)
        self.assertIn("Moonlight", result.stdout)
        self.assertIn("47990", result.stdout)
        self.assertIn("Remote access status: READY", result.stdout)
        self.assertIn("Tailscale-only remote access was verified", result.stdout)

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


if __name__ == "__main__":
    unittest.main()
