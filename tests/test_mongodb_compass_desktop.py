import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_EXEC_LINE = 'Exec=env ELECTRON_OZONE_PLATFORM_HINT=auto "$INSTALL_DIR/MongoDB Compass" --ignore-additional-command-line-flags --password-store=gnome-libsecret'


class MongoDBCompassDesktopTests(unittest.TestCase):
    def test_install_and_update_desktop_entries_use_libsecret_password_store(self):
        for relative_path in (
            "mongodb_compass/install_compass.sh",
            "mongodb_compass/update_compass.sh",
        ):
            with self.subTest(script=relative_path):
                script = (ROOT / relative_path).read_text(encoding="utf-8")
                self.assertIn(REQUIRED_EXEC_LINE, script)

    def test_install_script_is_verbose_and_validates_executable(self):
        script = (ROOT / "mongodb_compass/install_compass.sh").read_text(encoding="utf-8")
        self.assertIn("command -v curl", script)
        self.assertIn("print_info \"Obteniendo última versión de MongoDB Compass...\"", script)
        self.assertIn("wget --show-progress", script)
        self.assertIn("EXECUTABLE=\"$INSTALL_DIR/MongoDB Compass\"", script)
        self.assertIn("[ -x \"$EXECUTABLE\" ]", script)

    def test_update_script_is_verbose_and_validates_executable(self):
        script = (ROOT / "mongodb_compass/update_compass.sh").read_text(encoding="utf-8")
        self.assertIn("command -v tar", script)
        self.assertIn("print_info \"Obteniendo última versión de MongoDB Compass...\"", script)
        self.assertIn("wget --show-progress", script)
        self.assertIn("EXECUTABLE=\"$INSTALL_DIR/MongoDB Compass\"", script)
        self.assertIn("[ -x \"$EXECUTABLE\" ]", script)


if __name__ == "__main__":
    unittest.main()
