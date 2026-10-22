from dataclasses import replace
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from tests.support import TestDirectory
from wiz_controller import paths
from wiz_controller.integrations import WindowsAutostart
from wiz_controller.models import AppConfig, Scene, LightSetting
from wiz_controller.storage import Storage


class PathTests(unittest.TestCase):
    def test_persistent_path_uses_localappdata_and_never_bundle(self):
        with patch.dict("os.environ", {"LOCALAPPDATA": str(Path("C:/Users/Example/AppData/Local"))}), patch.object(paths.sys, "_MEIPASS", "C:/Temp/bundle", create=True):
            self.assertEqual(paths.user_data_directory(), Path("C:/Users/Example/AppData/Local/WiZController"))

    def test_frozen_resources_and_command_use_different_roots(self):
        with patch.object(paths.sys, "frozen", True, create=True), patch.object(paths.sys, "_MEIPASS", "C:/Temp/bundle", create=True), patch.object(paths.sys, "executable", "C:/Program Files/WiZ/WiZController.exe"):
            self.assertEqual(paths.resource_path("assets/wiz-controller.ico"), Path("C:/Temp/bundle/assets/wiz-controller.ico"))
            self.assertEqual(paths.legacy_data_directory(), Path("C:/Program Files/WiZ/data"))
            self.assertEqual(paths.launch_arguments(True), [str(Path("C:/Program Files/WiZ/WiZController.exe")), "--background"])
            command = WindowsAutostart.command()
            self.assertNotIn("python", command.lower())
            self.assertNotIn("main.py", command)
            self.assertIn("--background", command)

    def test_development_launch_does_not_depend_on_cwd(self):
        with patch.object(paths.sys, "frozen", False, create=True):
            args = paths.launch_arguments()
            self.assertTrue(Path(args[0]).is_absolute())
            self.assertTrue(Path(args[1]).is_absolute())
            self.assertEqual(Path(args[1]).name, "main.py")


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TestDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Storage(Path(self.temp.name) / "old")
        self.target = Storage(Path(self.temp.name) / "persistent")

    def test_migration_copies_valid_config_and_scenes_without_deleting_source(self):
        config = AppConfig(startup_scene="Mi escena", accent="Cian")
        scene = Scene("Mi escena", {"bulb1": LightSetting(), "bulb2": LightSetting(power=False)})
        self.source.save_config(config)
        self.source.save_scenes({scene.name: scene})
        before = {file.name: file.read_bytes() for file in self.source.directory.iterdir()}
        (self.source.directory / "controller.log").write_text("private diagnostics")
        self.assertEqual(self.target.migrate_legacy(self.source.directory), ["config.json", "scenes.json"])
        self.assertEqual(self.target.load_config(), config)
        self.assertEqual(self.target.load_scenes(), {scene.name: scene})
        self.assertFalse((self.target.directory / "controller.log").exists())
        self.assertEqual(before, {name: (self.source.directory / name).read_bytes() for name in before})

    def test_existing_destination_is_never_overwritten(self):
        self.source.save_config(AppConfig(accent="Cian"))
        self.target.save_config(AppConfig(accent="Magenta"))
        before = (self.target.directory / "config.json").read_bytes()
        self.assertEqual(self.target.migrate_legacy(self.source.directory), [])
        self.assertEqual((self.target.directory / "config.json").read_bytes(), before)

    def test_invalid_source_is_preserved_and_reported(self):
        self.source.directory.mkdir()
        (self.source.directory / "config.json").write_text("{broken")
        self.assertEqual(self.target.migrate_legacy(self.source.directory), [])
        self.assertTrue(self.target.warnings)
        self.assertFalse((self.target.directory / "config.json").exists())
        self.assertEqual((self.source.directory / "config.json").read_text(), "{broken")

    def test_missing_source_and_same_source_are_noops(self):
        self.assertEqual(self.target.migrate_legacy(self.source.directory), [])
        self.assertEqual(self.target.migrate_legacy(self.target.directory), [])

    def test_old_version_config_gets_new_preferences_without_losing_devices(self):
        value = AppConfig().to_dict()
        for key in ("tray_enabled", "close_to_tray", "hotkeys_enabled", "hotkeys"):
            value.pop(key)
        self.source.directory.mkdir()
        (self.source.directory / "config.json").write_text(json.dumps(value))
        self.target.migrate_legacy(self.source.directory)
        loaded = self.target.load_config()
        self.assertEqual(loaded.bulbs, AppConfig().bulbs)
        self.assertTrue(loaded.tray_enabled)
        self.assertFalse(loaded.hotkeys_enabled)

    def test_preferences_roundtrip_and_invalid_bindings_are_rejected(self):
        config = AppConfig(tray_enabled=False, close_to_tray=False, hotkeys_enabled=True,
                           hotkeys={**AppConfig().hotkeys, "Gaming": "Ctrl+Shift+G"})
        self.target.save_config(config)
        self.assertEqual(self.target.load_config(), config)
        with self.assertRaises(ValueError):
            replace(config, hotkeys={**config.hotkeys, "Gaming": "Ctrl+Alt+F12"})
