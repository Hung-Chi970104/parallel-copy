"""Transfer plans shared by the desktop window and reproducible benchmarks."""
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / ".local" / "rclone.conf"
REMOTE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]{1,}):(.*)$")
PRESETS = {
    "Small files": {"workers": 128, "pacer_ms": 1, "chunk_mib": 8, "folder_jobs": 0},
    "Many small files": {"workers": 128, "pacer_ms": 10, "download_pacer_ms": 1, "chunk_mib": 8, "folder_jobs": 16},
    "Large files": {"workers": 8, "pacer_ms": 10, "chunk_mib": 64, "folder_jobs": 0},
}


def is_remote(value):
    return bool(REMOTE.fullmatch(str(value)))


def remote_parts(value):
    match = REMOTE.fullmatch(str(value))
    if not match:
        raise ValueError("Use a configured remote path such as gdrive:Folder.")
    remote, path = match.groups()
    path = path.replace("\\", "/").strip("/")
    if any(part in (".", "..") for part in path.split("/")):
        raise ValueError("Remote paths cannot contain . or .. components.")
    return remote, path


def executable():
    bundled = ROOT / ".local" / "bin" / "rclone.exe"
    found = str(bundled) if bundled.is_file() else shutil.which("rclone")
    if not found:
        raise ValueError("Install the cloud engine using python install_rclone.py.")
    return found


def rclone_base():
    return [executable(), "--config", str(CONFIG)]


@dataclass
class TransferPlan:
    command: list
    target: str
    backend: str
    log: Path
    completion_note: str


def direct_plan(source, parent, workers, replace, log, streams=4, profile="Small files"):
    if profile not in PRESETS:
        raise ValueError("Choose a listed cloud preset.")
    settings = PRESETS[profile]
    source, parent = str(source).strip(), str(parent).strip()
    if not source or not parent:
        raise ValueError("Choose both folders.")
    for endpoint in (source, parent):
        if re.match(r"^[A-Za-z]:[\\/](My Drive|Shared drives|Other computers)([\\/]|$)", endpoint, re.IGNORECASE):
            raise ValueError("Use the Drive picker for both cloud endpoints. Do not mix a mounted Google Drive folder with a direct gdrive: path.")
    if not 1 <= int(workers) <= 128:
        raise ValueError("Parallel transfers must be between 1 and 128.")
    if not 0 <= int(streams) <= 16:
        raise ValueError("Download streams must be between 0 and 16.")
    if is_remote(source):
        remote, source_path = remote_parts(source)
        name = PurePosixPath(source_path).name
        if not name:
            raise ValueError("Choose a source folder, rather than an entire remote.")
        source = f"{remote}:{source_path}"
    else:
        path = Path(source).expanduser().resolve()
        if not path.is_dir() or not path.name:
            raise ValueError("Choose an accessible local source folder.")
        source, name = str(path), path.name
    if is_remote(parent):
        remote, parent_path = remote_parts(parent)
        target = f"{remote}:{parent_path + '/' if parent_path else ''}{name}"
    else:
        path = Path(parent).expanduser().resolve()
        if not path.is_dir():
            raise ValueError("Choose an existing local destination parent folder.")
        target = str((path / name).resolve())
        if Path(target).exists() and not Path(target).is_dir():
            raise ValueError("A file already occupies the destination folder path.")
    if is_remote(source) and is_remote(target):
        sr, sp = remote_parts(source)
        tr, tp = remote_parts(target)
        if sr == tr and (sp == tp or sp.startswith(tp + "/") or tp.startswith(sp + "/")):
            raise ValueError("Source and destination must not contain each other.")
    elif not is_remote(source) and not is_remote(target):
        sp, tp = Path(source), Path(target)
        if sp == tp or sp in tp.parents or tp in sp.parents:
            raise ValueError("Source and destination must not contain each other.")
    command = rclone_base() + ["copy", source, target, "--transfers", str(workers),
        "--checkers", "8", "--create-empty-src-dirs", "--stats", "1s",
        "--stats-one-line", "--stats-log-level", "NOTICE", "--log-level", "INFO",
        "--log-file", str(log), "--retries", "3", "--low-level-retries", "5",
        "--contimeout", "15s", "--timeout", "2m", "--multi-thread-streams", str(streams)]
    pacer = settings.get("download_pacer_ms", settings["pacer_ms"]) if not is_remote(target) else settings["pacer_ms"]
    command += ["--fast-list", "--drive-pacer-min-sleep", f"{pacer}ms",
                "--drive-chunk-size", f"{settings['chunk_mib']}M"]
    if not replace:
        command.append("--ignore-existing")
    backend = "rclone"
    if settings["folder_jobs"] and is_remote(target):
        folder_jobs = min(settings["folder_jobs"], max(1, int(workers) // 8))
        command = [sys.executable, "-B", str(ROOT / "folder_parallel.py"), source, str(parent),
                   "--workers", str(workers), "--folders", str(folder_jobs), "--log", str(log)]
        if replace:
            command.append("--replace")
        backend = "folders"
    return TransferPlan(command, target, backend, Path(log),
        "Cloud API transfer complete. Rclone checks available file checksums during transfer.")


def result_message(code, backend, cancelled=False):
    if cancelled:
        return "Stopped. Partial files may remain; enable replacement before restarting."
    if backend in ("rclone", "folders"):
        return ("Copy finished and acknowledged by the cloud API." if code == 0 else
                f"Copy failed (code {code}); review the log. Some files may have copied.")
    if code < 0 or code >= 8:
        return f"Copy failed (code {code}); review the log. Some files may have copied."
    if code & 4:
        return f"Finished with mismatches (code {code}); review the log."
    return "Filesystem copy finished. For cloud folders, Drive may still be uploading."
