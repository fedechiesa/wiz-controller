"""CustomTkinter control center. All widgets and timers live on the Tk thread."""
from dataclasses import replace
import logging
from queue import Empty, Queue
import sys
import time
import tkinter as tk
from tkinter import colorchooser, messagebox

import customtkinter as ctk
from customtkinter.windows.widgets.scaling.scaling_tracker import ScalingTracker

from .integrations import WindowsAutostart
from .desktop import DesktopServices
from .desktop_actions import DesktopAction
from .paths import resource_path
from .models import AppConfig, BulbConfig, LightSetting, Scene, builtin_scenes
from .runtime import LightingRuntime
from .storage import Storage

LOGGER = logging.getLogger(__name__)
TEXT = "#F0F1FA"
MUTED = "#979CB5"
CYAN = "#30D9E8"
GREEN = "#58DBAB"
AMBER = "#F2BD67"
RED = "#FF7D93"
ACCENTS = {"Violeta": "#9561F9", "Cian": "#168A9F", "Magenta": "#CB428D"}
SWATCHES = ("#FF406C", "#FFAA50", "#F9EDD2", "#50D6A0", "#30D9E8", "#597DFF", "#A65BFF")
SCENE_INFO = {
    "Gaming": ("01", "Violeta + cian · 70%", "#9561F9"),
    "Streaming": ("02", "Magenta + azul · 80%", "#EF56A0"),
    "Relax": ("03", "Blanco cálido · 2700 K", "#F2BD67"),
    "Estudio": ("04", "Blanco neutro · 4000 K", "#A7C8F2"),
    "Noche": ("05", "Azul profundo · 15%", "#777CFA"),
}


def hex_rgb(rgb):
    return "#%02x%02x%02x" % tuple(rgb)


def preview_color(rgb=None, kelvin=None, warm_white=None):
    if rgb is not None:
        if warm_white:
            # Native RGB excludes the separate white LED. Blend it for a useful
            # approximation; otherwise a white-only RGBW read would look black.
            if not any(rgb):
                return "#FFE8CC"
            amount = warm_white / 255
            rgb = tuple(round(channel + (255 - channel) * amount) for channel in rgb)
        return hex_rgb(rgb)
    if kelvin is not None:
        return "#FFD8A0" if kelvin < 3500 else "#EBF2FF"
    return "#5A6079"


def label(parent, text, size=13, color=TEXT, bold=False, **kwargs):
    return ctk.CTkLabel(parent, text=text, text_color=color,
                        font=("Segoe UI", size, "bold" if bold else "normal"), **kwargs)


class OptionMenu(ctk.CTkOptionMenu):
    def destroy(self):
        # CTk 5.2.2 DropdownMenu.destroy forgets its scaling callback. Without
        # this cleanup changing scale after page navigation calls dead Tk menus.
        menu = self._dropdown_menu
        ScalingTracker.remove_widget(menu._set_scaling, menu)
        super().destroy()


def merge_request(previous, action, kwargs):
    """Keep the latest intent without losing a queued color when brightness changes."""
    if previous and action == "on":
        old_action, old_kwargs = previous
        if old_action in {"color", "brightness"}:
            return previous
        if old_action == "scene":
            return "scene", {"setting": replace(old_kwargs["setting"], power=True)}
    if previous and action == "brightness":
        old_action, old_kwargs = previous
        if old_action == "color":
            return old_action, {**old_kwargs, "brightness": kwargs["brightness"]}
        if old_action == "scene" and old_kwargs["setting"].power:
            return old_action, {"setting": replace(old_kwargs["setting"], brightness=kwargs["brightness"])}
    return action, kwargs


class BulbCard(ctk.CTkFrame):
    def __init__(self, parent, app, bulb, index):
        super().__init__(parent, fg_color=app.panel, corner_radius=18,
                         border_width=1, border_color=app.border)
        self.app, self.bulb = app, bulb
        self.color = (145, 45, 255) if index == 0 else (0, 210, 255)
        self.level = 70
        self.grid_columnconfigure(0, weight=1)
        heading = ctk.CTkFrame(self, fg_color="transparent")
        heading.grid(row=0, column=0, sticky="ew", padx=20, pady=(15, 0))
        label(heading, f"CANAL  0{index + 1}", 10, MUTED, True).pack(side="left")
        self.connection = label(heading, "●  Sin consultar", 11, MUTED)
        self.connection.pack(side="right")
        self.name = ctk.CTkEntry(self, fg_color="transparent", border_width=0,
                                 font=("Segoe UI", 22, "bold"), text_color=TEXT, height=34)
        self.name.insert(0, bulb.name)
        self.name.grid(row=1, column=0, sticky="ew", padx=15, pady=(3, 0))
        self.name.bind("<Return>", lambda event: app.rename_bulb(bulb.id, self.name.get()))
        self.name.bind("<FocusOut>", lambda event: app.rename_bulb(bulb.id, self.name.get()))
        label(self, f"{bulb.ip}  ·  WiZ / LAN", 11, MUTED).grid(row=2, column=0, sticky="w", padx=20)

        self.visual = tk.Canvas(self, height=88, bg=app.panel, highlightthickness=0)
        self.visual.grid(row=3, column=0, sticky="ew", padx=20, pady=(7, 0))
        self.visual.bind("<Configure>", lambda event: self.draw_preview(None))
        self.power_text = label(self, "Estado todavía no consultado", 12, MUTED)
        self.power_text.grid(row=4, column=0, sticky="w", padx=20, pady=(0, 9))

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=5, column=0, sticky="ew", padx=20)
        buttons.grid_columnconfigure((0, 1), weight=1)
        app.button(buttons, "Encender", lambda: app.request(bulb.id, "on"), height=34).grid(
            row=0, column=0, sticky="ew", padx=(0, 5))
        app.button(buttons, "Apagar", lambda: app.request(bulb.id, "off"), secondary=True, height=34).grid(
            row=0, column=1, sticky="ew", padx=(5, 0))

        self.brightness_text = label(self, "Brillo solicitado  ·  70%", 12, MUTED)
        self.brightness_text.grid(row=6, column=0, sticky="w", padx=20, pady=(12, 2))
        self.slider = ctk.CTkSlider(self, from_=5, to=100, number_of_steps=95, height=16,
                                    progress_color=app.accent, button_color=TEXT,
                                    button_hover_color=CYAN, fg_color=app.border,
                                    command=self.change_brightness)
        self.slider.set(self.level)
        self.slider.grid(row=7, column=0, sticky="ew", padx=20, pady=(0, 9))
        self.colors = ctk.CTkFrame(self, fg_color="transparent")
        self.colors.grid(row=8, column=0, sticky="ew", padx=17)
        for color in SWATCHES:
            ctk.CTkButton(self.colors, text="", width=26, height=23, corner_radius=7,
                          fg_color=color, hover_color=color,
                          command=lambda col=color: self.set_color(tuple(bytes.fromhex(col[1:])))).pack(side="left", padx=3)
        app.button(self.colors, "RGB…", self.pick_color, secondary=True, width=65, height=25).pack(side="right", padx=3)
        self.detail = label(self, "Vista previa aproximada · sin confirmar", 10, MUTED, anchor="w",
                            wraplength=360, justify="left")
        self.detail.grid(row=9, column=0, sticky="ew", padx=20, pady=(8, 15))

    def draw_preview(self, state):
        self.visual.delete("all")
        width = max(200, self.visual.winfo_width())
        confirmed = state or self.app.states.get(self.bulb.id)
        color = preview_color(confirmed.rgb, confirmed.kelvin, confirmed.warm_white) if confirmed else "#5A6079"
        if confirmed and not confirmed.power:
            color = "#555C77"
        channels = tuple(bytes.fromhex(color[1:]))
        base = tuple(bytes.fromhex(self.app.panel[1:]))
        for radius in range(40, 10, -3):
            strength = (1 - radius / 48) * 0.48
            shade = hex_rgb(tuple(round(b + (c - b) * strength) for b, c in zip(base, channels)))
            self.visual.create_oval(width - 114 - radius, 44 - radius, width - 114 + radius,
                                    44 + radius, fill=shade, outline="")
        self.visual.create_oval(width - 138, 20, width - 90, 68, fill=color, outline="")
        self.visual.create_oval(width - 128, 27, width - 113, 40, fill="#F0F1FA", outline="")
        self.visual.create_text(0, 26, text="COLOR ACTUAL", anchor="w", fill=MUTED, font=("Segoe UI", 9, "bold"))
        value = (f"{confirmed.kelvin} K" if confirmed and confirmed.kelvin and not confirmed.rgb
                 else hex_rgb(confirmed.rgb).upper() if confirmed and confirmed.rgb else "SIN DATOS")
        self.visual.create_text(0, 53, text=value, anchor="w", fill=TEXT, font=("Segoe UI", 18, "bold"))

    def change_brightness(self, value):
        self.level = round(value)
        self.brightness_text.configure(text=f"Brillo solicitado  ·  {self.level}%")
        self.app.debounce(self.bulb.id, self.level)

    def set_color(self, color):
        self.color = color
        self.app.request(self.bulb.id, "color", rgb=color, brightness=self.level)

    def pick_color(self):
        value, _ = colorchooser.askcolor(color=hex_rgb(self.color), parent=self)
        if value is not None:
            self.set_color(tuple(round(channel) for channel in value))

    def render_state(self):
        key = self.bulb.id
        busy = key in self.app.inflight
        reachable = self.app.available.get(key)
        error = self.app.errors.get(key)
        status, color = (("●  Consultando…" if self.app.actions.get(key) == "refresh" else "●  Aplicando…", AMBER)
                         if busy else ("●  Sin conexión", RED) if reachable is False else
                         ("●  Revisar ajuste", AMBER) if error else
                         ("●  Conectada", GREEN) if reachable else ("●  Sin consultar", MUTED))
        self.connection.configure(text=status, text_color=color)
        state = self.app.states.get(key)
        if state:
            prefix = "Último estado" if reachable is False else "Confirmado"
            self.power_text.configure(text=f"{prefix}  ·  {'Encendida' if state.power else 'Apagada'}",
                                      text_color=GREEN if state.power and reachable else MUTED)
            if not busy and key not in self.app.slider_jobs:
                if state.brightness is not None:
                    self.level = max(5, state.brightness)
                    self.slider.set(self.level)
                    self.brightness_text.configure(text=f"Brillo leído  ·  {state.brightness}%")
                if state.rgb:
                    self.color = tuple(bytes.fromhex(preview_color(state.rgb, warm_white=state.warm_white)[1:]))
        self.detail.configure(text=error or ("Esperando confirmación de la bombilla…" if busy else
                                             "Vista previa aproximada · estado leído por LAN" if state else
                                             "Vista previa aproximada · sin confirmar"),
                              text_color=RED if error and not busy else MUTED)
        self.draw_preview(state)


class WizController(ctk.CTk):
    def __init__(self, storage=None, *, network_enabled=True, runtime=None,
                 desktop_enabled=None, instance=None, background=False):
        ctk.set_appearance_mode("dark")
        super().__init__()
        self.storage = storage or Storage()
        self.config_data = self.storage.load_config()
        self.custom_scenes = self.storage.load_scenes()
        self.runtime = runtime or (LightingRuntime() if network_enabled else None)
        self.network_enabled = network_enabled
        self.closing = False
        self.states, self.available, self.errors = {}, {}, {}
        self.inflight, self.waiting, self.actions, self.futures = {}, {}, {}, {}
        self.active_requests = {}
        self.slider_jobs, self.levels = {}, {"global": 70, "bulb1": 70, "bulb2": 70}
        self.sequence = 0
        self.global_color = (145, 45, 255)
        self.active_scene = None
        self.cards = {}
        self.integration_requests = Queue()
        self.instance = instance
        self.desktop = None
        self._toggle_pending = False
        self._background_requested = background
        self._background_deadline = time.monotonic() + 6
        self.desktop_message = "Integraciones de escritorio desactivadas en esta sesión de prueba."
        self.desktop_errors = []
        self._timers = set()
        self._view_changing = False
        self._dialogs = set()
        self.title("WiZ Controller 2.1 · Desktop Gaming Edition")
        self.geometry("1220x900")
        self.minsize(1050, 720)
        self.protocol("WM_DELETE_WINDOW", self.on_window_close)
        if sys.platform == "win32":
            try:
                self.iconbitmap(str(resource_path("assets/wiz-controller.ico")))
            except tk.TclError:
                LOGGER.warning("Window icon unavailable")
        self._apply_appearance()
        self._build_shell()
        self.show_page("Dashboard")
        enable_desktop = network_enabled if desktop_enabled is None else desktop_enabled
        if enable_desktop:
            self.desktop = DesktopServices(self.integration_requests)
            self.desktop.configure(self.config_data)
        self.schedule(80, self.poll_results)
        if network_enabled:
            self.schedule(300, self.start_network)
            self.schedule(12_000, self.periodic_refresh)
        if self.storage.warnings:
            self.schedule(500, lambda: self.notify("\n".join(self.storage.warnings), error=True))

    def report_callback_exception(self, exc, value, traceback):
        LOGGER.error("UI callback failed", exc_info=(exc, value, traceback))
        self.notify(f"Error de interfaz: {value}. Revisá controller.log.", error=True)

    def schedule(self, delay, callback):
        def run():
            self._timers.discard(timer)
            if not self.closing:
                callback()
        timer = self.after(delay, run)
        self._timers.add(timer)
        return timer

    def cancel_timer(self, timer):
        if timer:
            self.after_cancel(timer)
            self._timers.discard(timer)

    def _apply_appearance(self):
        self.accent = ACCENTS[self.config_data.accent]
        self.bg = "#0C0E17" if self.config_data.palette == "Medianoche" else "#191B24"
        self.panel = "#151925" if self.config_data.palette == "Medianoche" else "#242834"
        self.border = "#2A3043"
        self.configure(fg_color=self.bg)
        ctk.set_widget_scaling(self.config_data.scale / 100)

    def button(self, parent, text, command, *, secondary=False, **kwargs):
        options = dict(height=38, corner_radius=9, font=("Segoe UI", 12, "bold"),
                       fg_color=self.border if secondary else self.accent,
                       hover_color="#3C435C" if secondary else "#7852BD", text_color=TEXT)
        options.update(kwargs)
        return ctk.CTkButton(parent, text=text, command=command, **options)

    def _build_shell(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        rail = ctk.CTkFrame(self, width=188, corner_radius=0, fg_color="#10131E")
        rail.grid(row=0, column=0, sticky="nsew")
        rail.grid_propagate(False)
        label(rail, "WiZ", 38, TEXT, True).pack(anchor="w", padx=25, pady=(30, 0))
        label(rail, "CONTROL CENTER", 10, self.accent, True).pack(anchor="w", padx=26)
        label(rail, "DESKTOP GAMING", 9, MUTED).pack(anchor="w", padx=26, pady=(2, 35))
        self.nav = {}
        for text, prefix in (("Dashboard", "◈"), ("Escenas", "▦"), ("Settings", "⚙"), ("Integraciones", "＋")):
            self.nav[text] = self.button(rail, f"{prefix}   {text}", lambda page=text: self.show_page(page),
                                          secondary=True, anchor="w", width=156, height=43)
            self.nav[text].pack(padx=16, pady=4)
        bottom = ctk.CTkFrame(rail, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=24, pady=26)
        label(bottom, "●  100% LOCAL", 11, CYAN, True).pack(anchor="w")
        label(bottom, "Tu setup. Tu luz.\nSin cuentas ni nube.", 11, MUTED, justify="left").pack(anchor="w", pady=(7, 20))
        self.button(bottom, "A la bandeja", self.minimize_to_tray, secondary=True, width=140, height=30).pack(pady=(0, 7))
        self.button(bottom, "Salir completamente", self.close_app, secondary=True, width=140, height=30).pack(pady=(0, 12))
        label(bottom, "WiZ Controller   /   2.1", 10, MUTED).pack(anchor="w")

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=0, column=1, sticky="nsew", padx=(28, 24), pady=(24, 17))
        content.grid_rowconfigure(1, weight=1)
        content.grid_columnconfigure(0, weight=1)
        header = ctk.CTkFrame(content, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        self.page_title = label(header, "Tu setup, en otra luz.", 27, bold=True)
        self.page_title.pack(side="left")
        self.button(header, "↻  Reconectar", self.refresh_all, secondary=True, width=125).pack(side="right")
        self.connection_text = label(header, "●  Sin consultar", 11, MUTED)
        self.connection_text.pack(side="right", padx=14)
        self.body = ctk.CTkScrollableFrame(content, fg_color="transparent", corner_radius=0,
                                            scrollbar_button_color=self.border)
        self.body.grid(row=1, column=0, sticky="nsew")
        self.body.grid_columnconfigure(0, weight=1)
        footer = ctk.CTkFrame(content, fg_color=self.panel, corner_radius=9)
        footer.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        self.status = label(footer, "Listo · Consultá el estado de tus luces por LAN.", 11, MUTED,
                            anchor="w", wraplength=800, justify="left")
        self.status.pack(fill="x", padx=14, pady=9)

    def show_page(self, page):
        if self.closing:
            return
        self._view_changing = True
        for child in self.body.winfo_children():
            child.destroy()
        self.cards = {}
        self._view_changing = False
        self.current_page = page
        for name, button in self.nav.items():
            button.configure(fg_color=self.accent if name == page else "transparent")
        self.page_title.configure(text={"Dashboard": "Tu setup, en otra luz.", "Escenas": "Un ambiente para cada momento.",
                                       "Settings": "Ajustá tu centro de control.", "Integraciones": "Tu próximo nivel."}[page])
        {"Dashboard": self.build_dashboard, "Escenas": self.build_scenes,
         "Settings": self.build_settings, "Integraciones": self.build_integrations}[page]()
        self.body._parent_canvas.yview_moveto(0)
        self.update_indicators()

    def build_dashboard(self):
        hero = ctk.CTkFrame(self.body, fg_color=self.panel, border_width=1,
                             border_color=self.border, corner_radius=18)
        hero.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        hero.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(hero, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=22, pady=(17, 0))
        label(top, "MASTER CONTROL", 10, CYAN, True).pack(side="left")
        self.scene_badge = label(top, self.active_scene or "Control manual", 11, self.accent, True)
        self.scene_badge.pack(side="right")
        line = ctk.CTkFrame(hero, fg_color="transparent")
        line.grid(row=1, column=0, sticky="ew", padx=22, pady=(7, 12))
        label(line, "Todo tu espacio. Un solo toque.", 21, bold=True).pack(side="left")
        self.button(line, "Apagar todo", lambda: self.request_all("off"), secondary=True, width=116).pack(side="right", padx=(8, 0))
        self.button(line, "Encender todo", lambda: self.request_all("on"), width=125).pack(side="right")
        controls = ctk.CTkFrame(hero, fg_color="transparent")
        controls.grid(row=2, column=0, sticky="ew", padx=22, pady=(0, 17))
        controls.grid_columnconfigure(0, weight=1)
        self.master_label = label(controls, f"Brillo global solicitado   {self.levels['global']}%", 12, MUTED)
        self.master_label.grid(row=0, column=0, sticky="w")
        self.master_slider = ctk.CTkSlider(controls, from_=5, to=100, number_of_steps=95, height=16,
                                           progress_color=self.accent, button_color=TEXT,
                                           button_hover_color=CYAN, fg_color=self.border,
                                           command=self.master_brightness)
        self.master_slider.set(self.levels["global"])
        self.master_slider.grid(row=1, column=0, sticky="ew", padx=(0, 22), pady=(8, 0))
        self.button(controls, "◉  Color global", self.pick_global_color, secondary=True, width=145).grid(row=0, column=1, rowspan=2)
        section = ctk.CTkFrame(self.body, fg_color="transparent")
        section.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        label(section, "Tus luces", 18, bold=True).pack(side="left")
        label(section, "CONTROL INDEPENDIENTE  /  02", 10, MUTED).pack(side="right")
        row = ctk.CTkFrame(self.body, fg_color="transparent")
        row.grid(row=2, column=0, sticky="ew")
        row.grid_columnconfigure((0, 1), weight=1, uniform="bulbs")
        for index, bulb in enumerate(self.config_data.bulbs):
            card = BulbCard(row, self, bulb, index)
            card.grid(row=0, column=index, sticky="nsew", padx=(0, 8) if index == 0 else (8, 0))
            self.cards[bulb.id] = card
        self._card_columns = 2
        row.bind("<Configure>", lambda event: self.layout_cards(row))
        head = ctk.CTkFrame(self.body, fg_color="transparent")
        head.grid(row=3, column=0, sticky="ew", pady=(20, 10))
        label(head, "Escenas rápidas", 18, bold=True).pack(side="left")
        self.button(head, "Gestionar escenas  →", lambda: self.show_page("Escenas"), secondary=True, height=30, width=160).pack(side="right")
        self.scene_grid(self.body, row=4, compact=True)

    def layout_cards(self, row):
        columns = 2 if row.winfo_width() / self._get_widget_scaling() >= 730 else 1
        if columns == self._card_columns:
            return
        self._card_columns = columns
        row.grid_columnconfigure(1, weight=1 if columns == 2 else 0)
        for index, card in enumerate(self.cards.values()):
            card.grid(row=index // columns, column=index % columns, sticky="nsew",
                      padx=(0, 8) if columns == 2 and index == 0 else (8, 0) if columns == 2 else 0,
                      pady=(0, 12) if columns == 1 else 0)

    def scene_grid(self, parent, row, compact=False):
        grid = ctk.CTkFrame(parent, fg_color="transparent")
        grid.grid(row=row, column=0, sticky="ew")
        grid.grid_columnconfigure((0, 1, 2), weight=1, uniform="scenes")
        scenes = builtin_scenes() if compact else self.all_scenes()
        for index, (name, scene) in enumerate(scenes.items()):
            self.scene_tile(grid, scene, index, custom=name in self.custom_scenes)
        index = len(scenes)
        tile = ctk.CTkFrame(grid, fg_color=self.panel, corner_radius=13, border_width=1, border_color=self.border)
        tile.grid(row=index // 3, column=index % 3, sticky="nsew", padx=4, pady=4)
        label(tile, "+  Personalizado", 15, self.accent, True).pack(anchor="w", padx=16, pady=(13, 3))
        label(tile, "Diseñá tu propia combinación", 11, MUTED).pack(anchor="w", padx=16)
        self.button(tile, "Crear escena", lambda: self.edit_scene(), secondary=True, height=30).pack(fill="x", padx=16, pady=(9, 13))

    def scene_tile(self, parent, scene, index, custom=False):
        number, subtitle, color = SCENE_INFO.get(scene.name, ("＋", "Tu combinación guardada", self.accent))
        tile = ctk.CTkFrame(parent, fg_color=self.panel, corner_radius=13, border_width=1, border_color=self.border)
        tile.grid(row=index // 3, column=index % 3, sticky="nsew", padx=4, pady=4)
        title = ctk.CTkFrame(tile, fg_color="transparent")
        title.pack(fill="x", padx=16, pady=(13, 3))
        label(title, scene.name, 15, TEXT, True, anchor="w", wraplength=200).pack(side="left", fill="x", expand=True)
        label(title, number, 11, color, True).pack(side="right")
        label(tile, subtitle, 11, MUTED).pack(anchor="w", padx=16)
        bar = ctk.CTkFrame(tile, fg_color="transparent", height=4)
        bar.pack(fill="x", padx=16, pady=(8, 0))
        for setting in scene.lights.values():
            ctk.CTkFrame(bar, height=3, fg_color=preview_color(setting.rgb, setting.kelvin, setting.warm_white)).pack(side="left", fill="x", expand=True, padx=1)
        self.button(tile, "Aplicar", lambda: self.apply_scene(scene.name), secondary=True, height=30).pack(fill="x", padx=16, pady=(8, 13 if not custom else 5))
        if custom:
            actions = ctk.CTkFrame(tile, fg_color="transparent")
            actions.pack(fill="x", padx=16, pady=(0, 12))
            self.button(actions, "Editar", lambda: self.edit_scene(scene), secondary=True, width=75, height=27).pack(side="left")
            self.button(actions, "Eliminar", lambda: self.delete_scene(scene.name), secondary=True, width=80, height=27).pack(side="right")

    def build_scenes(self):
        label(self.body, "Dos luces, una composición. Cada escena conserva su propio color y brillo por canal.", 13,
              MUTED, anchor="w", wraplength=750).grid(row=0, column=0, sticky="ew", pady=(0, 14))
        tools = ctk.CTkFrame(self.body, fg_color="transparent")
        tools.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        self.button(tools, "+  Nueva escena", lambda: self.edit_scene(), width=150).pack(side="left")
        self.button(tools, "Guardar estado leído", self.capture_scene, secondary=True, width=180).pack(side="left", padx=10)
        self.scene_grid(self.body, row=2)

    def all_scenes(self):
        return {**builtin_scenes(), **self.custom_scenes}

    def notify(self, text, error=False):
        if not self.closing:
            self.status.configure(text=text, text_color=RED if error else MUTED)

    def rename_bulb(self, key, name):
        if self._view_changing or self.closing:
            return
        bulb = next(bulb for bulb in self.config_data.bulbs if bulb.id == key)
        if name.strip() == bulb.name:
            return
        try:
            changed = replace(bulb, name=name)
            config = replace(self.config_data, bulbs=[changed if item.id == key else item for item in self.config_data.bulbs])
            self.storage.save_config(config)
            self.config_data = config
            self.notify(f"Nombre guardado: {changed.name}.")
        except (ValueError, OSError) as error:
            self.notify(str(error), error=True)

    def master_brightness(self, value):
        self.levels["global"] = round(value)
        self.master_label.configure(text=f"Brillo global solicitado   {round(value)}%")
        for bulb in self.config_data.bulbs:
            card = self.cards.get(bulb.id)
            if card:
                card.level = round(value)
                card.slider.set(round(value))
                card.brightness_text.configure(text=f"Brillo solicitado  ·  {round(value)}%")
            self.debounce(bulb.id, round(value))

    def debounce(self, key, value):
        self.levels[key] = value
        self.cancel_timer(self.slider_jobs.pop(key, None))
        def send():
            self.slider_jobs.pop(key, None)
            self.request(key, "brightness", brightness=self.levels[key])
        self.slider_jobs[key] = self.schedule(350, send)

    def cancel_sliders(self, key=None):
        keys = [key] if key else list(self.slider_jobs)
        for item in keys:
            self.cancel_timer(self.slider_jobs.pop(item, None))

    def pick_global_color(self):
        rgb, _ = colorchooser.askcolor(color=hex_rgb(self.global_color), parent=self)
        if rgb is not None:
            self.global_color = tuple(round(channel) for channel in rgb)
            self.request_all("color", rgb=self.global_color, brightness=self.levels["global"])

    def request_all(self, action, **kwargs):
        for bulb in self.config_data.bulbs:
            self.request(bulb.id, action, **kwargs)

    def request(self, key, action, **kwargs):
        if self.closing:
            return
        if self.runtime is None:
            self.notify("Modo de prueba de interfaz: no se envían órdenes a las bombillas.")
            return
        if action != "refresh":
            self._toggle_pending = False
            self.cancel_sliders(key)
            if action != "scene":
                self.active_scene = None
        if key in self.inflight:
            if action == "refresh":
                return
            candidate = merge_request(self.waiting.get(key), action, kwargs)
            if self.waiting.get(key) == candidate or (key not in self.waiting and self.active_requests.get(key) == candidate):
                return
            self.waiting[key] = candidate
            self.notify("Ajuste pendiente · se aplicará la última selección al terminar la operación actual.")
            return
        self._begin(key, action, kwargs)

    def _begin(self, key, action, kwargs):
        bulb = next(bulb for bulb in self.config_data.bulbs if bulb.id == key)
        self.sequence += 1
        self.inflight[key] = (self.sequence, bulb.ip)
        self.actions[key] = action
        self.active_requests[key] = (action, kwargs)
        self.errors.pop(key, None)
        self.futures[key] = self.runtime.submit(key, bulb.ip, self.sequence, action, **kwargs)
        self.notify(f"{'Consultando' if action == 'refresh' else 'Aplicando ajuste a'} {bulb.name}…")
        self.update_indicators()

    def poll_results(self):
        if self.instance and self.instance.consume_restore():
            self.restore_window()
        if self.runtime:
            while True:
                try:
                    result = self.runtime.results.get_nowait()
                except Empty:
                    break
                if self.inflight.get(result.bulb_id) != (result.token, result.ip):
                    continue
                key = result.bulb_id
                self.inflight.pop(key, None)
                self.active_requests.pop(key, None)
                self.futures.pop(key, None)
                self.available[key] = result.reachable
                if result.state is not None:
                    self.states[key] = result.state
                if result.error:
                    self.errors[key] = result.error
                    self.active_scene = None
                else:
                    self.errors.pop(key, None)
                if key in self.waiting:
                    action, kwargs = self.waiting.pop(key)
                    self._begin(key, action, kwargs)
                elif not self.inflight:
                    if self.errors:
                        self.notify("Revisá las luces marcadas con error. Podés volver a intentar con Reconectar.", error=True)
                    else:
                        self.notify(f"Lectura confirmada · {time.strftime('%H:%M:%S')} · ajustes finalizados.")
                self.update_indicators()
        if self._toggle_pending and not self.inflight:
            self._toggle_pending = False
            if all(self.available.get(bulb.id) and bulb.id in self.states for bulb in self.config_data.bulbs):
                action = "off" if any(self.states[bulb.id].power for bulb in self.config_data.bulbs) else "on"
                self.request_all(action)
            else:
                self.notify("No se puede alternar: primero deben responder las dos bombillas. Usá Encender/Apagar para una orden explícita.", error=True)
        while True:
            try:
                action = self.integration_requests.get_nowait()
            except Empty:
                break
            self.handle_desktop_action(action)
            if self.closing:
                return
        if self._background_requested:
            if self.desktop and self.desktop.tray_ready:
                self._background_requested = False
                self.minimize_to_tray()
            elif time.monotonic() >= self._background_deadline:
                self._background_requested = False
                self.restore_window()
                self.notify("No se pudo iniciar en bandeja; el panel queda abierto para que puedas salir o revisar Settings.", error=True)
        self.schedule(80, self.poll_results)

    def handle_desktop_action(self, action):
        if self.closing:
            return
        if isinstance(action, str):
            action = DesktopAction("scene", action)  # Existing integration port remains compatible.
        if not isinstance(action, DesktopAction):
            return
        if action.kind == "show":
            self.restore_window()
        elif action.kind == "quit":
            self.close_app()
        elif action.kind in {"on", "off"}:
            self.request_all(action.kind)
        elif action.kind == "toggle":
            self.toggle_lights()
        elif action.kind == "scene":
            if action.value in self.all_scenes():
                self.apply_scene(action.value)
            else:
                self.notify(f"Escena desconocida: {action.value}", error=True)
        elif action.kind in {"error", "status"}:
            if action.kind == "error":
                self.desktop_errors.append(action.value)
                self._background_requested = False
                self.restore_window()
            self.desktop_message = "\n".join(self.desktop_errors[-3:]) if self.desktop_errors else action.value
            self.notify(self.desktop_message, error=bool(self.desktop_errors))

    def toggle_lights(self):
        if self._toggle_pending or self.inflight or self.waiting or self.slider_jobs:
            self.notify("Esperá a que termine la operación actual antes de alternar las luces.")
            return
        if self.runtime is None:
            self.notify("No hay conexión de red en esta sesión de prueba.")
            return
        self._toggle_pending = True
        self.request_all("refresh")

    def restore_window(self):
        if not self.closing:
            self._background_requested = False
            self.deiconify()
            self.state("normal")
            self.lift()
            self.focus_force()
            for dialog in self._dialogs:
                dialog.deiconify()
                dialog.lift()

    def minimize_to_tray(self):
        if self.desktop and self.desktop.tray_ready:
            for dialog in self._dialogs:
                dialog.withdraw()
            self.withdraw()
        else:
            self.notify("La bandeja todavía no está disponible. El panel seguirá abierto; podés usar Salir completamente.", error=True)

    def on_window_close(self):
        if self.config_data.close_to_tray and self.config_data.tray_enabled and self.desktop and self.desktop.tray_ready:
            self.minimize_to_tray()
        else:
            self.close_app()

    def update_indicators(self):
        count = sum(value is True for value in self.available.values())
        if self.inflight:
            text, color = f"●  {len(self.inflight)} en proceso", AMBER
        elif count == 2:
            text, color = "●  2 / 2 conectadas", GREEN
        elif self.available:
            text, color = f"●  {count} / 2 conectadas", AMBER if count else RED
        else:
            text, color = "●  Sin consultar", MUTED
        self.connection_text.configure(text=text, text_color=color)
        if self.current_page == "Dashboard":
            self.scene_badge.configure(text=f"Solicitada: {self.active_scene}" if self.active_scene else "Control manual")
        for card in self.cards.values():
            card.render_state()

    def start_network(self):
        if self.config_data.startup_scene in self.all_scenes():
            self.apply_scene(self.config_data.startup_scene)
        else:
            if self.config_data.startup_scene:
                self.notify("La escena de inicio no existe. Elegí otra en Settings.", error=True)
            self.refresh_all()

    def refresh_all(self):
        self.request_all("refresh")

    def periodic_refresh(self):
        self.refresh_all()
        self.schedule(12_000, self.periodic_refresh)

    def apply_scene(self, name):
        scene = self.all_scenes().get(name)
        if scene is None:
            return
        self.cancel_sliders()
        self.active_scene = name
        for key, setting in scene.lights.items():
            self.levels[key] = setting.brightness
            card = self.cards.get(key)
            if card:
                card.level = setting.brightness
                card.slider.set(setting.brightness)
                card.brightness_text.configure(text=f"Brillo solicitado  ·  {setting.brightness}%")
            self.request(key, "scene", setting=setting)
        self.update_indicators()

    def capture_scene(self):
        try:
            if self.inflight or self.slider_jobs or not all(self.available.get(b.id) for b in self.config_data.bulbs):
                raise ValueError("Reconectá ambas luces y esperá a que terminen los ajustes antes de capturar el estado.")
            scene = Scene("Personalizado", {key: state.as_setting() for key, state in self.states.items()})
            self.edit_scene(scene, copy=True)
        except ValueError as error:
            self.notify(str(error), error=True)

    def edit_scene(self, scene=None, copy=False):
        SceneEditor(self, scene, copy=copy)

    def save_scene(self, scene, original=None):
        names = {name.casefold() for name in self.all_scenes() if name != original} | {"sin escena"}
        if scene.name.casefold() in names:
            raise ValueError("Ya existe una escena con ese nombre. Elegí uno diferente.")
        scenes = dict(self.custom_scenes)
        if original:
            scenes.pop(original, None)
        scenes[scene.name] = scene
        # Write the rename first so startup references never point to a missing scene.
        self.storage.save_scenes(scenes)
        self.custom_scenes = scenes
        if original and self.config_data.startup_scene == original:
            config = replace(self.config_data, startup_scene=scene.name)
            self.storage.save_config(config)
            self.config_data = config
        self.show_page("Escenas")
        self.notify(f"Escena «{scene.name}» guardada localmente.")

    def delete_scene(self, name):
        if not messagebox.askyesno("Eliminar escena", f"¿Eliminar «{name}»?", parent=self):
            return
        try:
            if self.config_data.startup_scene == name:
                config = replace(self.config_data, startup_scene=None)
                self.storage.save_config(config)
                self.config_data = config
            scenes = {key: value for key, value in self.custom_scenes.items() if key != name}
            self.storage.save_scenes(scenes)
            self.custom_scenes = scenes
            self.show_page("Escenas")
            self.notify(f"Escena «{name}» eliminada.")
        except (OSError, ValueError) as error:
            self.notify(str(error), error=True)

    def build_settings(self):
        panel = ctk.CTkFrame(self.body, fg_color=self.panel, corner_radius=18)
        panel.grid(row=0, column=0, sticky="ew")
        panel.grid_columnconfigure(0, weight=1)
        label(panel, "Dispositivos de tu red", 20, bold=True).grid(row=0, column=0, sticky="w", padx=24, pady=(20, 4))
        label(panel, "Los cambios de IP reinician la conexión. No hace falta cerrar la aplicación.", 12, MUTED,
              wraplength=700).grid(row=1, column=0, sticky="w", padx=24, pady=(0, 15))
        self.settings_bulbs = {}
        for index, bulb in enumerate(self.config_data.bulbs):
            row = ctk.CTkFrame(panel, fg_color="transparent")
            row.grid(row=index + 2, column=0, sticky="ew", padx=24, pady=8)
            row.grid_columnconfigure((0, 1), weight=1)
            label(row, f"CANAL 0{index + 1} / NOMBRE", 10, MUTED, True).grid(row=0, column=0, sticky="w")
            label(row, "DIRECCIÓN IPv4", 10, MUTED, True).grid(row=0, column=1, sticky="w", padx=(14, 0))
            entries = []
            for col, value in enumerate((bulb.name, bulb.ip)):
                entry = ctk.CTkEntry(row, height=38, fg_color=self.bg, border_color=self.border, text_color=TEXT)
                entry.insert(0, value)
                entry.grid(row=1, column=col, sticky="ew", pady=(6, 0), padx=(0, 0) if col == 0 else (14, 0))
                entries.append(entry)
            self.settings_bulbs[bulb.id] = entries

        prefs = ctk.CTkFrame(panel, fg_color="transparent")
        prefs.grid(row=4, column=0, sticky="ew", padx=24, pady=(19, 12))
        prefs.grid_columnconfigure((0, 1), weight=1)
        values = ["Sin escena"] + list(self.all_scenes())
        self.startup_choice = self.setting_menu(prefs, 0, 0, "ESCENA AL INICIAR", values,
                                                self.config_data.startup_scene if self.config_data.startup_scene in values else "Sin escena")
        self.accent_choice = self.setting_menu(prefs, 0, 1, "ACENTO", list(ACCENTS), self.config_data.accent)
        self.palette_choice = self.setting_menu(prefs, 2, 0, "APARIENCIA", ["Medianoche", "Grafito"], self.config_data.palette)
        self.scale_choice = self.setting_menu(prefs, 2, 1, "ESCALA DE CONTROLES", ["100%", "110%", "125%"], f"{self.config_data.scale}%")
        try:
            self.autostart_original = WindowsAutostart.enabled()
            autostart_error = None
        except OSError as error:
            self.autostart_original, autostart_error = False, str(error)
        self.autostart_var = tk.BooleanVar(value=self.autostart_original)
        self.autostart_box = ctk.CTkCheckBox(panel, text="Iniciar WiZ Controller al entrar a Windows",
                                            variable=self.autostart_var, fg_color=self.accent, text_color=TEXT,
                                            font=("Segoe UI", 12), hover_color=self.accent)
        self.autostart_box.grid(row=5, column=0, sticky="w", padx=24, pady=(5, 10))
        if sys.platform != "win32" or autostart_error:
            self.autostart_box.configure(state="disabled")
        label(panel, autostart_error or "Se guarda para tu usuario de Windows. Podés desactivarlo desde aquí.", 11, MUTED,
              wraplength=700).grid(row=6, column=0, sticky="w", padx=24, pady=(0, 12))
        self.button(panel, "Guardar configuración", self.save_settings, width=210).grid(row=7, column=0, sticky="w", padx=24, pady=(0, 22))
        daily = ctk.CTkFrame(self.body, fg_color=self.panel, corner_radius=18)
        daily.grid(row=1, column=0, sticky="ew", pady=(16, 0))
        daily.grid_columnconfigure(1, weight=1)
        label(daily, "Escritorio y gaming", 20, bold=True).grid(row=0, column=0, columnspan=2, sticky="w", padx=24, pady=(18, 12))
        self.tray_var = tk.BooleanVar(value=self.config_data.tray_enabled)
        self.close_to_tray_var = tk.BooleanVar(value=self.config_data.close_to_tray)
        self.hotkeys_var = tk.BooleanVar(value=self.config_data.hotkeys_enabled)
        for row, (text, variable) in enumerate([
            ("Mostrar ícono en la bandeja del sistema", self.tray_var),
            ("La X minimiza a la bandeja (Salir siempre cierra)", self.close_to_tray_var),
            ("Activar atajos globales de Windows", self.hotkeys_var),
        ], 1):
            ctk.CTkCheckBox(daily, text=text, variable=variable, fg_color=self.accent, text_color=TEXT,
                            font=("Segoe UI", 12)).grid(row=row, column=0, columnspan=2, sticky="w", padx=24, pady=7)
        self.hotkey_entries = {}
        for row, (name, combination) in enumerate(self.config_data.hotkeys.items(), 4):
            label(daily, name, 12, MUTED).grid(row=row, column=0, sticky="w", padx=24, pady=5)
            entry = ctk.CTkEntry(daily, height=34, fg_color=self.bg, border_color=self.border)
            entry.insert(0, combination)
            entry.grid(row=row, column=1, sticky="ew", padx=(12, 24), pady=5)
            self.hotkey_entries[name] = entry
        label(daily, "Formato: Ctrl+Alt+F9 · Ctrl+Shift+G. F12 está reservada por Windows.\nLos conflictos se informan al registrar; los demás atajos siguen disponibles.",
              11, MUTED, wraplength=700, justify="left").grid(row=8, column=0, columnspan=2, sticky="w", padx=24, pady=(10, 5))
        label(daily, self.desktop_message, 11, MUTED, wraplength=700, justify="left").grid(row=9, column=0, columnspan=2, sticky="w", padx=24, pady=8)
        self.button(daily, "Guardar configuración", self.save_settings, width=210).grid(row=10, column=0, columnspan=2, sticky="w", padx=24, pady=(5, 20))
        label(self.body, f"ARCHIVOS LOCALES\n{self.storage.directory}\nconfig.json  ·  scenes.json  ·  controller.log", 12, MUTED,
              anchor="w", justify="left", wraplength=750).grid(row=2, column=0, sticky="ew", padx=4, pady=20)

    def setting_menu(self, parent, row, col, title, values, value):
        label(parent, title, 10, MUTED, True).grid(row=row, column=col, sticky="w", padx=(0, 12), pady=(0, 5))
        menu = OptionMenu(parent, values=values, fg_color=self.bg, button_color=self.border,
                                 button_hover_color=self.accent, height=36, text_color=TEXT,
                                 dropdown_fg_color=self.panel, dropdown_text_color=TEXT)
        menu.set(value)
        menu.grid(row=row + 1, column=col, sticky="ew", padx=(0, 12), pady=(0, 15))
        return menu

    def save_settings(self):
        try:
            config = AppConfig(
                bulbs=[BulbConfig(key, entries[0].get(), entries[1].get().strip()) for key, entries in self.settings_bulbs.items()],
                startup_scene=None if self.startup_choice.get() == "Sin escena" else self.startup_choice.get(),
                accent=self.accent_choice.get(), palette=self.palette_choice.get(), scale=int(self.scale_choice.get().rstrip("%")),
                tray_enabled=self.tray_var.get(), close_to_tray=self.close_to_tray_var.get(),
                hotkeys_enabled=self.hotkeys_var.get(), hotkeys={name: entry.get().strip() for name, entry in self.hotkey_entries.items()})
            autostart = self.autostart_var.get()
            self.storage.save_config(config)
        except (ValueError, OSError) as error:
            self.notify(str(error), error=True)
            return
        autostart_error = None
        if autostart != self.autostart_original or autostart:
            try:
                WindowsAutostart.set_enabled(autostart)
            except OSError as error:
                LOGGER.warning("Autostart failed: %s", error)
                autostart_error = f"Configuración guardada; no se pudo cambiar el inicio automático: {error}"
        self.cancel_sliders()
        for future in self.futures.values():
            if future:
                future.cancel()
        self.inflight.clear()
        self.waiting.clear()
        self.futures.clear()
        self.active_requests.clear()
        self.states.clear()
        self.available.clear()
        self.errors.clear()
        self._toggle_pending = False
        self.config_data = config
        self.desktop_errors.clear()
        if self.desktop:
            self.desktop.configure(config)
        self._view_changing = True
        for child in self.winfo_children():
            child.destroy()
        self._view_changing = False
        self._apply_appearance()
        self._build_shell()
        self.show_page("Settings")
        self.refresh_all()
        self.notify(autostart_error or "Configuración guardada. Se actualizarán los estados por LAN.", error=bool(autostart_error))

    def build_integrations(self):
        label(self.body, "Bandeja y atajos se configuran en Settings. Las integraciones de streaming quedan para otra fase.",
              13, MUTED, anchor="w", wraplength=750).grid(row=0, column=0, sticky="ew", pady=(0, 18))
        for index, (title, detail) in enumerate([
            ("OBS Studio", "Pendiente · obs-websocket y activación por estado de streaming."),
            ("Atajos globales", "Disponible en Windows · RegisterHotKey sin hooks. Activación y combinaciones en Settings."),
            ("Bandeja del sistema", "Disponible en Windows · abrir, encender, apagar, aplicar escenas o salir desde el ícono."),
            ("Eventos del stream", "Pendiente · adaptadores para eventos y alertas de tu plataforma."),
        ]):
            card = ctk.CTkFrame(self.body, fg_color=self.panel, corner_radius=14)
            card.grid(row=index + 1, column=0, sticky="ew", pady=6)
            label(card, title, 19, bold=True).pack(anchor="w", padx=22, pady=(17, 4))
            label(card, detail, 12, MUTED, wraplength=700, justify="left").pack(anchor="w", padx=22, pady=(0, 18))

    def close_app(self):
        if self.closing:
            return
        self.closing = True
        if self.desktop:
            self.desktop.stop()
        for dialog in list(self._dialogs):
            dialog.destroy()
        for timer in list(self._timers):
            self.cancel_timer(timer)
        if self.runtime:
            self.runtime.close()
        self.destroy()


class SceneEditor(ctk.CTkToplevel):
    def __init__(self, app, scene=None, *, copy=False):
        super().__init__(app)
        self.app = app
        self.original = scene.name if scene and not copy else None
        self.title("Editar escena" if self.original else "Crear escena personalizada")
        self.geometry("620x690")
        self.minsize(580, 600)
        self.configure(fg_color=app.bg)
        self.transient(app)
        self.grab_set()
        app._dialogs.add(self)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.grid(row=0, column=0, sticky="nsew", padx=20, pady=15)
        body.grid_columnconfigure(0, weight=1)
        label(body, "Diseñá tu ambiente", 25, bold=True).grid(row=0, column=0, sticky="w", pady=(0, 3))
        label(body, "Esta ventana guarda una escena; Aplicar envía los cambios a las luces.", 11, MUTED,
              wraplength=530).grid(row=1, column=0, sticky="w", pady=(0, 12))
        self.name = ctk.CTkEntry(body, height=38, placeholder_text="Nombre de la escena", fg_color=app.panel)
        self.name.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        if scene:
            self.name.insert(0, scene.name)
        self.controls = {}
        for index, bulb in enumerate(app.config_data.bulbs):
            setting = scene.lights[bulb.id] if scene else LightSetting(rgb=(145, 45, 255) if index == 0 else (0, 210, 255))
            frame = ctk.CTkFrame(body, fg_color=app.panel, corner_radius=14)
            frame.grid(row=index + 3, column=0, sticky="ew", pady=6)
            frame.grid_columnconfigure(0, weight=1)
            label(frame, bulb.name, 18, bold=True).grid(row=0, column=0, sticky="w", padx=18, pady=(13, 5))
            power = tk.BooleanVar(value=setting.power)
            ctk.CTkSwitch(frame, text="Encendida", variable=power, progress_color=app.accent,
                          text_color=TEXT).grid(row=0, column=1, padx=18, pady=(13, 5))
            level = tk.DoubleVar(value=setting.brightness)
            level_label = label(frame, f"Brillo: {setting.brightness}%", 12, MUTED)
            level_label.grid(row=1, column=0, sticky="w", padx=18)
            slider = ctk.CTkSlider(frame, from_=5, to=100, number_of_steps=95, variable=level,
                                    progress_color=app.accent,
                                    command=lambda value, target=level_label: target.configure(text=f"Brillo: {round(value)}%"))
            slider.grid(row=2, column=0, columnspan=2, sticky="ew", padx=18, pady=(5, 12))
            mode = OptionMenu(frame, values=["RGB", "Blanco cálido · 2700 K", "Blanco neutro · 4000 K", "Blanco frío · 6500 K"],
                                     fg_color=app.border, button_color=app.accent, height=34)
            mode.set("RGB" if setting.rgb else f"Blanco {'cálido' if setting.kelvin < 3500 else 'neutro' if setting.kelvin < 5500 else 'frío'} · {2700 if setting.kelvin < 3500 else 4000 if setting.kelvin < 5500 else 6500} K")
            if setting.kelvin and setting.kelvin not in (2700, 4000, 6500):
                custom_white = f"Blanco personalizado · {setting.kelvin} K"
                mode.configure(values=[*mode.cget("values"), custom_white])
                mode.set(custom_white)
            mode.grid(row=3, column=0, sticky="ew", padx=(18, 8), pady=(0, 16))
            color = setting.rgb or (255, 220, 170)
            button = app.button(frame, "Elegir RGB", lambda key=bulb.id: self.pick_color(key), width=130, height=34)
            button.configure(fg_color=hex_rgb(color), text_color="#10131E")
            button.grid(row=3, column=1, padx=(0, 18), pady=(0, 16))
            self.controls[bulb.id] = {"power": power, "level": level, "mode": mode, "rgb": color,
                                      "warm_white": setting.warm_white, "button": button}
        self.error = label(body, "", 12, RED, anchor="w", justify="left", wraplength=530)
        self.error.grid(row=5, column=0, sticky="ew", pady=5)
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=1, column=0, sticky="ew", padx=25, pady=(0, 20))
        app.button(actions, "Cancelar", self.destroy, secondary=True).pack(side="left")
        app.button(actions, "Guardar escena", self.save).pack(side="right")
        self._focus_timer = self.after(150, self.focus)

    def pick_color(self, key):
        control = self.controls[key]
        rgb, _ = colorchooser.askcolor(color=hex_rgb(control["rgb"]), parent=self)
        if rgb:
            control["rgb"] = tuple(round(channel) for channel in rgb)
            control["warm_white"] = None
            control["mode"].set("RGB")
            control["button"].configure(fg_color=hex_rgb(control["rgb"]))

    def save(self):
        try:
            lights = {}
            for key, control in self.controls.items():
                mode = control["mode"].get()
                kelvin = None if mode == "RGB" else int(mode.split()[-2])
                lights[key] = LightSetting(control["power"].get(), round(control["level"].get()),
                                            control["rgb"] if kelvin is None else None, kelvin,
                                            control["warm_white"] if kelvin is None else None)
            self.app.save_scene(Scene(self.name.get(), lights), self.original)
            self.destroy()
        except (ValueError, OSError) as error:
            self.error.configure(text=str(error))

    def destroy(self):
        if hasattr(self, "_focus_timer"):
            self.after_cancel(self._focus_timer)
        self.app._dialogs.discard(self)
        super().destroy()
