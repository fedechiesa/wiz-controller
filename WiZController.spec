# Explicit resources only: never collect data/, tests/, credentials or the repo.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, copy_metadata

root = Path(SPECPATH)
datas = collect_data_files("customtkinter")
datas += copy_metadata("pystray")
datas += [(str(root / "assets" / name), "assets")
          for name in ("wiz-controller.ico", "wiz-controller.png")]

a = Analysis([str(root / "main.py")], pathex=[str(root)], datas=datas,
             hiddenimports=["pystray._win32", "PIL.IcoImagePlugin", "PIL.PngImagePlugin"],
             excludes=["pytest", "unittest", "tests", "PyInstaller", "setuptools"],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="WiZController",
          console=False, debug=False, strip=False, upx=False,
          icon=str(root / "assets/wiz-controller.ico"))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="WiZController")
