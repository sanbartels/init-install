import subprocess
import unittest
from unittest.mock import Mock, patch

import install


class SudoKeepaliveTests(unittest.TestCase):
    def test_start_sudo_keepalive_refreshes_credentials_non_interactively(self):
        with patch("install.subprocess.Popen") as popen:
            install.start_sudo_keepalive()

        popen.assert_called_once_with(
            ["bash", "-c", "while true; do sudo -n -v; sleep 30; done"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    def test_stop_sudo_keepalive_terminates_running_process(self):
        process = Mock()
        process.pid = 1234
        process.poll.return_value = None

        with patch("install.os.killpg") as killpg:
            install.stop_sudo_keepalive(process)

        killpg.assert_called_once_with(1234, 15)
        process.wait.assert_called_once_with(timeout=2)

    def test_stop_sudo_keepalive_kills_stubborn_process(self):
        process = Mock()
        process.pid = 1234
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired("sudo", 2), None]

        with patch("install.os.killpg") as killpg:
            install.stop_sudo_keepalive(process)

        self.assertEqual(killpg.call_args_list[0].args, (1234, 15))
        self.assertEqual(killpg.call_args_list[1].args, (1234, 9))

    def test_stop_sudo_keepalive_ignores_exit_race_during_force_kill(self):
        process = Mock()
        process.pid = 1234
        process.poll.return_value = None
        process.wait.side_effect = subprocess.TimeoutExpired("sudo", 2)

        with patch("install.os.killpg", side_effect=[None, ProcessLookupError]):
            install.stop_sudo_keepalive(process)

        self.assertEqual(process.wait.call_count, 1)


if __name__ == "__main__":
    unittest.main()
