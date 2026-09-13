"""Small asynchronous folder picker backed by rclone's Drive API listing."""
import json
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from transfer_engine import rclone_base


class DrivePicker:
    def __init__(self, parent, callback, initial="gdrive:"):
        self.callback = callback
        self.path = initial if initial.startswith("gdrive:") else "gdrive:"
        self.pending = queue.Queue()
        self.items = []
        self.closed = threading.Event()
        self.process = None
        self.process_lock = threading.Lock()
        self.after_id = None
        self.window = tk.Toplevel(parent)
        self.window.title("Choose a Google Drive folder")
        self.window.geometry("600x450")
        self.window.transient(parent)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Destroy>", lambda event: self.cancel_listing() if event.widget is self.window else None)
        self.label = tk.StringVar(value=self.path)
        ttk.Label(self.window, textvariable=self.label, wraplength=570).pack(fill="x", padx=15, pady=12)
        self.listbox = tk.Listbox(self.window, font=("Segoe UI", 11))
        self.listbox.pack(fill="both", expand=True, padx=15)
        self.listbox.bind("<Double-Button-1>", self.open_selected)
        bar = ttk.Frame(self.window, padding=15)
        bar.pack(fill="x")
        self.up = ttk.Button(bar, text="Up", command=self.go_up)
        self.up.pack(side="left")
        self.select = ttk.Button(bar, text="Use this folder", command=self.choose)
        self.select.pack(side="right")
        self.load()

    def load(self):
        self.label.set(f"Loading {self.path}…")
        self.listbox.delete(0, "end")
        self.select.configure(state="disabled")
        self.up.configure(state="disabled")
        path = self.path

        def worker():
            try:
                with self.process_lock:
                    if self.closed.is_set():
                        return
                    process = subprocess.Popen(rclone_base() + ["lsjson", path, "--dirs-only"],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    self.process = process
                try:
                    stdout, stderr = process.communicate(timeout=60)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()
                    raise RuntimeError("Drive listing timed out.")
                finally:
                    with self.process_lock:
                        self.process = None
                if process.returncode:
                    raise RuntimeError(stderr.strip())
                items = sorted(json.loads(stdout), key=lambda item: item["Name"].casefold())
                names = [item["Name"] for item in items]
                if len(names) != len(set(names)):
                    raise RuntimeError("This folder contains duplicate folder names. Rename the duplicates in Drive before copying by path.")
                self.pending.put((items, None))
            except Exception as error:
                self.pending.put(([], str(error)))

        threading.Thread(target=worker, daemon=True).start()
        self.after_id = self.window.after(100, self.poll)

    def poll(self):
        if self.closed.is_set():
            return
        try:
            items, error = self.pending.get_nowait()
        except queue.Empty:
            self.after_id = self.window.after(100, self.poll)
            return
        self.up.configure(state="normal")
        if error:
            self.label.set(self.path)
            messagebox.showerror("Could not list Drive folders", error, parent=self.window)
            return
        self.items = items
        self.label.set(self.path + "  •  Double-click a folder to open it")
        for item in items:
            self.listbox.insert("end", item["Name"])
        self.select.configure(state="normal")

    def open_selected(self, *_):
        selected = self.listbox.curselection()
        if selected:
            self.path = self.path.rstrip("/") + ("" if self.path.endswith(":") else "/") + self.items[selected[0]]["Name"]
            self.load()

    def go_up(self):
        path = self.path.split(":", 1)[1].strip("/")
        self.path = "gdrive:" + (path.rsplit("/", 1)[0] if "/" in path else "")
        self.load()

    def choose(self):
        self.callback(self.path)
        self.close()

    def cancel_listing(self):
        self.closed.set()
        with self.process_lock:
            if self.process and self.process.poll() is None:
                self.process.terminate()

    def close(self):
        self.cancel_listing()
        if self.after_id:
            self.window.after_cancel(self.after_id)
        self.window.destroy()
