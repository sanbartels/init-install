import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "ssh" / "install_ssh.sh"


class SshInstallerTests(unittest.TestCase):
    def test_ssh_installer_enables_starts_and_verifies_sshd(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            calls = bin_dir / "calls.log"
            self._write_mock(bin_dir / "sudo", f"#!/bin/bash\necho sudo $@ >> {calls}\n\"$@\"\n")
            self._write_mock(bin_dir / "pacman", f"#!/bin/bash\necho pacman $@ >> {calls}\nexit 0\n")
            self._write_mock(bin_dir / "systemctl", f"#!/bin/bash\necho systemctl $@ >> {calls}\nexit 0\n")
            self._write_mock(bin_dir / "ss", "#!/bin/bash\nprintf 'LISTEN 0 128 0.0.0.0:22 0.0.0.0:*\n'\n")
            env = {"PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin"}

            result = subprocess.run(["/bin/bash", str(INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("sudo pacman -S --needed --noconfirm openssh", log)
        self.assertIn("sudo systemctl enable --now sshd.service", log)
        self.assertIn("systemctl is-active --quiet sshd.service", log)
        self.assertIn("SSH is listening on port 22", result.stdout)
        self.assertIn("SSH hardening next steps", result.stdout)
        self.assertIn("PasswordAuthentication no", result.stdout)
        self.assertIn("PermitRootLogin no", result.stdout)

    def test_ssh_installer_fails_when_sshd_is_not_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            calls = bin_dir / "calls.log"
            self._write_mock(bin_dir / "sudo", f"#!/bin/bash\necho sudo $@ >> {calls}\n\"$@\"\n")
            self._write_mock(bin_dir / "pacman", f"#!/bin/bash\necho pacman $@ >> {calls}\nexit 0\n")
            self._write_mock(
                bin_dir / "systemctl",
                f"#!/bin/bash\necho systemctl $@ >> {calls}\nif [ \"$1\" = \"is-active\" ]; then exit 3; fi\nexit 0\n",
            )
            self._write_mock(bin_dir / "ss", "#!/bin/bash\nprintf 'LISTEN 0 128 0.0.0.0:22 0.0.0.0:*\n'\n")
            env = {"PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin"}

            result = subprocess.run(["/bin/bash", str(INSTALLER)], env=env, text=True, capture_output=True)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not report it active", result.stderr)
        self.assertNotIn("OpenSSH installed and sshd.service configured", result.stdout)

    def test_ssh_installer_fails_when_port_22_is_not_listening(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            calls = bin_dir / "calls.log"
            self._write_mock(bin_dir / "sudo", f"#!/bin/bash\necho sudo $@ >> {calls}\n\"$@\"\n")
            self._write_mock(bin_dir / "pacman", f"#!/bin/bash\necho pacman $@ >> {calls}\nexit 0\n")
            self._write_mock(bin_dir / "systemctl", f"#!/bin/bash\necho systemctl $@ >> {calls}\nexit 0\n")
            self._write_mock(bin_dir / "ss", "#!/bin/bash\nexit 0\n")
            env = {"PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin"}

            result = subprocess.run(["/bin/bash", str(INSTALLER)], env=env, text=True, capture_output=True)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Port 22 was not found", result.stderr)
        self.assertNotIn("OpenSSH installed and sshd.service configured", result.stdout)

    @staticmethod
    def _write_mock(path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)


if __name__ == "__main__":
    unittest.main()
