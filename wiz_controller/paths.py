"""Resource, launch and user data paths for Python and PyInstaller."""
import os
from pathlib import Path
import sys


def frozen():
    return bool(getattr(sys, "frozen", False))


def resource_path(name):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / name


def user_data_directory():
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    return base / "WiZController"


def legacy_data_directory():
    # Never migrate from an extracted bundle or the current working directory.
    base = Path(sys.executable).resolve().parent if frozen() else Path(__file__).resolve().parent.parent
    return base / "data"


def launch_arguments(background=False):
    executable = Path(sys.executable).resolve()
    if frozen():
        arguments = [str(executable)]
    else:
        pythonw = executable.with_name("pythonw.exe")
        if pythonw.exists():
            executable = pythonw
        arguments = [str(executable), str(resource_path("main.py").resolve())]
    if background:
        arguments.append("--background")
    return arguments
