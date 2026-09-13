from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from folder_parallel import run
from benchmark import manifest


class FolderCopies(unittest.TestCase):
    def test_disjoint_batches_handle_regex_characters_and_root_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, parent = root / "source", root / "out"
            source.mkdir()
            parent.mkdir()
            for name in ("a [x]", "b {stuff}", "Unicode 板", "d.plus+"):
                folder = source / name
                folder.mkdir()
                (folder / "empty").mkdir()
                (folder / "file.txt").write_text(name, encoding="utf-8")
            (source / "root [x].txt").write_text("root")
            target = Path(run(str(source), str(parent), 8, 2, False, root / "groups.log", strategy="groups"))
            self.assertEqual(manifest(source), manifest(target))
            for name in ("a [x]", "b {stuff}", "Unicode 板", "d.plus+"):
                self.assertTrue((target / name / "empty").is_dir())
            self.assertEqual(list(root.glob("*.filter")), [])

    def test_parallel_folders_preserve_tree_and_existing_file_choices(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, parent = root / "source", root / "target"
            source.mkdir()
            parent.mkdir()
            for name in ("a", "b", "Unicode 板"):
                folder = source / name
                folder.mkdir()
                (folder / "empty").mkdir()
                (folder / "file.txt").write_text(name, encoding="utf-8")
            (source / "root.txt").write_text("root file")
            target = Path(run(str(source), str(parent), 8, 2, False, root / "run.log"))
            self.assertEqual(manifest(source), manifest(target))
            self.assertTrue((target / "a" / "empty").is_dir())
            (target / "extra.txt").write_text("keep")
            (target / "a" / "file.txt").write_text("existing")
            run(str(source), str(parent), 8, 2, False, root / "keep.log")
            self.assertEqual((target / "a" / "file.txt").read_text(), "existing")
            run(str(source), str(parent), 8, 2, True, root / "replace.log")
            self.assertEqual((target / "a" / "file.txt").read_text(), "a")
            self.assertEqual((target / "extra.txt").read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
