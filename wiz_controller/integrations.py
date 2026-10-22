"""Optional integration port; the dashboard has no OBS dependency."""
from pathlib import Path
import subprocess
import sys
from typing import Callable, Protocol


class Integration(Protocol):
    """Future adapters (OBS, hotkeys, tray) must release resources on stop.

    Callbacks may run in a worker: enqueue scene names, never call Tk directly.
    """
    def start(self, request_scene: Callable[[str], None]) -> None: ...
    def stop(self) -> None: ...


class WindowsAutostart:
    VALUE = "WiZController"
    KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

    @staticmethod
    def command():
        executable = Path(sys.executable)
        pythonw = executable.with_name("pythonw.exe")
        if pythonw.exists():
            executable = pythonw
        return subprocess.list2cmdline([str(executable), str(Path(__file__).resolve().parent.parent / "main.py")])

    @classmethod
    def enabled(cls):
        if sys.platform != "win32":
            return False
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, cls.KEY) as key:
                value, _ = winreg.QueryValueEx(key, cls.VALUE)
                return value == cls.command()
        except FileNotFoundError:
            return False

    @classmethod
    def set_enabled(cls, enabled):
        if sys.platform != "win32":
            raise OSError("El inicio automático está disponible solo en Windows.")
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, cls.KEY) as key:
            if enabled:
                winreg.SetValueEx(key, cls.VALUE, 0, winreg.REG_SZ, cls.command())
            else:
                try:
                    winreg.DeleteValue(key, cls.VALUE)
                except FileNotFoundError:
                    pass
