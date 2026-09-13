"""Copy independent top-level folders through bounded rclone child processes.

All children target distinct subfolders. Root creation happens once before
starting children, avoiding races that could create duplicate Drive folders.
This retains rclone's transfer, retry, checksum, and existing-file semantics.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time

from transfer_engine import direct_plan, is_remote, rclone_base


def kill_tree(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        process.terminate()


def list_children(source):
    result = subprocess.run(rclone_base() + ["lsjson", source], capture_output=True,
        text=True, encoding="utf-8", timeout=90)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    items = json.loads(result.stdout)
    names = [item["Name"] for item in items]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate names in the source cannot be copied by path safely.")
    return items


def append_path(parent, child):
    if is_remote(parent):
        return parent.rstrip("/") + ("" if parent.endswith(":") else "/") + child
    return str(Path(parent) / child)


def run(source, parent, workers, folders, replace, log, pacer=10, chunk=8, strategy="folders"):
    log = Path(log)
    # Reuse the normal planner's validation and destination convention.
    plan = direct_plan(source, parent, workers, replace, log)
    source = plan.command[plan.command.index("copy") + 1]
    target = plan.target
    children = list_children(source)
    directories = [item for item in children if item["IsDir"]]
    files = [item for item in children if not item["IsDir"]]
    folders = max(1, min(int(folders), int(workers), len(directories) or 1))
    per_child = max(1, int(workers) // folders)
    active = set()
    lock = threading.Lock()
    cancelled = threading.Event()
    log.parent.mkdir(parents=True, exist_ok=True)

    def emit(message):
        with lock:
            with log.open("a", encoding="utf-8") as handle:
                handle.write(message + "\n")

    def execute(command):
        if cancelled.is_set():
            raise RuntimeError("Copy cancelled")
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        with lock:
            active.add(process)
        try:
            for line in process.stdout:
                emit(line.rstrip())
            code = process.wait()
            if code:
                raise RuntimeError(f"Folder transfer failed with exit code {code}")
        finally:
            process.stdout.close()
            with lock:
                active.discard(process)

    base_options = ["--drive-pacer-min-sleep", f"{pacer}ms", "--drive-chunk-size", f"{chunk}M",
                    "--fast-list", "--stats", "0", "--log-level", "ERROR", "--retries", "3"]
    if not replace:
        base_options.append("--ignore-existing")
    # Mkdir is idempotent in an existing non-ambiguous namespace.
    execute(rclone_base() + ["mkdir", target])
    emit(f"Copying {len(directories)} folders with {folders} simultaneous folder jobs, {per_child} file transfers per job.")
    try:
        if files and strategy == "folders":
            execute(rclone_base() + ["copy", source, target, "--max-depth", "1",
                                    "--transfers", str(workers)] + base_options)

        def folder(item):
            name = item["Name"]
            emit(f"Started folder: {name}")
            execute(rclone_base() + ["copy", append_path(source, name), append_path(target, name),
                "--transfers", str(per_child), "--create-empty-src-dirs"] + base_options)
            emit(f"Finished folder: {name}")

        def group(item):
            index, members = item
            filters = log.parent / f"{log.stem}-group-{index}.filter"
            rules = ["+ /{{" + re.escape(member["Name"]) + "}}/**" for member in members]
            if index == 0:
                rules += ["+ /{{" + re.escape(member["Name"]) + "}}" for member in files]
            filters.write_text("\n".join(rules + ["- **"]) + "\n", encoding="utf-8")
            emit(f"Started batch {index + 1}: {len(members)} independent folders")
            try:
                execute(rclone_base() + ["copy", source, target, "--filter-from", str(filters),
                    "--transfers", str(per_child), "--create-empty-src-dirs"] + base_options)
                emit(f"Finished batch {index + 1}")
            finally:
                filters.unlink(missing_ok=True)

        with ThreadPoolExecutor(max_workers=folders) as pool:
            jobs = list(enumerate([directories[i::folders] for i in range(folders)])) if strategy == "groups" else directories
            handler = group if strategy == "groups" else folder
            futures = [pool.submit(handler, item) for item in jobs]
            for future in as_completed(futures):
                try:
                    future.result()
                except BaseException:
                    cancelled.set()
                    for pending in futures:
                        pending.cancel()
                    with lock:
                        processes = list(active)
                    for process in processes:
                        kill_tree(process)
                    raise
    finally:
        cancelled.set()
        with lock:
            processes = list(active)
        for process in processes:
            kill_tree(process)
    emit("All folder jobs completed successfully.")
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    parser.add_argument("parent")
    parser.add_argument("--workers", type=int, default=64)
    parser.add_argument("--folders", type=int, default=8)
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--log", required=True)
    parser.add_argument("--strategy", choices=["folders", "groups"], default="folders")
    args = parser.parse_args()
    try:
        run(args.source, args.parent, args.workers, args.folders, args.replace, args.log, strategy=args.strategy)
    except Exception as error:
        with Path(args.log).open("a", encoding="utf-8") as handle:
            handle.write(f"ERROR: {error}\n")
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
