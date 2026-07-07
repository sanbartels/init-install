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

    def test_tailscale_installer_uses_arch_package_and_manual_auth(self):
        script = TAILSCALE_INSTALLER.read_text(encoding="utf-8")

        self.assertIn("sudo pacman -S --needed --noconfirm tailscale", script)
        self.assertIn("sudo systemctl enable --now tailscaled.service", script)
        self.assertIn("sudo tailscale up --ssh", script)
        self.assertNotIn("tailscale up --authkey", script)


if __name__ == "__main__":
    unittest.main()
