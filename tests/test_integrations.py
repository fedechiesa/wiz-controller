from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from wiz_controller.integrations import WindowsAutostart


class AutostartTests(unittest.TestCase):
    def test_command_quotes_python_and_absolute_entrypoint(self):
        with patch("wiz_controller.integrations.sys.executable", "C:/Program Files/Python/python.exe"), patch.object(Path, "exists", return_value=True):
            command = WindowsAutostart.command()
        self.assertTrue(command.startswith('"C:'))
        self.assertIn("pythonw.exe", command)
        self.assertIn("main.py", command)

    def test_registry_changes_are_opt_in_and_mocked(self):
        registry = MagicMock()
        with patch("wiz_controller.integrations.sys.platform", "win32"), patch.dict("sys.modules", winreg=registry):
            WindowsAutostart.set_enabled(True)
            registry.SetValueEx.assert_called_once()
            registry.DeleteValue.assert_not_called()
            WindowsAutostart.set_enabled(False)
            registry.DeleteValue.assert_called_once()
