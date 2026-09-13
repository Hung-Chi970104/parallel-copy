import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from parallel_copy import copy_command


@unittest.skipUnless(shutil.which("robocopy"), "Windows Robocopy required")
class ParallelCopyTests(unittest.TestCase):
    def test_real_copy_preserves_extras_and_supports_overwrite_choice(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, parent = root / "board ü", root / "destination"
            source.mkdir()
            parent.mkdir()
            (source / "empty").mkdir()
            payload = bytes(range(256)) * 4096
            (source / "data.bin").write_bytes(payload)
            (source / "existing.txt").write_text("new content", encoding="utf-8")
            target = parent / source.name
            target.mkdir()
            (target / "extra.txt").write_text("keep")
            (target / "existing.txt").write_text("old")
            for replace in (False, True):
                command, actual = copy_command(source, parent, 8, replace, True, root / "copy.log")
                result = subprocess.run(command, capture_output=True, timeout=30)
                self.assertLess(result.returncode, 8)
                self.assertEqual(actual, target)
                self.assertEqual((target / "extra.txt").read_text(), "keep")
                self.assertEqual((target / "existing.txt").read_text(), "new content" if replace else "old")
                self.assertEqual(hashlib.sha256((target / "data.bin").read_bytes()).digest(), hashlib.sha256(payload).digest())
                self.assertTrue((target / "empty").is_dir())
                self.assertTrue((source / "data.bin").exists())
            command, _ = copy_command(source, parent, 8, True, True, root / "again.log")
            result = subprocess.run(command, capture_output=True, timeout=30)
            self.assertEqual(result.returncode & 1, 0, "Unchanged files should be skipped")

    def test_rejects_self_copy_and_recursive_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            for parent in (root, source):
                with self.assertRaises(ValueError):
                    copy_command(source, parent, 16, False, False, root / "copy.log")


if __name__ == "__main__":
    unittest.main()
