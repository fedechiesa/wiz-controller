"""Windows RegisterHotKey message loop; no keyboard hooks or keystroke history."""
import ctypes
from ctypes import wintypes
import logging
import sys
import threading

LOGGER = logging.getLogger(__name__)
DEFAULT_HOTKEYS = {"Gaming": "Ctrl+Alt+F9", "Streaming": "Ctrl+Alt+F10",
                   "Relax": "Ctrl+Alt+F11", "Alternar luces": "Ctrl+Alt+F8"}
MODIFIERS = {"ALT": 1, "CTRL": 2, "SHIFT": 4}
MOD_NOREPEAT = 0x4000
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012


def parse_hotkey(value):
    if not isinstance(value, str):
        raise ValueError("El atajo debe ser texto, por ejemplo Ctrl+Alt+F9.")
    parts = [part.strip().upper() for part in value.split("+")]
    modifiers, key = parts[:-1], parts[-1]
    if not modifiers or len(set(modifiers)) != len(modifiers) or any(part not in MODIFIERS for part in modifiers):
        raise ValueError("Usá Ctrl, Alt o Shift sin repetir, más una letra, número o F1–F11.")
    if not {"CTRL", "ALT"} & set(modifiers):
        raise ValueError("El atajo debe incluir Ctrl o Alt para no capturar teclas comunes de juegos.")
    if key == "F12":
        raise ValueError("Windows reserva F12 para depuración. Elegí otra tecla, por ejemplo F8.")
    if len(key) == 1 and key.isascii() and key.isalnum():
        virtual_key = ord(key)
    elif key.startswith("F") and key[1:].isdigit() and 1 <= int(key[1:]) <= 11:
        virtual_key = 0x70 + int(key[1:]) - 1
    else:
        raise ValueError("La tecla debe ser A–Z, 0–9 o F1–F11.")
    return sum(MODIFIERS[modifier] for modifier in modifiers) | MOD_NOREPEAT, virtual_key


def validate_bindings(bindings):
    if not isinstance(bindings, dict) or set(bindings) != set(DEFAULT_HOTKEYS):
        raise ValueError("Configurá los cuatro atajos: Gaming, Streaming, Relax y Alternar luces.")
    parsed = [parse_hotkey(value) for value in bindings.values()]
    if len(set(parsed)) != len(parsed):
        raise ValueError("Dos acciones no pueden usar la misma combinación de teclas.")


class WinHotkeyAPI:
    def __init__(self):
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        self.user32.RegisterHotKey.restype = wintypes.BOOL
        self.user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user32.UnregisterHotKey.restype = wintypes.BOOL
        self.user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        self.user32.GetMessageW.restype = wintypes.BOOL
        self.user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
        self.user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.kernel32.GetCurrentThreadId.restype = wintypes.DWORD

    def prepare(self):
        message = wintypes.MSG()
        self.user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)
        return self.kernel32.GetCurrentThreadId()

    def register(self, identifier, modifiers, key):
        return bool(self.user32.RegisterHotKey(None, identifier, modifiers, key))

    def unregister(self, identifier):
        self.user32.UnregisterHotKey(None, identifier)

    def next_hotkey(self):
        message = wintypes.MSG()
        result = self.user32.GetMessageW(ctypes.byref(message), None, 0, 0)
        if result == -1:
            raise ctypes.WinError(ctypes.get_last_error())
        if result == 0:
            return None
        return int(message.wParam) if message.message == WM_HOTKEY else -1

    def wake(self, thread_id):
        if not self.user32.PostThreadMessageW(thread_id, WM_QUIT, 0, 0):
            raise ctypes.WinError(ctypes.get_last_error())


class GlobalHotkeys:
    def __init__(self, bindings, bus, api=None):
        validate_bindings(bindings)
        self.bindings, self.bus, self.api = dict(bindings), bus, api
        self.ready = threading.Event()
        self._stop = threading.Event()
        self.thread = None
        self.thread_id = None
        self.registered = {}

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, name="wiz-hotkeys", daemon=True)
        self.thread.start()

    def _run(self):
        try:
            if self.api is None:
                if sys.platform != "win32":
                    raise OSError("Los atajos globales están disponibles solo en Windows.")
                self.api = WinHotkeyAPI()
            self.thread_id = self.api.prepare()
            for identifier, (name, combination) in enumerate(self.bindings.items(), 1):
                if self._stop.is_set():
                    break
                if self.api.register(identifier, *parse_hotkey(combination)):
                    self.registered[identifier] = name
                else:
                    self.bus.emit("error", f"Atajo {name} ({combination}) no disponible; puede estar reservado u ocupado. Cambialo en Settings.")
            self.ready.set()
            self.bus.emit("status", f"Atajos registrados: {len(self.registered)} / {len(self.bindings)}.")
            while not self._stop.is_set():
                identifier = self.api.next_hotkey()
                if identifier is None:
                    break
                name = self.registered.get(identifier)
                if name:
                    self.bus.emit("toggle" if name == "Alternar luces" else "scene",
                                  "" if name == "Alternar luces" else name)
        except Exception as error:
            LOGGER.exception("Hotkey initialization/message loop failed")
            self.bus.emit("error", f"No se pudieron iniciar los atajos: {error}")
        finally:
            self.ready.set()
            if self.api:
                for identifier in self.registered:
                    self.api.unregister(identifier)
            self.registered.clear()

    def stop(self):
        self._stop.set()
        if self.thread:
            self.ready.wait(2)
            if self.thread.is_alive() and self.thread_id is not None:
                self.api.wake(self.thread_id)
            self.thread.join(2)
            if self.thread.is_alive():
                raise TimeoutError("El hilo de atajos no terminó a tiempo.")
