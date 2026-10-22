"""Serialize desktop integration lifecycle on a supervisor, never on Tk."""
import logging
from queue import Empty, Queue
import threading

from .desktop_actions import ActionBus
from .hotkeys import GlobalHotkeys
from .tray import SystemTray

LOGGER = logging.getLogger(__name__)


class DesktopServices:
    def __init__(self, queue, tray_factory=SystemTray, hotkey_factory=GlobalHotkeys):
        self.bus = ActionBus(queue)
        self.tray_factory, self.hotkey_factory = tray_factory, hotkey_factory
        self.tray = self.hotkeys = None
        self.commands = Queue()
        self._closed = False
        self.thread = threading.Thread(target=self._run, name="wiz-desktop", daemon=True)
        self.thread.start()

    @property
    def tray_ready(self):
        tray = self.tray
        return bool(tray and tray.ready.is_set() and not tray.failed.is_set())

    def configure(self, config):
        if not self._closed:
            self.commands.put(config)

    def _stop_adapter(self, adapter):
        if adapter:
            try:
                adapter.stop()
            except Exception as error:
                LOGGER.exception("Desktop adapter cleanup failed")
                self.bus.emit("error", f"No se pudo liberar una integración: {error}")

    def _run(self):
        try:
            while True:
                try:
                    config = self.commands.get(timeout=0.25)
                except Empty:
                    if self.tray and self.tray.failed.is_set():
                        self._stop_adapter(self.tray)
                        self.tray = None
                    continue
                if config is None or self._closed:
                    break
                try:
                    self._stop_adapter(self.hotkeys)
                    self.hotkeys = None
                    if not config.tray_enabled or (self.tray and self.tray.failed.is_set()):
                        self._stop_adapter(self.tray)
                        self.tray = None
                    if config.tray_enabled and self.tray is None:
                        self.tray = self.tray_factory(self.bus)
                        self.tray.start()
                    if config.hotkeys_enabled:
                        self.hotkeys = self.hotkey_factory(config.hotkeys, self.bus)
                        self.hotkeys.start()
                except Exception as error:
                    LOGGER.exception("Desktop configuration failed")
                    self.bus.emit("error", f"No se pudo iniciar una integración: {error}")
        finally:
            self._stop_adapter(self.hotkeys)
            self._stop_adapter(self.tray)

    def stop(self):
        if not self._closed:
            self._closed = True
            self.bus.close()
            self.commands.put(None)

    def wait(self, timeout=8):
        self.thread.join(timeout)
        return not self.thread.is_alive()
