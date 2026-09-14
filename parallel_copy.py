"""Windows folder-copy GUI. Run python parallel_copy.py (no pip packages).

Uses Windows Robocopy for parallel transfers; never mirrors or deletes files.
Destination is a parent folder: the source folder's name is appended.
"""
import sys
sys.dont_write_bytecode = True
import argparse
import codecs
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import threading
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from transfer_engine import CONFIG, ROOT, PRESETS, direct_plan, is_remote, rclone_base, result_message
from drive_picker import DrivePicker
from scratch import TransferScratch
from folder_parallel import kill_tree


def copy_command(source, parent, workers, replace, resumable, log):
    if not str(source).strip() or not str(parent).strip():
        raise ValueError("Choose both folders.")
    source = Path(str(source).strip()).expanduser().resolve()
    parent = Path(str(parent).strip()).expanduser().resolve()
    if not source.is_dir():
        raise ValueError("The source folder is missing or inaccessible.")
    if not source.name:
        raise ValueError("Choose a folder, rather than an entire drive.")
    if not parent.is_dir():
        raise ValueError("Choose an existing destination parent folder.")
    target = (parent / source.name).resolve()
    if (source == target or source in target.parents or target in source.parents):
        raise ValueError("Source and destination must not contain each other.")
    if target.exists() and not target.is_dir():
        raise ValueError("A file already occupies the destination folder path.")
    workers = int(workers)
    if not 1 <= workers <= 128:
        raise ValueError("Parallel transfers must be between 1 and 128.")
    executable = shutil.which("robocopy")
    if not executable:
        raise ValueError("This app requires Windows Robocopy.")
    args = [executable, str(source), str(target), "/E", f"/MT:{workers}",
            "/R:2", "/W:2", "/COPY:DAT", "/DCOPY:DAT", "/XJ", "/NP",
            f"/UNILOG:{log}"]
    if not replace:
        args.extend(["/XC", "/XN", "/XO"])
    if resumable:
        args.append("/Z")
    return args, target


class CopyApp:
    def __init__(self, root, source="", parent=""):
        self.root = root
        self.process = None
        self.log = None
        self.log_offset = 0
        self.cancelled = False
        self.target = None
        self.backend = "robocopy"
        self.cloud_route = False
        self.scratch = None
        self.auth_process = None
        self.auth_scratch = None
        root.title("Parallel Folder Copy")
        root.geometry("940x720")
        root.minsize(650, 520)
        root.protocol("WM_DELETE_WINDOW", self.close)
        frame = ttk.Frame(root, padding=20)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(9, weight=1)
        ttk.Label(frame, text="Parallel Folder Copy", font=("Segoe UI", 19, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        ttk.Label(frame, text="Choose Local for Windows folders, or Drive for direct cloud transfers and server-side copies.").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(0, 18))
        self.source = tk.StringVar(value=source)
        self.parent = tk.StringVar(value=parent)
        self.inputs = []
        for row, label, variable in [(2, "Source folder", self.source),
                                     (3, "Copy into", self.parent)]:
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12))
            entry = ttk.Entry(frame, textvariable=variable)
            entry.grid(row=row, column=1, sticky="ew", pady=5)
            browse_bar = ttk.Frame(frame)
            browse_bar.grid(row=row, column=2, padx=(8, 0))
            button = ttk.Button(browse_bar, text="Local…", command=lambda v=variable: self.browse(v))
            button.pack(side="left")
            cloud = ttk.Button(browse_bar, text="Drive…", command=lambda v=variable: self.browse_drive(v))
            cloud.pack(side="left", padx=(4, 0))
            self.inputs.extend([entry, button, cloud])
        self.destination_label = tk.StringVar()
        ttk.Label(frame, textvariable=self.destination_label, wraplength=730).grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(5, 14))
        for variable in (self.source, self.parent):
            variable.trace_add("write", self.preview)
        self.preview()
        options = ttk.Frame(frame)
        options.grid(row=5, column=0, columnspan=3, sticky="w")
        ttk.Label(options, text="Parallel transfers").pack(side="left")
        self.workers = tk.StringVar(value="16")
        spin = ttk.Spinbox(options, from_=1, to=128, width=5, textvariable=self.workers)
        spin.pack(side="left", padx=10)
        ttk.Label(options, text="More can be slower. See PERFORMANCE.md for measured settings.").pack(side="left")
        self.inputs.append(spin)
        self.replace = tk.BooleanVar(value=False)
        self.resumable = tk.BooleanVar(value=True)
        checks = ttk.Frame(frame)
        checks.grid(row=6, column=0, columnspan=3, sticky="w", pady=10)
        presets = ttk.Frame(checks)
        presets.pack(anchor="w", pady=(0, 6))
        ttk.Label(presets, text="Cloud preset").pack(side="left", padx=(0, 10))
        self.profile = tk.StringVar(value="Small files")
        preset = ttk.Combobox(presets, textvariable=self.profile, values=["Small files", "Many small files", "Large files"],
                              state="readonly", width=18)
        preset.pack(side="left")
        preset.bind("<<ComboboxSelected>>", lambda _: self.workers.set(self.default_workers()))
        self.preset_widget = preset
        self.inputs.append(preset)
        for label, variable in [("Replace existing files when different", self.replace),
                                ("Resume interrupted files (Windows folder copies only)", self.resumable)]:
            checkbox = ttk.Checkbutton(checks, text=label, variable=variable)
            checkbox.pack(anchor="w", pady=2)
            self.inputs.append(checkbox)
            if variable is self.resumable:
                self.resume_checkbox = checkbox
        buttons = ttk.Frame(frame)
        buttons.grid(row=7, column=0, columnspan=3, sticky="ew", pady=8)
        self.start_button = ttk.Button(buttons, text="Start copy", command=self.start)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(buttons, text="Stop", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=8)
        self.connect_button = ttk.Button(buttons, text="Connect Drive…", command=self.connect_drive)
        self.connect_button.pack(side="left", padx=8)
        self.inputs.append(self.connect_button)
        self.open_button = ttk.Button(buttons, text="Open destination", command=self.open_target, state="disabled")
        self.open_button.pack(side="right")
        self.status = tk.StringVar(value="Ready. Existing files are kept unless you enable replacement.")
        ttk.Label(frame, textvariable=self.status, wraplength=730).grid(
            row=8, column=0, columnspan=3, sticky="w", pady=(5, 10))
        self.output = scrolledtext.ScrolledText(frame, height=14, wrap="word", font=("Consolas", 10), state="disabled")
        self.output.grid(row=9, column=0, columnspan=3, sticky="nsew")
        ttk.Label(frame, text="Source and extra destination files stay in place. Windows junctions are skipped. Direct cloud copies use Google's API; G: paths use the desktop cache.",
                  wraplength=730).grid(row=10, column=0, columnspan=3, sticky="w", pady=(12, 0))
        self.preview()

    def browse(self, variable):
        chosen = filedialog.askdirectory(parent=self.root, initialdir=variable.get() or None)
        if chosen:
            variable.set(chosen)

    def default_workers(self):
        if not self.cloud_route:
            return "16"
        return str(PRESETS[self.profile.get()]["workers"])

    def browse_drive(self, variable):
        if not CONFIG.exists():
            messagebox.showinfo("Connect Google Drive", "Use Connect Drive first, then choose a cloud folder.", parent=self.root)
            return
        DrivePicker(self.root, variable.set, variable.get())

    def connect_drive(self):
        if self.auth_process or self.process:
            return
        client = filedialog.askopenfilename(parent=self.root, title="Choose Google OAuth desktop-client JSON",
                                           filetypes=[("Google OAuth JSON", "*.json")])
        if not client:
            return
        import sys
        self.auth_scratch = TransferScratch()
        log_path = self.auth_scratch.log
        try:
            with log_path.open("w", encoding="utf-8") as output:
                process = subprocess.Popen([sys.executable, "-B", str(ROOT / "connect_drive.py"), client],
                    stdout=output, stderr=output, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as error:
            self.auth_scratch.clean()
            self.auth_scratch = None
            messagebox.showerror("Cannot connect Drive", str(error), parent=self.root)
            return
        self.auth_process = process
        self.status.set("Finish Google sign-in in your browser. Credentials stay on this computer.")
        self.connect_button.configure(state="disabled")
        self.start_button.configure(state="disabled")

        def check():
            if self.auth_process is not process:
                return
            if process.poll() is None:
                self.root.after(500, check)
                return
            self.connect_button.configure(state="normal")
            self.start_button.configure(state="normal")
            self.status.set("Google Drive connected." if process.returncode == 0 else "Drive connection failed; see log below.")
            self.append(log_path.read_text(encoding="utf-8", errors="replace"))
            self.auth_scratch.clean()
            self.auth_scratch = None
            self.auth_process = None
        self.root.after(500, check)

    def preview(self, *_):
        source, parent = self.source.get().strip(), self.parent.get().strip()
        name = source.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1]
        target = (parent.rstrip("/") + ("" if parent.endswith(":") else "/") + name) if source and parent else "Choose both folders"
        self.destination_label.set(f"Destination: {target}")
        cloud_route = is_remote(source) or is_remote(parent)
        if hasattr(self, "profile") and not self.process and cloud_route != self.cloud_route:
            self.cloud_route = cloud_route
            self.workers.set(self.default_workers())
        if hasattr(self, "resume_checkbox") and not self.process:
            self.resume_checkbox.configure(state="disabled" if is_remote(source) or is_remote(parent) else "normal")

    def append(self, text):
        self.output.configure(state="normal")
        self.output.insert("end", text)
        if int(self.output.index("end-1c").split(".")[0]) > 1500:
            self.output.delete("1.0", "500.0")
        self.output.see("end")
        self.output.configure(state="disabled")

    def start(self):
        if self.process or self.auth_process:
            return
        try:
            # A unique directory owns all disposable logs/cache for this job.
            self.scratch = TransferScratch()
            self.log = self.scratch.log
            if is_remote(self.source.get().strip()) or is_remote(self.parent.get().strip()):
                plan = direct_plan(self.source.get(), self.parent.get(), self.workers.get(), self.replace.get(), self.log, profile=self.profile.get())
                args, self.target, self.backend = plan.command, plan.target, plan.backend
                args += ["--cache-dir", str(self.scratch.cache), "--temp-dir", str(self.scratch.temp)]
            else:
                args, self.target = copy_command(self.source.get(), self.parent.get(),
                    self.workers.get(), self.replace.get(), self.resumable.get(), self.log)
                self.backend = "robocopy"
            self.process = subprocess.Popen(args, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, ValueError) as error:
            if self.scratch:
                self.scratch.clean()
                self.scratch = None
            messagebox.showerror("Cannot start copy", str(error), parent=self.root)
            return
        self.cancelled = False
        self.log_offset = 0
        self.decoder = codecs.getincrementaldecoder("utf-16-le" if self.backend == "robocopy" else "utf-8")(errors="replace")
        self.started = time.monotonic()
        for widget in self.inputs + [self.start_button]:
            widget.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.open_button.configure(state="disabled")
        self.append(f"\nCopying to {self.target}\nLog: {self.log}\n")
        self.poll()

    def poll(self):
        code = self.process.poll()
        try:
            with self.log.open("rb") as handle:
                handle.seek(self.log_offset)
                data = handle.read(131072)
                self.log_offset += len(data)
            if data:
                self.append(self.decoder.decode(data).lstrip("\ufeff"))
        except OSError:
            pass
        if code is None:
            elapsed = int(time.monotonic() - self.started)
            self.status.set(f"{'Stopping' if self.cancelled else 'Copying'}… {elapsed}s elapsed. Transfer progress appears below.")
            self.root.after(300, self.poll)
            return
        # Drain any remaining log chunks before reporting the final summary.
        if self.log.exists() and self.log.stat().st_size > self.log_offset + 1:
            self.root.after(10, self.poll)
            return
        self.process = None
        for widget in self.inputs + [self.start_button]:
            widget.configure(state="normal")
        self.preset_widget.configure(state="readonly")
        self.preview()
        self.stop_button.configure(state="disabled")
        if is_remote(self.target) or Path(self.target).is_dir():
            self.open_button.configure(state="normal")
        self.status.set(result_message(code, self.backend, self.cancelled))
        try:
            self.scratch.clean()
            self.scratch = None
            self.append("Temporary files and on-disk logs cleaned. The displayed log stays available until you close the window.\n")
        except OSError as error:
            self.append(f"Temporary-file cleanup could not finish: {error}\n")

    def stop(self):
        if self.process and self.process.poll() is None:
            self.cancelled = True
            if self.backend == "folders":
                kill_tree(self.process)
            else:
                self.process.terminate()
            self.stop_button.configure(state="disabled")

    def open_target(self):
        if self.target and is_remote(self.target):
            target = self.target
            def worker():
                try:
                    result = subprocess.run(rclone_base() + ["lsjson", target, "--stat"], capture_output=True,
                        text=True, encoding="utf-8", timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    if result.returncode == 0:
                        identifier = json.loads(result.stdout)["ID"]
                        webbrowser.open("https://drive.google.com/drive/folders/" + identifier)
                except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
                    pass
            threading.Thread(target=worker, daemon=True).start()
        elif self.target and Path(self.target).is_dir():
            os.startfile(self.target)

    def close(self):
        if self.auth_process:
            if self.auth_process.poll() is None:
                self.auth_process.terminate()
            self.auth_process.wait(timeout=5)
            self.auth_scratch.clean()
            self.auth_process = None
            self.auth_scratch = None
        if self.process:
            if not messagebox.askyesno("Stop copying?", "Stop the current copy and close? Some files may be incomplete.", parent=self.root):
                return
            self.stop()
            self.root.after(100, self.close_when_stopped)
        else:
            self.root.destroy()

    def close_when_stopped(self):
        if self.process:
            self.root.after(100, self.close_when_stopped)
        else:
            self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="")
    parser.add_argument("--destination", default="", help="Destination parent folder")
    args = parser.parse_args()
    root = tk.Tk()
    CopyApp(root, args.source, args.destination)
    root.mainloop()


if __name__ == "__main__":
    main()
