import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "claude_code" / "install_claude_code.sh"
INSTALL_PY = ROOT / "install.py"


class ClaudeCodeInstallerTests(unittest.TestCase):
    def test_claude_installer_accepts_local_bin_before_path_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            bin_dir = Path(tmp) / "bin"
            calls = Path(tmp) / "calls.log"
            home.mkdir()
            bin_dir.mkdir()
            (home / ".bashrc").write_text("", encoding="utf-8")
            (home / ".zshrc").write_text("", encoding="utf-8")

            self._write_mock(
                bin_dir / "curl",
                "#!/bin/bash\n"
                "cat <<'SCRIPT'\n"
                "#!/bin/bash\n"
                "mkdir -p \"$HOME/.local/bin\"\n"
                "cat > \"$HOME/.local/bin/claude\" <<'CLAUDE'\n"
                "#!/bin/bash\n"
                f"echo claude \"$@\" >> {calls}\n"
                "echo '2.1.203'\n"
                "CLAUDE\n"
                "chmod +x \"$HOME/.local/bin/claude\"\n"
                "SCRIPT\n",
            )
            env = {
                "PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin",
                "HOME": str(home),
            }

            result = subprocess.run(["/bin/bash", str(INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8")
            bashrc = (home / ".bashrc").read_text(encoding="utf-8")
            zshrc = (home / ".zshrc").read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('claude --version', log)
        self.assertIn('export PATH="$HOME/.local/bin:$PATH"', bashrc)
        self.assertIn('export PATH="$HOME/.local/bin:$PATH"', zshrc)
        self.assertIn("Claude Code listo para usar", result.stdout)
        self.assertNotIn("no está disponible todavía", result.stderr)

    def test_claude_installer_is_available_from_software_menu(self):
        source = INSTALL_PY.read_text(encoding="utf-8")

        self.assertIn('Category("claude_code", "Claude Code"', source)
        self.assertIn('scripts("claude_code/install_claude_code.sh")', source)

    @staticmethod
    def _write_mock(path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)


if __name__ == "__main__":
    unittest.main()
