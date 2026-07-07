import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import install


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "go_rust_tools" / "install_go_rust_tools.sh"


class GoRustToolsInstallerTests(unittest.TestCase):
    def test_go_rust_menu_uses_dedicated_installer(self):
        categories = {category.key: category for category in install.SOFTWARE_SECTION.categories}

        self.assertIn("go_rust_tools", categories)
        self.assertEqual(categories["go_rust_tools"].scripts, install.scripts("go_rust_tools/install_go_rust_tools.sh"))
        self.assertIsNone(categories["go_rust_tools"].internal_runner)

    def test_installs_go_and_rustup_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            calls = bin_dir / "calls.log"
            self._write_mock(bin_dir / "sudo", f"#!/bin/bash\necho sudo $@ >> {calls}\nexit 0\n")
            self._write_mock(bin_dir / "pacman", "#!/bin/bash\nexit 0\n")
            env = {"PATH": str(bin_dir)}

            result = subprocess.run(["/bin/bash", str(INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("sudo pacman -S --needed --noconfirm go", log)
        self.assertIn("sudo pacman -S --needed --noconfirm rustup", log)

    def test_skips_rustup_when_rust_is_already_installed_without_rustup(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            calls = bin_dir / "calls.log"
            self._write_mock(bin_dir / "go", "#!/bin/bash\necho go version go1.25 linux/amd64\n")
            self._write_mock(bin_dir / "rustc", "#!/bin/bash\necho rustc 1.90.0\n")
            self._write_mock(bin_dir / "sudo", f"#!/bin/bash\necho sudo $@ >> {calls}\nexit 0\n")
            self._write_mock(bin_dir / "pacman", "#!/bin/bash\nexit 0\n")
            env = {"PATH": str(bin_dir)}

            result = subprocess.run(["/bin/bash", str(INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8") if calls.exists() else ""

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Go ya está instalado", result.stdout)
        self.assertIn("Rust/Cargo ya está instalado sin rustup", result.stdout)
        self.assertNotIn("rustup", log)

    def test_configures_stable_toolchain_when_rustup_has_no_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            calls = bin_dir / "calls.log"
            self._write_mock(bin_dir / "go", "#!/bin/bash\necho go version go1.25 linux/amd64\n")
            self._write_mock(
                bin_dir / "rustup",
                f"#!/bin/bash\necho rustup $@ >> {calls}\nif [ \"$1\" = default ] && [ $# -eq 1 ]; then echo 'no default toolchain configured'; fi\nexit 0\n",
            )
            self._write_mock(bin_dir / "sudo", "#!/bin/bash\nexit 0\n")
            self._write_mock(bin_dir / "pacman", "#!/bin/bash\nexit 0\n")
            env = {"PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin"}

            result = subprocess.run(["/bin/bash", str(INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("rustup default stable", log)

    @staticmethod
    def _write_mock(path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)


if __name__ == "__main__":
    unittest.main()
