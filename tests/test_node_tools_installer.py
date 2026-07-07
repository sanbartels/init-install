import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import install


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "node_tools" / "install_node_tools.sh"
BASE_INSTALLER = ROOT / "system_base" / "install_base.sh"


class NodeToolsInstallerTests(unittest.TestCase):
    def test_node_tools_menu_uses_dedicated_installer(self):
        categories = {category.key: category for category in install.SOFTWARE_SECTION.categories}

        self.assertIn("node_tools", categories)
        self.assertEqual(categories["node_tools"].scripts, install.scripts("node_tools/install_node_tools.sh"))
        self.assertIsNone(categories["node_tools"].internal_runner)

    def test_installs_lts_when_node_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            calls = bin_dir / "calls.log"
            self._write_mock(bin_dir / "sudo", f"#!/bin/bash\necho sudo $@ >> {calls}\nexit 0\n")
            self._write_mock(bin_dir / "pacman", "#!/bin/bash\nexit 0\n")
            env = {"PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin"}

            result = subprocess.run(["/bin/bash", str(INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("nodejs-lts-krypton npm pnpm yarn", log)

    def test_skips_lts_when_node_is_already_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            calls = bin_dir / "calls.log"
            self._write_mock(bin_dir / "node", "#!/bin/bash\necho v26.4.0\n")
            self._write_mock(bin_dir / "sudo", f"#!/bin/bash\necho sudo $@ >> {calls}\nexit 0\n")
            self._write_mock(bin_dir / "pacman", "#!/bin/bash\nexit 0\n")
            env = {"PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin"}

            result = subprocess.run(["/bin/bash", str(INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Node.js ya está instalado", result.stdout)
        self.assertIn("sudo pacman -S --needed --noconfirm npm pnpm yarn", log)
        self.assertNotIn("nodejs-lts-krypton", log)

    def test_base_and_terminal_tools_include_less_for_git_pager(self):
        install_py = (ROOT / "install.py").read_text(encoding="utf-8")
        base_script = BASE_INSTALLER.read_text(encoding="utf-8")

        self.assertIn('"less"', install_py)
        self.assertIn("less \\", base_script)

    @staticmethod
    def _write_mock(path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)


if __name__ == "__main__":
    unittest.main()
