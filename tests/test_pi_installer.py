import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "pi" / "install_pi.sh"
INSTALL_PY = ROOT / "install.py"


class PiInstallerTests(unittest.TestCase):
    def test_pi_installer_installs_pi_non_interactively_and_installs_subagents(self):
        script = INSTALLER.read_text(encoding="utf-8")

        self.assertNotIn("curl -fsSL https://pi.dev/install.sh | sh", script)
        self.assertIn("npm install -g --ignore-scripts --min-release-age=0", script)
        self.assertIn("--prefix \"$LOCAL_PREFIX\"", script)
        self.assertIn("https://github.com/j0k3r-dev-rgl/j0k3r-pi.git", script)
        self.assertIn("$HOME/.pi/agent", script)
        self.assertIn("git clone --depth 1 \"$REPO_URL\" \"$TARGET_DIR\"", script)
        self.assertIn("git -C \"$TARGET_DIR\" pull --ff-only", script)
        self.assertNotIn("rsync -a", script)
        self.assertIn('"$PI_BIN" install npm:pi-subagents-j0k3r', script)

        clone_index = script.index("clone_global_config")
        extension_index = script.index("install_subagents_extension")
        self.assertLess(clone_index, extension_index)

    def test_pi_installer_runs_without_official_tty_prompts(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            bin_dir = Path(tmp) / "bin"
            local_bin = home / ".local" / "bin"
            calls = Path(tmp) / "calls.log"
            home.mkdir()
            (home / ".bashrc").write_text("", encoding="utf-8")
            bin_dir.mkdir()
            local_bin.mkdir(parents=True)
            self._write_mock(bin_dir / "sudo", f"#!/bin/bash\necho sudo $@ >> {calls}\nexit 0\n")
            self._write_mock(bin_dir / "pacman", "#!/bin/bash\nexit 0\n")
            self._write_mock(
                bin_dir / "npm",
                f"#!/bin/bash\necho npm $@ >> {calls}\nprintf '#!/bin/bash\\necho pi \"$@\" >> {calls}\\nexit 0\\n' > {local_bin}/pi\nchmod +x {local_bin}/pi\nexit 0\n",
            )
            self._write_mock(bin_dir / "git", f"#!/bin/bash\necho git $@ >> {calls}\nmkdir -p {home}/.pi/agent/.git\nexit 0\n")
            env = {"PATH": f"{bin_dir}{os.pathsep}{local_bin}{os.pathsep}/usr/bin:/bin", "HOME": str(home)}

            result = subprocess.run(["/bin/bash", str(INSTALLER)], env=env, text=True, capture_output=True)
            log = calls.read_text(encoding="utf-8")
            bashrc = (home / ".bashrc").read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("npm install -g --ignore-scripts --min-release-age=0", log)
        self.assertIn("--prefix", log)
        self.assertIn("pi install npm:pi-subagents-j0k3r", log)
        self.assertIn('export PATH="$HOME/.local/bin:$PATH"', bashrc)
        self.assertNotIn("Choose an action", result.stdout)
        self.assertNotIn("Add /home", result.stdout)

    def test_pi_installer_is_available_from_software_menu(self):
        source = INSTALL_PY.read_text(encoding="utf-8")

        self.assertIn('Category("pi", "Pi Coding Agent"', source)
        self.assertIn('scripts("pi/install_pi.sh")', source)

    @staticmethod
    def _write_mock(path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)


if __name__ == "__main__":
    unittest.main()
