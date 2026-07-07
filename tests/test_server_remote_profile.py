import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import install


ROOT = Path(__file__).resolve().parents[1]
TAILSCALE_INSTALLER = ROOT / "tailscale" / "install_tailscale.sh"


class TailscaleBaseInstallTests(unittest.TestCase):
    def test_tailscale_is_a_base_install_option_not_a_separate_profile(self):
        main_action_keys = [action.key for action in install.MAIN_ACTIONS]
        base_categories = {category.key: category for category in install.BASE_SECTION.categories}

        self.assertNotIn("server_remote", main_action_keys)
        self.assertIn("tailscale", base_categories)
        self.assertEqual(base_categories["tailscale"].scripts, install.scripts("tailscale/install_tailscale.sh"))
        self.assertTrue(base_categories["tailscale"].install_detector is not None)

    def test_tailscale_installer_fails_fast_without_sudo(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"PATH": tmp}
            result = subprocess.run(["/bin/bash", str(TAILSCALE_INSTALLER)], env=env, text=True, capture_output=True)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("falta sudo", result.stderr)

    def test_tailscale_installer_installs_package_and_enables_service(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            calls = bin_dir / "calls.log"
            self._write_mock(bin_dir / "sudo", f"#!/bin/bash\necho sudo $@ >> {calls}\nexit 0\n")
            self._write_mock(bin_dir / "pacman", "#!/bin/bash\nexit 0\n")
            env = {"PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin"}

            result = subprocess.run(["/bin/bash", str(TAILSCALE_INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("sudo pacman -S --needed --noconfirm tailscale", log)
        self.assertIn("sudo systemctl enable --now tailscaled.service", log)
        self.assertIn("sudo tailscale up --ssh", result.stdout)
        self.assertNotIn("tailscale up --authkey", result.stdout)

    @staticmethod
    def _write_mock(path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)


if __name__ == "__main__":
    unittest.main()
