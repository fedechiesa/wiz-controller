"""Opt-in native API tests. No bulb commands, registry changes or keyboard hooks."""
import os
from queue import Queue
import sys
import subprocess
import unittest
from unittest.mock import patch
from uuid import uuid4

from wiz_controller.desktop_actions import ActionBus, DesktopAction
from wiz_controller.hotkeys import GlobalHotkeys, WinHotkeyAPI, WM_HOTKEY, parse_hotkey
from wiz_controller.instance import SingleInstance
from wiz_controller.tray import SystemTray


@unittest.skipUnless(sys.platform == "win32" and os.environ.get("WIZ_NATIVE_TESTS") == "1",
                     "Set WIZ_NATIVE_TESTS=1 on a Windows desktop")
class WindowsNativeTests(unittest.TestCase):
    def test_another_python_process_signals_restore_instead_of_starting_again(self):
        identifier = uuid4().hex
        first = SingleInstance()
        first.MUTEX = rf"Local\WiZController.ProcessTest.{identifier}"
        first.EVENT = rf"Local\WiZController.ProcessRestore.{identifier}"
        try:
            self.assertTrue(first.acquire())
            code = ("import sys; from wiz_controller.instance import SingleInstance; "
                    "instance=SingleInstance(); instance.MUTEX,instance.EVENT=sys.argv[1:]; "
                    "acquired=instance.acquire(); instance.close(); raise SystemExit(2 if acquired else 0)")
            child = subprocess.run([sys.executable, "-c", code, first.MUTEX, first.EVENT],
                                   capture_output=True, timeout=5)
            self.assertEqual(child.returncode, 0, child.stderr.decode(errors="replace"))
            self.assertTrue(first.consume_restore())
        finally:
            first.close()

    def test_native_registration_conflict_message_dispatch_and_release(self):
        bindings = {"Gaming": "Ctrl+Alt+Shift+F9", "Streaming": "Ctrl+Alt+Shift+F10",
                    "Relax": "Ctrl+Alt+Shift+F11", "Alternar luces": "Ctrl+Alt+Shift+F8"}
        queue = Queue()
        hotkeys = GlobalHotkeys(bindings, ActionBus(queue))
        probe = WinHotkeyAPI()
        probe.prepare()
        probe_registered = False
        try:
            hotkeys.start()
            self.assertTrue(hotkeys.ready.wait(3))
            self.assertEqual(len(hotkeys.registered), 4, "One of the native test combinations is in use")
            self.assertFalse(probe.register(222, *parse_hotkey(bindings["Gaming"])))
            self.assertEqual(queue.get(timeout=2).kind, "status")
            self.assertTrue(hotkeys.api.user32.PostThreadMessageW(hotkeys.thread_id, WM_HOTKEY, 1, 0))
            self.assertEqual(queue.get(timeout=2), DesktopAction("scene", "Gaming"))
            hotkeys.stop()
            probe_registered = probe.register(222, *parse_hotkey(bindings["Gaming"]))
            self.assertTrue(probe_registered, "The hotkey was not released")
        finally:
            hotkeys.stop()
            if probe_registered:
                probe.unregister(222)

    def test_native_single_instance_restores_first_and_releases_handles(self):
        identifier = uuid4().hex
        with patch.object(SingleInstance, "MUTEX", rf"Local\WiZController.Test.{identifier}"), patch.object(SingleInstance, "EVENT", rf"Local\WiZController.TestRestore.{identifier}"):
            first, second, third = SingleInstance(), SingleInstance(), SingleInstance()
            try:
                self.assertTrue(first.acquire())
                self.assertFalse(second.acquire())
                self.assertTrue(first.consume_restore())
                self.assertFalse(first.consume_restore())
                first.close()
                self.assertTrue(third.acquire())
            finally:
                first.close()
                second.close()
                third.close()

    def test_native_tray_can_show_and_stop(self):
        tray = SystemTray(ActionBus(Queue()))
        try:
            tray.start()
            self.assertTrue(tray.ready.wait(4), "The Windows notification icon was not initialized")
            self.assertFalse(tray.failed.is_set())
        finally:
            tray.stop()
        self.assertFalse(tray.thread.is_alive())

    def test_native_tray_startup_failure_releases_pystray_setup_thread(self):
        import pystray
        tray = SystemTray(ActionBus(Queue()))
        with patch.object(pystray.Icon, "_create_window", side_effect=OSError("native startup test failure")):
            tray.start()
            tray.thread.join(4)
            self.assertTrue(tray.failed.is_set())
            self.assertFalse(tray.thread.is_alive())
            self.assertFalse(tray.icon._setup_thread.is_alive())
        tray.stop()
