"""Windows folder-copy GUI. Run python parallel_copy.py (no pip packages).

Uses Windows Robocopy for parallel transfers; never mirrors or deletes files.
Destination is a parent folder: the source folder's name is appended.
"""
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
from transfer_engine import CONFIG, ROOT, direct_plan, is_remote, rclone_base, result_message
from drive_picker import DrivePicker


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
        for label, variable in [("Replace existing files when different", self.replace),
                                ("Resume interrupted files (may be slower)", self.resumable)]:
            checkbox = ttk.Checkbutton(checks, text=label, variable=variable)
            checkbox.pack(anchor="w", pady=2)
            self.inputs.append(checkbox)
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

    def browse(self, variable):
        chosen = filedialog.askdirectory(parent=self.root, initialdir=variable.get() or None)
        if chosen:
            variable.set(chosen)

    def browse_drive(self, variable):
        if not CONFIG.exists():
            messagebox.showinfo("Connect Google Drive", "Use Connect Drive first, then choose a cloud folder.", parent=self.root)
            return
        DrivePicker(self.root, variable.set, variable.get())

    def connect_drive(self):
        client = filedialog.askopenfilename(parent=self.root, title="Choose Google OAuth desktop-client JSON",
                                           filetypes=[("Google OAuth JSON", "*.json")])
        if not client:
            return
        import sys
        log_path = ROOT / ".local" / "connect.log"
        log_path.parent.mkdir(exist_ok=True)
        with log_path.open("w", encoding="utf-8") as output:
            process = subprocess.Popen([sys.executable, str(ROOT / "connect_drive.py"), client],
                stdout=output, stderr=output, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.status.set("Finish Google sign-in in your browser. Credentials stay on this computer.")
        self.connect_button.configure(state="disabled")

        def check():
            if process.poll() is None:
                self.root.after(500, check)
                return
            self.connect_button.configure(state="normal")
            self.status.set("Google Drive connected." if process.returncode == 0 else "Drive connection failed; see log below.")
            self.append(log_path.read_text(encoding="utf-8", errors="replace"))
        self.root.after(500, check)

    def preview(self, *_):
        source, parent = self.source.get().strip(), self.parent.get().strip()
        name = source.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1]
        target = (parent.rstrip("/") + ("" if parent.endswith(":") else "/") + name) if source and parent else "Choose both folders"
        self.destination_label.set(f"Destination: {target}")

    def append(self, text):
        self.output.configure(state="normal")
        self.output.insert("end", text)
        if int(self.output.index("end-1c").split(".")[0]) > 1500:
            self.output.delete("1.0", "500.0")
        self.output.see("end")
        self.output.configure(state="disabled")

    def start(self):
        if self.process:
            return
        try:
            # Keep logs outside both copy trees; do not inherit a shell.
            log_dir = Path(tempfile.gettempdir()) / "parallel-folder-copy"
            log_dir.mkdir(exist_ok=True)
            self.log = log_dir / f"copy-{time.time_ns()}.log"
            if is_remote(self.source.get().strip()) or is_remote(self.parent.get().strip()):
                plan = direct_plan(self.source.get(), self.parent.get(), self.workers.get(), self.replace.get(), self.log)
                args, self.target, self.backend = plan.command, plan.target, plan.backend
            else:
                args, self.target = copy_command(self.source.get(), self.parent.get(),
                    self.workers.get(), self.replace.get(), self.resumable.get(), self.log)
                self.backend = "robocopy"
            self.process = subprocess.Popen(args, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, ValueError) as error:
            messagebox.showerror("Cannot start copy", str(error), parent=self.root)
            return
        self.cancelled = False
        self.log_offset = 0
        self.decoder = codecs.getincrementaldecoder("utf-8" if self.backend == "rclone" else "utf-16-le")(errors="replace")
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
            self.status.set(f"{'Stopping' if self.cancelled else 'Copying'}… {elapsed}s elapsed. Details appear below as Windows reports them.")
            self.root.after(300, self.poll)
            return
        # Drain any remaining log chunks before reporting the final summary.
        if self.log.exists() and self.log.stat().st_size > self.log_offset + 1:
            self.root.after(10, self.poll)
            return
        self.process = None
        for widget in self.inputs + [self.start_button]:
            widget.configure(state="normal")
        self.stop_button.configure(state="disabled")
        if is_remote(self.target) or Path(self.target).is_dir():
            self.open_button.configure(state="normal")
        self.status.set(result_message(code, self.backend, self.cancelled))

    def stop(self):
        if self.process and self.process.poll() is None:
            self.cancelled = True
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
