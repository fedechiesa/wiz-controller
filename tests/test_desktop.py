from dataclasses import replace
from queue import Queue
import threading
import time
from types import SimpleNamespace
import unittest

from wiz_controller.desktop import DesktopServices
from wiz_controller.desktop_actions import ActionBus, DesktopAction
from wiz_controller.hotkeys import DEFAULT_HOTKEYS, GlobalHotkeys, parse_hotkey, validate_bindings
from wiz_controller.models import AppConfig
from wiz_controller.tray import SystemTray, TRAY_ITEMS


class ActionTests(unittest.TestCase):
    def test_duplicate_actions_from_tray_and_keyboard_are_coalesced(self):
        queue = Queue()
        moment = [10.0]
        bus = ActionBus(queue, clock=lambda: moment[0])
        self.assertTrue(bus.emit("scene", "Gaming"))
        self.assertFalse(bus.emit("scene", "Gaming"))
        self.assertTrue(bus.emit("off"))
        moment[0] += 1
        self.assertTrue(bus.emit("scene", "Gaming"))
        bus.close()
        self.assertFalse(bus.emit("on"))
        self.assertEqual(queue.qsize(), 3)

    def test_tray_callbacks_send_expected_actions_without_tk(self):
        queue = Queue()
        tray = SystemTray(ActionBus(queue))
        for title, kind, value in TRAY_ITEMS:
            tray.callback(kind, value)()
            self.assertEqual(queue.get_nowait(), DesktopAction(kind, value), title)
        tray.stop()
        tray.callback("on")()
        self.assertTrue(queue.empty())

    def test_tray_run_and_stop_release_the_worker(self):
        class Icon:
            def __init__(self, *args):
                self.done = threading.Event()
            def run(self, setup):
                setup(self)
                self.done.wait(2)
            def stop(self):
                self.done.set()
        module = SimpleNamespace(Icon=Icon, MenuItem=lambda *args, **kwargs: args, Menu=lambda *args: args)
        tray = SystemTray(ActionBus(Queue()), module, image_loader=lambda: object())
        tray.start()
        self.assertTrue(tray.ready.wait(1))
        tray.stop()
        self.assertFalse(tray.thread.is_alive())
        self.assertFalse(tray.ready.is_set())

    def test_tray_failure_is_reported_and_never_marked_ready(self):
        queue = Queue()
        def fail():
            raise OSError("icon unavailable")
        tray = SystemTray(ActionBus(queue), module=object(), image_loader=fail)
        tray.start()
        tray.thread.join(2)
        self.assertTrue(tray.failed.is_set())
        self.assertFalse(tray.ready.is_set())
        self.assertEqual(queue.get_nowait().kind, "error")
        tray.stop()


class FakeHotkeyAPI:
    def __init__(self, conflict=None):
        self.messages = Queue()
        self.registrations, self.released = [], []
        self.conflict = conflict
    def prepare(self):
        return 123
    def register(self, identifier, modifiers, key):
        self.registrations.append((identifier, modifiers, key))
        return identifier != self.conflict
    def unregister(self, identifier):
        self.released.append(identifier)
    def next_hotkey(self):
        return self.messages.get(timeout=2)
    def wake(self, thread_id):
        self.messages.put(None)


class HotkeyTests(unittest.TestCase):
    def test_parse_modifiers_case_and_norepeat(self):
        self.assertEqual(parse_hotkey(" ctrl + ALT + f9 "), (0x4003, 0x78))
        self.assertEqual(parse_hotkey("Ctrl+Shift+G"), (0x4006, ord("G")))

    def test_invalid_combinations_and_reserved_f12(self):
        for text in ("F9", "Ctrl+Ctrl+G", "Win+G", "Shift+G", "Ctrl+Alt+F12", "Ctrl+Alt+F99", "Ctrl+Alt+", "Ctrl+ñ"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_hotkey(text)

    def test_duplicate_bindings_are_rejected_even_in_different_order(self):
        bindings = {**DEFAULT_HOTKEYS, "Streaming": "Alt+Ctrl+F9"}
        with self.assertRaises(ValueError):
            validate_bindings(bindings)

    def test_registration_conflicts_do_not_disable_other_shortcuts(self):
        queue = Queue()
        api = FakeHotkeyAPI(conflict=2)
        hotkeys = GlobalHotkeys(DEFAULT_HOTKEYS, ActionBus(queue), api)
        hotkeys.start()
        self.assertTrue(hotkeys.ready.wait(1))
        self.assertEqual(len(hotkeys.registered), 3)
        error = queue.get_nowait()
        self.assertEqual(error.kind, "error")
        self.assertIn("Streaming", error.value)
        queue.get_nowait()  # Registration summary.
        api.messages.put(1)
        self.assertEqual(queue.get(timeout=1), DesktopAction("scene", "Gaming"))
        api.messages.put(4)
        self.assertEqual(queue.get(timeout=1), DesktopAction("toggle"))
        hotkeys.stop()
        self.assertEqual(api.released, [1, 3, 4])
        self.assertFalse(hotkeys.thread.is_alive())

    def test_stop_during_initialization_unregisters_every_success(self):
        api = FakeHotkeyAPI()
        hotkeys = GlobalHotkeys(DEFAULT_HOTKEYS, ActionBus(Queue()), api)
        hotkeys.start()
        hotkeys.stop()
        self.assertFalse(hotkeys.thread.is_alive())
        self.assertEqual(set(api.released), {identifier for identifier, _, _ in api.registrations})


class SupervisorTests(unittest.TestCase):
    def test_reconfigure_and_shutdown_are_serialized(self):
        events = []
        configured = threading.Event()
        class Tray:
            def __init__(self, bus):
                self.ready, self.failed = threading.Event(), threading.Event()
            def start(self):
                events.append("tray.start")
                self.ready.set()
            def stop(self):
                events.append("tray.stop")
        class Hotkeys:
            def __init__(self, bindings, bus):
                pass
            def start(self):
                events.append("keys.start")
                configured.set()
            def stop(self):
                events.append("keys.stop")
        desktop = DesktopServices(Queue(), Tray, Hotkeys)
        desktop.configure(AppConfig(hotkeys_enabled=True))
        self.assertTrue(configured.wait(2))
        self.assertTrue(desktop.tray_ready)
        desktop.configure(AppConfig(tray_enabled=False, hotkeys_enabled=False))
        desktop.stop()
        self.assertTrue(desktop.wait(2))
        self.assertEqual(events.count("tray.start"), 1)
        self.assertEqual(events.count("tray.stop"), 1)
        self.assertEqual(events.count("keys.start"), 1)
        self.assertEqual(events.count("keys.stop"), 1)
