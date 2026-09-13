"""Own each transfer's temporary files and remove them after the child exits."""
from pathlib import Path
import tempfile


class TransferScratch:
    def __init__(self):
        self._temporary = tempfile.TemporaryDirectory(prefix="parallel-copy-")
        self.root = Path(self._temporary.name)
        self.log = self.root / "transfer.log"
        self.cache = self.root / "cache"
        self.temp = self.root / "temp"
        self.cache.mkdir()
        self.temp.mkdir()

    def clean(self):
        self._temporary.cleanup()
