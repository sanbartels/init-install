import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
YAY_INSTALLER = ROOT / "yay_install" / "install_yay_packages.sh"


class YayInstallerBehaviorTests(unittest.TestCase):
    def test_yay_installer_preinstalls_build_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            calls = bin_dir / "calls.log"
            self._write_mock(bin_dir / "sudo", f"#!/bin/bash\necho sudo $@ >> {calls}\nexit 0\n")
            self._write_mock(bin_dir / "git", f"#!/bin/bash\necho git $@ >> {calls}\nmkdir -p \"$3\"\nexit 0\n")
            self._write_mock(bin_dir / "makepkg", f"#!/bin/bash\necho makepkg $@ >> {calls}\nexit 0\n")
            self._write_mock(bin_dir / "mktemp", "#!/bin/bash\necho /tmp/init-install-yay-test\n")
            self._write_mock(bin_dir / "rm", "#!/bin/bash\nexit 0\n")
            env = {"PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin", "SUDO_KEEPALIVE_INTERVAL": "1"}

            result = subprocess.run(["/bin/bash", str(YAY_INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("sudo pacman -S --needed --noconfirm base-devel git go", log)
        self.assertIn("git clone https://aur.archlinux.org/yay.git", log)
        self.assertIn("makepkg -si --noconfirm", log)

    @staticmethod
    def _write_mock(path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)


if __name__ == "__main__":
    unittest.main()
