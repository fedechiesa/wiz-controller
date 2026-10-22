"""Optional integration port; the dashboard has no OBS dependency."""
import subprocess
import sys
from typing import Callable, Protocol

from .paths import launch_arguments


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
        return subprocess.list2cmdline(launch_arguments(background=True))

    @classmethod
    def enabled(cls):
        if sys.platform != "win32":
            return False
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, cls.KEY) as key:
                value, _ = winreg.QueryValueEx(key, cls.VALUE)
                return isinstance(value, str) and bool(value)
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
