"""GUI lifecycle checks. Run outside a sandbox that blocks installed Tcl files."""
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from parallel_copy import CopyApp
from drive_picker import DrivePicker
from transfer_engine import TransferPlan
import subprocess


class CopyWindowTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(str(error))
        self.root.withdraw()

    def tearDown(self):
        if hasattr(self, "root"):
            self.root.destroy()

    def test_start_copy_reaches_completed_state_and_restores_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = root / "source", root / "target"
            source.mkdir()
            target.mkdir()
            (source / "test.txt").write_text("GUI fixture")
            app = CopyApp(self.root, str(source), str(target))
            app.start()
            scratch_root = app.scratch.root
            deadline = time.monotonic() + 10
            while app.process is not None and time.monotonic() < deadline:
                self.root.update()
                time.sleep(.01)
            self.assertIsNone(app.process)
            self.assertEqual((target / "source" / "test.txt").read_text(), "GUI fixture")
            self.assertIn("finished", app.status.get())
            self.assertEqual(str(app.start_button["state"]), "normal")
            self.assertEqual(str(app.stop_button["state"]), "disabled")
            self.assertFalse(scratch_root.exists())

    def test_invalid_input_shows_error_without_starting_process(self):
        app = CopyApp(self.root)
        with patch("parallel_copy.messagebox.showerror") as show:
            app.start()
        show.assert_called_once()
        self.assertIsNone(app.process)
        self.assertIsNone(app.scratch)

    def test_cloud_paths_disable_windows_resume_option(self):
        app = CopyApp(self.root)
        app.source.set("gdrive:example")
        app.parent.set("gdrive:destination")
        self.assertEqual(str(app.resume_checkbox["state"]), "disabled")
        self.assertIn("gdrive:destination/example", app.destination_label.get())

    def test_stop_terminates_child_and_restores_start(self):
        with tempfile.TemporaryDirectory() as directory:
            app = CopyApp(self.root, directory, directory)
            command = [sys.executable, "-c", "import time; time.sleep(30)"]
            with patch("parallel_copy.copy_command", return_value=(command, Path(directory))):
                app.start()
            process = app.process
            scratch_root = app.scratch.root
            app.stop()
            deadline = time.monotonic() + 5
            while app.process is not None and time.monotonic() < deadline:
                self.root.update()
                time.sleep(.01)
            self.assertIsNotNone(process.poll())
            self.assertIsNone(app.process)
            self.assertIn("Stopped", app.status.get())
            self.assertEqual(str(app.start_button["state"]), "normal")
            self.assertFalse(scratch_root.exists())

    def test_closing_picker_stops_its_pending_listing(self):
        command = [sys.executable, "-c", "import time; time.sleep(30)"]
        with patch("drive_picker.rclone_base", return_value=command):
            picker = DrivePicker(self.root, lambda _: None)
            deadline = time.monotonic() + 5
            while picker.process is None and time.monotonic() < deadline:
                self.root.update()
                time.sleep(.01)
            process = picker.process
            self.assertIsNotNone(process)
            picker.close()
            process.wait(timeout=5)
            self.assertIsNotNone(process.poll())

    def test_failed_auth_launch_cleans_its_scratch(self):
        app = CopyApp(self.root)
        with patch("parallel_copy.filedialog.askopenfilename", return_value="fixture.json"), \
             patch("parallel_copy.subprocess.Popen", side_effect=OSError("fixture failure")), \
             patch("parallel_copy.messagebox.showerror"):
            app.connect_drive()
        self.assertIsNone(app.auth_scratch)
        self.assertIsNone(app.auth_process)

    def test_stop_many_file_route_terminates_grandchild_and_cleans_scratch(self):
        with tempfile.TemporaryDirectory() as directory:
            pid_path = Path(directory) / "child.pid"
            script = "import subprocess,sys,time,pathlib; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); pathlib.Path(sys.argv[1]).write_text(str(p.pid)); time.sleep(30)"
            command = [sys.executable, "-c", script, str(pid_path)]
            app = CopyApp(self.root, "gdrive:fixture", directory)
            def plan(source, parent, workers, replace, log, **kwargs):
                return TransferPlan(command, directory, "folders", log, "fixture")
            with patch("parallel_copy.direct_plan", side_effect=plan):
                app.start()
            scratch_root = app.scratch.root
            deadline = time.monotonic() + 5
            while not pid_path.exists() and time.monotonic() < deadline:
                self.root.update()
                time.sleep(.02)
            self.assertTrue(pid_path.exists())
            child_pid = int(pid_path.read_text())
            app.stop()
            while app.process is not None and time.monotonic() < deadline:
                self.root.update()
                time.sleep(.02)
            self.assertIsNone(app.process)
            self.assertFalse(scratch_root.exists())
            result = subprocess.run(["tasklist", "/FI", f"PID eq {child_pid}", "/FO", "CSV", "/NH"],
                                    capture_output=True, text=True)
            self.assertNotIn(f'"{child_pid}"', result.stdout)


if __name__ == "__main__":
    unittest.main()
