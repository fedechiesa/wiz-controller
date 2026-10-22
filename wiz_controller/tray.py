"""Real Windows notification icon, isolated from the Tk main thread."""
import logging
import threading

from .paths import resource_path

LOGGER = logging.getLogger(__name__)
TRAY_ITEMS = (("Abrir WiZ Controller", "show", ""),
              ("Encender todas", "on", ""), ("Apagar todas", "off", ""),
              ("Gaming", "scene", "Gaming"), ("Streaming", "scene", "Streaming"),
              ("Relax", "scene", "Relax"), ("Salir completamente", "quit", ""))


class SystemTray:
    def __init__(self, bus, module=None, image_loader=None):
        self.bus, self.module, self.image_loader = bus, module, image_loader
        self.ready, self.failed, self.stopping = threading.Event(), threading.Event(), threading.Event()
        self.icon = None
        self.thread = None

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, name="wiz-tray", daemon=True)
        self.thread.start()

    def callback(self, kind, value=""):
        def invoke(icon=None, item=None):
            if not self.stopping.is_set():
                self.bus.emit(kind, value)
        return invoke

    def _run(self):
        try:
            if self.module is None:
                import pystray
                self.module = pystray
            if self.image_loader:
                image = self.image_loader()
            else:
                from PIL import Image
                with Image.open(resource_path("assets/wiz-controller.png")) as source:
                    image = source.copy()
            items = [self.module.MenuItem(title, self.callback(kind, value), default=kind == "show")
                     for title, kind, value in TRAY_ITEMS]
            self.icon = self.module.Icon("WiZController", image, "WiZ Controller 2.1", self.module.Menu(*items))
            self.icon.run(setup=self._setup)
            if not self.stopping.is_set():
                raise RuntimeError("El ícono de bandeja dejó de responder.")
        except Exception as error:
            LOGGER.exception("Tray failed")
            if not self.stopping.is_set():
                self.failed.set()
                self.bus.emit("error", f"Bandeja no disponible: {error}. La X cerrará la aplicación; podés reintentar desde Settings.")
            # pystray 0.19.5 starts a setup thread before creating the Windows
            # icon. Release it if native startup failed before _mark_ready.
            startup_queue = getattr(self.icon, "_Icon__queue", None)
            if startup_queue is not None:
                startup_queue.put(True)
        finally:
            self.ready.clear()
            setup_thread = getattr(self.icon, "_setup_thread", None)
            if setup_thread is not None and setup_thread is not threading.current_thread():
                setup_thread.join(2)

    def _setup(self, icon):
        try:
            if self.failed.is_set():
                return
            if not self.stopping.is_set():
                icon.visible = True
                self.ready.set()
                self.bus.emit("status", "Bandeja disponible. Abrí el menú del ícono para restaurar o salir.")
            else:
                icon.stop()
        except Exception as error:
            self.failed.set()
            LOGGER.exception("Tray visibility failed")
            self.bus.emit("error", f"No se pudo mostrar el ícono de bandeja: {error}")
            icon.stop()

    def stop(self):
        self.stopping.set()
        if self.icon:
            self.icon.stop()
        if self.thread:
            self.thread.join(2)
            if self.thread.is_alive():
                raise TimeoutError("El hilo de bandeja no terminó a tiempo.")
        self.ready.clear()
