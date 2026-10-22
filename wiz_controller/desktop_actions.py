"""Small thread-safe command port shared by tray, hotkeys and Tk."""
from dataclasses import dataclass
import threading
import time


@dataclass(frozen=True)
class DesktopAction:
    kind: str
    value: str = ""


class ActionBus:
    def __init__(self, queue, debounce=0.35, clock=time.monotonic):
        self.queue, self.debounce, self.clock = queue, debounce, clock
        self._last = {}
        self._lock = threading.Lock()
        self._closed = False

    def emit(self, kind, value=""):
        action = DesktopAction(kind, value)
        with self._lock:
            if self._closed:
                return False
            now = self.clock()
            if kind not in {"error", "status"} and now - self._last.get(action, float("-inf")) < self.debounce:
                return False
            self._last[action] = now
            self.queue.put(action)
            return True

    def close(self):
        with self._lock:
            self._closed = True
