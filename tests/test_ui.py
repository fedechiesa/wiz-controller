"""Opt-in real Tk widgets with a fake network worker: WIZ_GUI_TESTS=1."""
from concurrent.futures import Future
from dataclasses import replace
import os
from queue import Queue
import time
import unittest
from unittest.mock import patch

from tests.support import TestDirectory
from wiz_controller.lighting import BulbState
from wiz_controller.models import AppConfig, LightSetting, Scene
from wiz_controller.runtime import Result
from wiz_controller.storage import Storage
from wiz_controller.ui import SceneEditor, WizController
from wiz_controller.desktop_actions import DesktopAction


class FakeRuntime:
    def __init__(self):
        self.results = Queue()
        self.calls = []

    def submit(self, key, ip, token, action, **kwargs):
        self.calls.append((key, ip, token, action, kwargs))
        return Future()

    def close(self):
        pass


@unittest.skipUnless(os.environ.get("WIZ_GUI_TESTS") == "1", "Set WIZ_GUI_TESTS=1 to test desktop widgets")
class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = TestDirectory()
        cls.worker = FakeRuntime()
        cls.autostart_patch = patch("wiz_controller.ui.WindowsAutostart.enabled", return_value=False)
        cls.autostart_patch.start()
        cls.app = WizController(Storage(cls.temp.name), network_enabled=False, runtime=cls.worker)
        cls.app.update()

    @classmethod
    def tearDownClass(cls):
        cls.app.close_app()
        cls.autostart_patch.stop()
        cls.temp.cleanup()

    def setUp(self):
        app = self.app
        for dialog in list(app._dialogs):
            dialog.destroy()
        app.cancel_sliders()
        self.worker.calls.clear()
        app.inflight.clear()
        app.active_requests.clear()
        app.waiting.clear()
        app.states.clear()
        app.available.clear()
        app.errors.clear()
        app._toggle_pending = False
        app.desktop_errors.clear()
        app.custom_scenes.clear()
        app.config_data = AppConfig()
        app.show_page("Dashboard")
        app.update()

    def pump(self, duration=0.13):
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            self.app.update()
            time.sleep(0.005)

    def respond(self, index=0, state=None, error=None, reachable=True):
        key, ip, token, action, _ = self.worker.calls[index]
        self.worker.results.put(Result(key, ip, token, action, state, error, reachable))
        self.pump()

    def test_slider_debounce_sends_only_last_value(self):
        card = self.app.cards["bulb1"]
        for value in range(10, 90):
            card.change_brightness(value)
        self.assertEqual(self.worker.calls, [])
        self.pump(0.42)
        self.assertEqual(len(self.worker.calls), 1)
        self.assertEqual(self.worker.calls[0][4]["brightness"], 89)

    def test_failed_action_never_shows_confirmed_power(self):
        self.app.request("bulb1", "on")
        self.assertNotIn("bulb1", self.app.states)
        self.respond(error="Sin respuesta", reachable=False)
        card = self.app.cards["bulb1"]
        self.assertIn("Sin conexión", card.connection.cget("text"))
        self.assertNotIn("Confirmado", card.power_text.cget("text"))

    def test_success_uses_readback_and_independent_channel(self):
        self.app.request("bulb1", "on")
        self.respond(state=BulbState(True, 45, None, 2700))
        self.assertIn("Confirmado", self.app.cards["bulb1"].power_text.cget("text"))
        self.assertEqual(self.app.cards["bulb1"].level, 45)
        self.assertNotIn("bulb2", self.app.states)

    def test_pending_intents_are_bounded_and_color_survives_brightness(self):
        self.app.request("bulb1", "refresh")
        self.app.request("bulb1", "color", rgb=(0, 210, 255), brightness=70)
        for value in range(10, 95):
            self.app.request("bulb1", "brightness", brightness=value)
        self.assertEqual(len(self.worker.calls), 1)
        self.assertEqual(len(self.app.waiting), 1)
        self.respond(state=BulbState(False, 40, None, 2700))
        self.assertEqual(len(self.worker.calls), 2)
        self.assertEqual(self.worker.calls[-1][3], "color")
        self.assertEqual(self.worker.calls[-1][4], {"rgb": (0, 210, 255), "brightness": 94})

    def test_scene_cancels_delayed_slider(self):
        self.app.debounce("bulb1", 20)
        self.app.apply_scene("Gaming")
        self.assertFalse(self.app.slider_jobs)
        self.pump(0.42)
        self.assertEqual([call[3] for call in self.worker.calls], ["scene", "scene"])
        self.assertNotEqual(self.worker.calls[0][4]["setting"].rgb, self.worker.calls[1][4]["setting"].rgb)

    def test_global_brightness_and_color_keep_the_latest_level(self):
        self.app.master_brightness(86)
        self.app.cards["bulb1"].set_color((0, 210, 255))
        self.assertEqual(self.worker.calls[0][4]["brightness"], 86)
        self.assertNotIn("bulb1", self.app.slider_jobs)

    def test_on_does_not_discard_a_pending_color(self):
        self.app.request("bulb1", "refresh")
        self.app.request("bulb1", "color", rgb=(0, 210, 255), brightness=80)
        self.app.request("bulb1", "on")
        self.assertEqual(self.app.waiting["bulb1"][0], "color")
        self.assertEqual(self.app.waiting["bulb1"][1]["brightness"], 80)

    def test_large_scale_stacks_cards_in_a_narrow_window(self):
        import customtkinter as ctk
        self.app.geometry("1050x720")
        ctk.set_widget_scaling(1.25)
        self.pump(0.18)
        self.assertEqual(self.app.cards["bulb2"].grid_info()["row"], 1)
        ctk.set_widget_scaling(1)
        self.app.geometry("1220x900")
        self.pump(0.18)
        self.assertEqual(self.app.cards["bulb2"].grid_info()["row"], 0)

    def test_reconnect_recovers_after_failure(self):
        self.app.request("bulb1", "refresh")
        self.respond(error="Timeout", reachable=False)
        self.app.refresh_all()
        self.respond(1, state=BulbState(True, 80, (0, 210, 255), None))
        self.assertTrue(self.app.available["bulb1"])
        self.assertNotIn("bulb1", self.app.errors)

    def test_invalid_settings_do_not_replace_previous_config(self):
        self.app.show_page("Settings")
        entry = self.app.settings_bulbs["bulb1"][1]
        entry.delete(0, "end")
        entry.insert(0, "invalid")
        self.app.save_settings()
        self.assertEqual(self.app.config_data.bulbs[0].ip, "192.0.2.10")
        self.assertFalse(self.worker.calls)

    def test_old_result_after_ip_change_is_ignored(self):
        self.app.request("bulb1", "on")
        key, ip, token, action, _ = self.worker.calls[0]
        self.app.inflight[key] = (token + 1, "192.0.2.20")
        self.worker.results.put(Result(key, ip, token, action, BulbState(True, 70, None, 4000), reachable=True))
        self.pump()
        self.assertNotIn(key, self.app.states)
        self.assertEqual(self.app.inflight[key][1], "192.0.2.20")

    def test_scene_editor_create_rename_delete_and_startup_reference(self):
        editor = SceneEditor(self.app)
        self.app.update()
        editor.name.insert(0, "Mi stream")
        editor.controls["bulb2"]["power"].set(False)
        editor.controls["bulb1"]["level"].set(63)
        editor.save()
        self.assertFalse(self.app.custom_scenes["Mi stream"].lights["bulb2"].power)
        self.app.config_data = replace(self.app.config_data, startup_scene="Mi stream")
        original = self.app.custom_scenes["Mi stream"]
        self.app.save_scene(Scene("Renombrada", original.lights), original="Mi stream")
        self.assertEqual(self.app.config_data.startup_scene, "Renombrada")
        with patch("wiz_controller.ui.messagebox.askyesno", return_value=True):
            self.app.delete_scene("Renombrada")
        self.assertEqual(self.app.custom_scenes, {})
        self.assertIsNone(self.app.config_data.startup_scene)

    def test_settings_save_and_all_pages_render(self):
        for page in ("Escenas", "Integraciones", "Settings"):
            self.app.show_page(page)
            self.app.update()
        entry = self.app.settings_bulbs["bulb1"][1]
        entry.delete(0, "end")
        entry.insert(0, "192.0.2.20")
        self.app.scale_choice.set("110%")
        self.app.save_settings()
        self.assertEqual(self.app.config_data.bulbs[0].ip, "192.0.2.20")
        self.assertEqual(self.app.storage.load_config().bulbs[0].ip, "192.0.2.20")
        self.assertEqual(self.worker.calls[0][1], "192.0.2.20")
        self.assertEqual(self.app.config_data.scale, 110)
        self.app.show_page("Dashboard")

    def test_scene_editor_preserves_native_capture_and_custom_kelvin(self):
        scene = Scene("Captura", {"bulb1": LightSetting(True, 70, (121, 0, 255), None, 73),
                                  "bulb2": LightSetting(True, 45, None, 3200)})
        editor = SceneEditor(self.app, scene, copy=True)
        editor.save()
        self.assertEqual(self.app.custom_scenes["Captura"], scene)

    def test_desktop_scene_and_power_use_existing_runtime(self):
        self.app.integration_requests.put(DesktopAction("scene", "Gaming"))
        self.pump()
        self.assertEqual([call[3] for call in self.worker.calls], ["scene", "scene"])

    def test_same_scene_from_tray_does_not_queue_duplicate_active_commands(self):
        self.app.apply_scene("Gaming")
        self.app.handle_desktop_action(DesktopAction("scene", "Gaming"))
        self.assertFalse(self.app.waiting)
        self.assertEqual(len(self.worker.calls), 2)

    def test_explicit_scene_cancels_a_pending_toggle(self):
        self.app.toggle_lights()
        self.app.apply_scene("Gaming")
        self.assertFalse(self.app._toggle_pending)

    def test_toggle_reads_both_lights_before_sending_and_ignores_repeat(self):
        self.app.handle_desktop_action(DesktopAction("toggle"))
        self.app.handle_desktop_action(DesktopAction("toggle"))
        self.assertEqual([call[3] for call in self.worker.calls], ["refresh", "refresh"])
        self.respond(0, state=BulbState(False, 70, (0, 210, 255), None))
        self.assertEqual(len(self.worker.calls), 2)
        self.respond(1, state=BulbState(False, 70, (0, 210, 255), None))
        self.assertEqual([call[3] for call in self.worker.calls[2:]], ["on", "on"])

    def test_toggle_never_guesses_when_one_bulb_is_offline(self):
        self.app.toggle_lights()
        self.respond(0, state=BulbState(True, 70, (0, 210, 255), None))
        self.respond(1, error="Timeout", reachable=False)
        self.assertEqual(len(self.worker.calls), 2)
        self.assertFalse(self.app._toggle_pending)

    def test_x_hides_only_with_a_ready_tray(self):
        from types import SimpleNamespace
        desktop = SimpleNamespace(tray_ready=True)
        self.app.desktop = desktop
        try:
            self.app.on_window_close()
            self.app.update()
            self.assertEqual(self.app.state(), "withdrawn")
            self.assertFalse(self.app.closing)
            self.app.handle_desktop_action(DesktopAction("show"))
            self.app.update()
            self.assertEqual(self.app.state(), "normal")
            desktop.tray_ready = False
            with patch.object(self.app, "close_app") as close:
                self.app.on_window_close()
                close.assert_called_once()
        finally:
            self.app.desktop = None

    def test_quit_always_exits_even_with_tray_preference(self):
        with patch.object(self.app, "close_app") as close:
            self.app.handle_desktop_action(DesktopAction("quit"))
            close.assert_called_once()
