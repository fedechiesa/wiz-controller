import json
from pathlib import Path
import unittest
from unittest.mock import patch

from wiz_controller.models import AppConfig, BulbConfig, LightSetting, Scene, builtin_scenes
from wiz_controller.storage import Storage
from tests.support import TestDirectory


class ModelTests(unittest.TestCase):
    def test_defaults_use_documentation_ips(self):
        self.assertEqual([b.ip for b in AppConfig().bulbs], ["192.0.2.10", "192.0.2.11"])

    def test_invalid_addresses_and_duplicate_ips(self):
        for ip in ("bad", "192.0.2.999", "0.0.0.0", "255.255.255.255", "224.0.0.1"):
            with self.subTest(ip=ip), self.assertRaises(ValueError):
                BulbConfig("bulb1", "Luz", ip)
        with self.assertRaises(ValueError):
            AppConfig(bulbs=[BulbConfig("bulb1", "A", "192.0.2.12"), BulbConfig("bulb2", "B", "192.0.2.12")])

    def test_invalid_settings(self):
        for values in ({"brightness": 101}, {"brightness": True}, {"rgb": (1, 2)},
                       {"rgb": (0, -1, 2)}, {"rgb": None}, {"kelvin": 4000},
                       {"rgb": None, "kelvin": 1000}, {"power": "yes"}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                LightSetting(**values)

    def test_scenes_require_both_bulbs(self):
        with self.assertRaises(ValueError):
            Scene("Incomplete", {"bulb1": LightSetting()})

    def test_builtins_have_distinct_channels_and_native_white(self):
        scenes = builtin_scenes()
        self.assertNotEqual(scenes["Gaming"].lights["bulb1"].rgb, scenes["Gaming"].lights["bulb2"].rgb)
        self.assertEqual(scenes["Estudio"].lights["bulb1"].kelvin, 4000)
        self.assertIsNone(scenes["Relax"].lights["bulb1"].rgb)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = TestDirectory()
        self.addCleanup(self.temp.cleanup)
        self.storage = Storage(self.temp.name)

    def test_missing_files_use_defaults(self):
        self.assertEqual(self.storage.load_config(), AppConfig())
        self.assertEqual(self.storage.load_scenes(), {})

    def test_roundtrip_settings_and_scene_crud(self):
        config = AppConfig(startup_scene="Mi escena", scale=110, accent="Cian")
        self.storage.save_config(config)
        self.assertEqual(self.storage.load_config(), config)
        scene = Scene("Mi escena", {"bulb1": LightSetting(), "bulb2": LightSetting(False, 15, None, 2700)})
        self.storage.save_scenes({scene.name: scene})
        self.assertEqual(self.storage.load_scenes(), {scene.name: scene})
        updated = Scene("Actualizada", scene.lights)
        self.storage.save_scenes({updated.name: updated})
        self.assertEqual(list(self.storage.load_scenes()), ["Actualizada"])
        self.storage.save_scenes({})
        self.assertEqual(self.storage.load_scenes(), {})

    def test_invalid_json_is_preserved_and_not_silently_overwritten(self):
        path = Path(self.temp.name) / "config.json"
        path.write_text("{broken", encoding="utf-8")
        self.assertEqual(self.storage.load_config(), AppConfig())
        self.assertTrue(self.storage.warnings)
        with self.assertRaises(ValueError):
            self.storage.save_config(AppConfig())
        self.assertEqual(path.read_text(encoding="utf-8"), "{broken")

    def test_reserved_custom_scene_is_rejected(self):
        path = Path(self.temp.name) / "scenes.json"
        path.write_text(json.dumps({"version": 1, "scenes": [builtin_scenes()["Gaming"].to_dict()]}), encoding="utf-8")
        self.assertEqual(self.storage.load_scenes(), {})
        self.assertTrue(self.storage.warnings)

    def test_failed_atomic_replace_preserves_previous_file(self):
        self.storage.save_config(AppConfig())
        previous = (self.storage.directory / "config.json").read_bytes()
        with patch("wiz_controller.storage.os.replace", side_effect=OSError("disk error")):
            with self.assertRaises(OSError):
                self.storage.save_config(AppConfig(accent="Cian"))
        self.assertEqual((self.storage.directory / "config.json").read_bytes(), previous)
        self.assertEqual(list(self.storage.directory.glob("*.tmp")), [])
