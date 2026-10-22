"""Small, atomic JSON stores. Invalid files are preserved for recovery."""
import json
import logging
import os
from pathlib import Path
import tempfile

from .models import AppConfig, Scene, builtin_scenes

LOGGER = logging.getLogger(__name__)


class Storage:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else Path(__file__).resolve().parent.parent / "data"
        self.warnings = []
        self.protected = set()

    def _read(self, filename, fallback, decode):
        path = self.directory / filename
        if not path.exists():
            return fallback()
        try:
            return decode(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            LOGGER.warning("Cannot load %s: %s", path, error)
            self.warnings.append(f"No se pudo leer {filename}. Se usan valores iniciales; conservá o corregí el archivo.")
            self.protected.add(filename)
            return fallback()

    def _write(self, filename, value):
        if filename in self.protected:
            raise ValueError(f"{filename} es inválido. Renombralo o corregilo antes de guardar para no perder tus datos.")
        self.directory.mkdir(parents=True, exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.directory,
                                             suffix=".tmp", delete=False) as handle:
                temp_path = Path(handle.name)
                json.dump(value, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.directory / filename)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def load_config(self):
        return self._read("config.json", AppConfig, AppConfig.from_dict)

    def save_config(self, config):
        self._write("config.json", config.to_dict())

    def load_scenes(self):
        def decode(value):
            if value["version"] != 1 or not isinstance(value["scenes"], list):
                raise ValueError("Archivo de escenas inválido.")
            scenes = [Scene.from_dict(scene) for scene in value["scenes"]]
            names = [scene.name.casefold() for scene in scenes]
            if len(names) != len(set(names)) or set(names) & {name.casefold() for name in builtin_scenes()}:
                raise ValueError("Nombres de escenas duplicados o reservados.")
            return {scene.name: scene for scene in scenes}
        return self._read("scenes.json", dict, decode)

    def save_scenes(self, scenes):
        self._write("scenes.json", {"version": 1, "scenes": [scene.to_dict() for scene in scenes.values()]})
