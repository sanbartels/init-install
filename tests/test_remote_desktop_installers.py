import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import install


ROOT = Path(__file__).resolve().parents[1]
SUNSHINE_INSTALLER = ROOT / "remote_desktop" / "install_sunshine.sh"
WAYVNC_INSTALLER = ROOT / "remote_desktop" / "install_wayvnc.sh"


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
        self.assertIn("yay no está instalado", result.stderr)

    def test_sunshine_installer_uses_yay_and_tolerates_user_service_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            calls = bin_dir / "calls.log"
            self._write_mock(bin_dir / "yay", f"#!/bin/bash\necho yay $@ >> {calls}\nexit 0\n")
            self._write_mock(bin_dir / "systemctl", f"#!/bin/bash\necho systemctl $@ >> {calls}\nexit 1\n")
            env = {"PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin"}

            result = subprocess.run(["/bin/bash", str(SUNSHINE_INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("yay -S --needed --noconfirm sunshine", log)
        self.assertIn("systemctl --user enable --now sunshine.service", log)
        self.assertIn("No se pudo iniciar sunshine.service", result.stdout)
        self.assertIn("Moonlight", result.stdout)
        self.assertIn("47990", result.stdout)

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

    @staticmethod
    def _write_mock(path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)


if __name__ == "__main__":
    unittest.main()
