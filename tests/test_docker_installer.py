import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "docker" / "install_docker.sh"


class DockerInstallerTests(unittest.TestCase):
    def test_docker_installer_does_not_fail_when_service_start_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            calls = bin_dir / "calls.log"
            self._write_mock(bin_dir / "sudo", f"#!/bin/bash\necho sudo $@ >> {calls}\nif [ \"$1\" = systemctl ]; then exit 1; fi\nexit 0\n")
            self._write_mock(bin_dir / "pacman", "#!/bin/bash\nexit 0\n")
            self._write_mock(bin_dir / "getent", "#!/bin/bash\nexit 1\n")
            env = {"PATH": str(bin_dir), "SUDO_USER": "santiago", "USER": "santiago"}

            result = subprocess.run(["/bin/bash", str(INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("sudo pacman -S --needed --noconfirm docker docker-compose", log)
        self.assertIn("sudo systemctl enable --now docker.service", log)
        self.assertIn("sudo usermod -aG docker santiago", log)
        self.assertIn("docker.service no pudo arrancar", result.stdout)

    @staticmethod
    def _write_mock(path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)


if __name__ == "__main__":
    unittest.main()
