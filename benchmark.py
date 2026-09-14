"""Synthetic transfer benchmark: never touches files outside its benchmark roots.

Run prepare, then run cases; raw JSONL is append-only. Each case uses a new
destination. API-visible MD5 validation is measured separately from copy time.
Mounted upload completion is the first successful remote validation observation,
so it is an upper bound with polling/API latency, not an exact server timestamp.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from transfer_engine import ROOT, rclone_base

DATA = ROOT / ".local" / "benchmark"
RESULTS = ROOT / "results" / "measurements.jsonl"
CLOUD_ROOT = "ParallelCopy-benchmark-20260913"
MOUNT = Path("G:/My Drive") / CLOUD_ROOT
PROFILES = {"small": (128, 32 * 1024), "large": (4, 16 * 1024 * 1024),
            "many": (2048, 8 * 1024), "bulk": (2, 256 * 1024 * 1024)}


def record(row):
    RESULTS.parent.mkdir(exist_ok=True)
    with RESULTS.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")
    print(json.dumps(row), flush=True)


def manifest(folder):
    result = {}
    for path in sorted(Path(folder).rglob("*")):
        if path.is_file():
            with path.open("rb") as handle:
                digest = hashlib.file_digest(handle, "md5").hexdigest()
            result[path.relative_to(folder).as_posix()] = {"size": path.stat().st_size, "md5": digest}
    return result


def prepare():
    DATA.mkdir(parents=True, exist_ok=True)
    for profile, (count, size) in PROFILES.items():
        folder = DATA / "source" / profile
        folder.mkdir(parents=True, exist_ok=True)
        for index in range(count):
            subfolder = folder / f"group-{index // 32:03d}" if profile == "many" else folder
            subfolder.mkdir(exist_ok=True)
            path = subfolder / f"file-{index:04d}.bin"
            if not path.exists():
                path.write_bytes(os.urandom(size))
        (DATA / f"{profile}.json").write_text(json.dumps(manifest(folder)), encoding="utf-8")
    print("Prepared incompressible payloads: 128 x 32 KiB, 4 x 16 MiB, 2,048 x 8 KiB across 64 folders, and 2 x 256 MiB", flush=True)


def remote_manifest(remote):
    process = subprocess.run(rclone_base() + ["lsjson", remote, "--recursive", "--files-only",
        "--hash", "--hash-type", "MD5", "--fast-list"], capture_output=True, text=True, encoding="utf-8", timeout=90)
    if process.returncode:
        return None
    return {item["Path"]: {"size": item["Size"], "md5": item.get("Hashes", {}).get("md5", "")}
            for item in json.loads(process.stdout)}


def wait_remote(remote, expected, timeout=600):
    deadline = time.perf_counter() + timeout
    checks = 0
    while time.perf_counter() < deadline:
        checks += 1
        if remote_manifest(remote) == expected:
            return checks
        time.sleep(2)
    raise TimeoutError(f"Cloud metadata/checksum verification did not complete: {remote}")


def run_case(direction, backend, profile, workers, restartable, trial, streams=4, seed="seed", fast_list=False, pacer_ms=100, chunk_mib=8, cutoff_mib=256, warm=False, upload_cutoff_mib=8, folder_jobs=8):
    if backend in ("folders", "batches"):
        fast_list, pacer_ms, chunk_mib = True, 10, 8
    expected = json.loads((DATA / f"{profile}.json").read_text())
    identifier = f"{direction}-{backend}-{profile}-t{workers}-z{int(restartable)}-s{streams}-r{trial}-{uuid.uuid4().hex[:6]}"
    remote_source = f"gdrive:{CLOUD_ROOT}/{seed}/{profile}"
    mount_source = MOUNT / seed / profile
    local_source = DATA / "source" / profile
    remote_target = f"gdrive:{CLOUD_ROOT}/runs/{identifier}/{profile}"
    local_target = DATA / "downloads" / identifier / profile
    mounted_target = MOUNT / "runs" / identifier / profile
    direct = backend in ("rclone", "folders", "batches")
    source = str(local_source) if direction == "upload" else (remote_source if direct else str(mount_source))
    target = str(local_target) if direction == "download" else (remote_target if direct else str(mounted_target))
    log = DATA / f"{identifier}.log"
    row = {"id": identifier, "utc": datetime.now(timezone.utc).isoformat(), "direction": direction,
           "backend": backend, "profile": profile, "workers": workers, "restartable": restartable,
           "streams": streams, "trial": trial, "files": len(expected),
           "bytes": sum(item["size"] for item in expected.values()), "seed": seed, "fast_list": fast_list,
           "pacer_ms": pacer_ms, "chunk_mib": chunk_mib, "cutoff_mib": cutoff_mib, "warm": warm,
           "upload_cutoff_mib": upload_cutoff_mib,
           "folder_jobs": folder_jobs,
           "cache": "DriveFS warm/unspecified" if not direct and direction != "upload" else "bypasses DriveFS" if direct else "local source"}
    if backend in ("folders", "batches"):
        if direction == "download":
            local_target.parent.mkdir(parents=True, exist_ok=True)
            parent = str(local_target.parent)
        else:
            parent = target.rsplit("/", 1)[0]
        command = [sys.executable, str(ROOT / "folder_parallel.py"), source, parent,
            "--workers", str(workers), "--folders", str(folder_jobs), "--replace", "--log", str(log)]
        if backend == "batches":
            command += ["--strategy", "groups"]
    elif backend == "rclone":
        command = rclone_base() + ["copy", source, target, "--transfers", str(workers),
            "--checkers", "8", "--multi-thread-streams", str(streams), "--log-file", str(log),
            "--log-level", "INFO", "--stats", "1s", "--retries", "2", "--low-level-retries", "5"]
        command += ["--drive-pacer-min-sleep", f"{pacer_ms}ms", "--drive-chunk-size", f"{chunk_mib}M",
                    "--multi-thread-cutoff", f"{cutoff_mib}M", "--drive-upload-cutoff", f"{upload_cutoff_mib}M"]
        if fast_list:
            command.append("--fast-list")
    elif backend == "robocopy":
        command = ["robocopy", source, target, "/E", f"/MT:{workers}", "/R:2", "/W:2",
            "/COPY:DAT", "/DCOPY:DAT", "/XJ", "/NP", "/NFL", "/NDL", f"/LOG:{log}"]
        if restartable:
            command.append("/Z")
    else:
        command = None
    if warm and not direct and direction != "upload":
        def read_all(path):
            with path.open("rb") as handle:
                while handle.read(1024 * 1024):
                    pass
        with ThreadPoolExecutor(max_workers=32) as pool:
            list(pool.map(read_all, (p for p in mount_source.rglob("*") if p.is_file())))
        row["cache"] = "Explicitly warmed immediately before timing"
    start = time.perf_counter()
    try:
        if command:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            try:
                process.communicate(timeout=600)
            except subprocess.TimeoutExpired:
                from folder_parallel import kill_tree
                kill_tree(process)
                process.communicate()
                raise
            row["exit_code"] = process.returncode
            if process.returncode < 0 or process.returncode >= (8 if backend == "robocopy" else 1):
                raise RuntimeError(f"Transfer failed, code {process.returncode}; see local log")
        else:
            shutil.copytree(source, target)
            row["exit_code"] = 0
        finished = time.perf_counter()
        row["copy_seconds"] = finished - start
        if direction == "download":
            actual = manifest(local_target)
            if actual != expected:
                raise RuntimeError("Downloaded MD5 manifest mismatch")
        else:
            row["verification_polls"] = wait_remote(remote_target, expected)
        verified = time.perf_counter()
        row["verified_seconds"] = verified - start
        row["verification_seconds"] = verified - finished
        row["md5_verified"] = True
        row["status"] = "ok"
    except Exception as error:
        row["status"] = "failed"
        row["error"] = str(error)
        row["elapsed_seconds"] = time.perf_counter() - start
    record(row)
    return row


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("prepare")
    sub.add_parser("seed", help="Upload only the generated source fixtures to the benchmark seed")
    run = sub.add_parser("run")
    run.add_argument("direction", choices=["download", "upload", "cloud-copy"])
    run.add_argument("backend", choices=["robocopy", "rclone", "python", "folders", "batches"])
    run.add_argument("profile", choices=PROFILES)
    run.add_argument("--workers", type=int, default=16)
    run.add_argument("--restartable", action="store_true")
    run.add_argument("--trial", type=int, default=1)
    run.add_argument("--streams", type=int, default=4)
    run.add_argument("--seed", default="seed")
    run.add_argument("--fast-list", action="store_true")
    run.add_argument("--pacer-ms", type=int, default=100)
    run.add_argument("--chunk-mib", type=int, default=8)
    run.add_argument("--cutoff-mib", type=int, default=256)
    run.add_argument("--warm", action="store_true")
    run.add_argument("--upload-cutoff-mib", type=int, default=8)
    run.add_argument("--folder-jobs", type=int, default=8)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    elif args.action == "seed":
        if not (DATA / "source").is_dir():
            parser.error("Run prepare first.")
        subprocess.run(rclone_base() + ["copy", str(DATA / "source"),
            f"gdrive:{CLOUD_ROOT}/seed", "--transfers", "32", "--drive-pacer-min-sleep", "10ms"], check=True)
        for profile in PROFILES:
            wait_remote(f"gdrive:{CLOUD_ROOT}/seed/{profile}",
                        json.loads((DATA / f"{profile}.json").read_text()))
        print("All generated seed profiles verified.")
    else:
        result = run_case(args.direction, args.backend, args.profile, args.workers,
                          args.restartable, args.trial, args.streams, args.seed, args.fast_list,
                          args.pacer_ms, args.chunk_mib, args.cutoff_mib, args.warm,
                          args.upload_cutoff_mib, args.folder_jobs)
        raise SystemExit(0 if result["status"] == "ok" else 1)
