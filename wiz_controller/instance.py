"""Per-session Windows instance guard and restore signal (no listening socket)."""
import ctypes
from ctypes import wintypes
import sys


class SingleInstance:
    MUTEX = r"Local\WiZController.Desktop"
    EVENT = r"Local\WiZController.Restore"

    def __init__(self):
        self.kernel = None
        self.mutex = self.event = None

    def acquire(self):
        if sys.platform != "win32":
            return True
        kernel = self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        kernel.CreateMutexW.restype = wintypes.HANDLE
        kernel.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
        kernel.CreateEventW.restype = wintypes.HANDLE
        kernel.SetEvent.argtypes = [wintypes.HANDLE]
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.event = kernel.CreateEventW(None, False, False, self.EVENT)
        if not self.event:
            raise ctypes.WinError(ctypes.get_last_error())
        self.mutex = kernel.CreateMutexW(None, False, self.MUTEX)
        error = ctypes.get_last_error()
        if not self.mutex:
            self.close()
            raise ctypes.WinError(error)
        if error == 183:  # ERROR_ALREADY_EXISTS
            kernel.SetEvent(self.event)
            self.close()
            return False
        return True

    def consume_restore(self):
        return bool(self.kernel and self.event and self.kernel.WaitForSingleObject(self.event, 0) == 0)

    def close(self):
        if self.kernel:
            for handle in (self.mutex, self.event):
                if handle:
                    self.kernel.CloseHandle(handle)
        self.mutex = self.event = None
