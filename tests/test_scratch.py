from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scratch import TransferScratch


class ScratchCleanup(unittest.TestCase):
    def test_cleans_owned_log_cache_and_temp_without_touching_neighbor(self):
        with tempfile.TemporaryDirectory() as other:
            unrelated = Path(other) / "keep.txt"
            unrelated.write_text("keep")
            scratch = TransferScratch()
            root = scratch.root
            scratch.log.write_text("log")
            (scratch.cache / "cache.bin").write_bytes(b"cache")
            (scratch.temp / "partial.bin").write_bytes(b"partial")
            scratch.clean()
            self.assertFalse(root.exists())
            self.assertEqual(unrelated.read_text(), "keep")
