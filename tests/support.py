"""Temporary test directories with inherited Windows workspace permissions."""
from pathlib import Path
import shutil
from uuid import uuid4


class TestDirectory:
    def __init__(self):
        self.root = Path(__file__).resolve().parent
        self.path = self.root / f".tmp-{uuid4().hex}"
        self.path.mkdir()
        self.name = str(self.path)

    def cleanup(self):
        resolved = self.path.resolve()
        if resolved.parent != self.root or not resolved.name.startswith(".tmp-"):
            raise ValueError("Unsafe test cleanup path")
        shutil.rmtree(resolved)
