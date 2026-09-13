from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from transfer_engine import direct_plan, is_remote, remote_parts, result_message


class TransferPlans(unittest.TestCase):
    def test_windows_paths_are_not_remote_paths(self):
        self.assertFalse(is_remote("C:\\folder"))
        self.assertFalse(is_remote("G:/My Drive/folder"))
        self.assertTrue(is_remote("gdrive:folder/child"))

    def test_rejects_remote_self_and_nested_copies(self):
        for source, parent in [("gdrive:folder", "gdrive:"),
                               ("gdrive:folder", "gdrive:folder/sub")]:
            with self.assertRaises(ValueError):
                direct_plan(source, parent, 16, False, Path("test.log"))
        with self.assertRaises(ValueError):
            remote_parts("gdrive:a/../b")

    def test_cloud_copy_preserves_source_folder_and_skips_existing(self):
        with patch("transfer_engine.rclone_base", return_value=["rclone"]):
            plan = direct_plan("gdrive:source/板", "gdrive:target", 32, False, Path("test.log"))
            self.assertEqual(plan.target, "gdrive:target/板")
            self.assertEqual(plan.command[1:4], ["copy", "gdrive:source/板", "gdrive:target/板"])
            self.assertIn("--ignore-existing", plan.command)
            for forbidden in ("sync", "move", "purge", "delete", "--delete-excluded"):
                self.assertNotIn(forbidden, plan.command)

    def test_all_rclone_nonzero_exit_codes_are_failures(self):
        for code in (-1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10):
            self.assertIn("failed", result_message(code, "rclone"))
        self.assertIn("acknowledged", result_message(0, "rclone"))
        self.assertIn("mismatches", result_message(4, "robocopy"))
        self.assertIn("uploading", result_message(1, "robocopy"))
        self.assertIn("Stopped", result_message(0, "rclone", True))

    def test_real_rclone_copy_on_local_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, parent = root / "source", root / "out"
            source.mkdir()
            parent.mkdir()
            (source / "α file.txt").write_text("bytes preserved", encoding="utf-8")
            plan = direct_plan(source, parent, 4, False, root / "copy.log")
            result = subprocess.run(plan.command, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((Path(plan.target) / "α file.txt").read_text(encoding="utf-8"), "bytes preserved")


if __name__ == "__main__":
    unittest.main()
