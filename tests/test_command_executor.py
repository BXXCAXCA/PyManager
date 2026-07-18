import shlex
import unittest

from src.command_executor import RemoteCommandExecutor, WSLCommandExecutor


class CaptureWSLExecutor(WSLCommandExecutor):
    def __init__(self, password=None):
        super().__init__(password=password)
        self.last_command = None

    def execute(self, command, cwd=None, env=None, timeout=60):
        self.last_command = command
        return 0, command, ""


class FakeSSHClient:
    def __init__(self):
        self.client = object()
        self.last_command = None

    def execute_command(self, command, timeout=30, input_data=None):
        self.last_command = command
        return "", "", 0


class CommandExecutorTests(unittest.TestCase):
    def test_wsl_sudo_quotes_password_and_compound_command(self):
        executor = CaptureWSLExecutor(password="pa'ss word")
        command = "apt-get update && apt-get install -y curl"

        exit_code, stdout, stderr = executor.execute_sudo(command)

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(stdout, executor.last_command)
        self.assertIn("printf '%s\\n'", executor.last_command)
        self.assertIn(shlex.quote("pa'ss word"), executor.last_command)
        self.assertIn("sudo -S -p '' bash -lc", executor.last_command)
        self.assertIn(shlex.quote(command), executor.last_command)

    def test_wsl_sudo_without_password_runs_whole_command_as_root(self):
        executor = CaptureWSLExecutor()
        command = "apt-get update && apt-get install -y build-essential"

        executor.execute_sudo(command)

        self.assertEqual(
            executor.last_command,
            f"sudo bash -lc {shlex.quote(command)}",
        )

    def test_remote_executor_quotes_cwd_with_spaces(self):
        ssh = FakeSSHClient()
        executor = RemoteCommandExecutor(ssh)

        exit_code, stdout, stderr = executor.execute("pwd", cwd="~/project dir")

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "")
        self.assertEqual(ssh.last_command, "cd -- ~/'project dir' && pwd")


if __name__ == "__main__":
    unittest.main()
