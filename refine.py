"""Bounded experiments beyond file-level concurrency; all runs remain serial."""
import argparse
import time
import json
from benchmark import run_case
from benchmark import RESULTS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["folders", "batches", "limits", "warm", "many-limits", "repeat-small"])
    args = parser.parse_args()
    if args.phase in ("folders", "batches"):
        for direction in ("cloud-copy", "upload", "download"):
            print(f"Independent-folder experiment: {direction}", flush=True)
            run_case(direction, args.phase, "many", 64, False, 3, folder_jobs=8)
    elif args.phase == "many-limits":
        for direction in ("download", "upload", "cloud-copy"):
            for backend in ("rclone", "batches" if direction == "download" else "folders"):
                print(f"Many-file final screen: {direction}, {backend}, 128 workers", flush=True)
                run_case(direction, backend, "many", 128, False, 4,
                         fast_list=True, pacer_ms=1, folder_jobs=16)
    elif args.phase == "repeat-small":
        for trial in (4, 5):
            for direction in ("download", "upload", "cloud-copy"):
                for workers, pacer in ((64, 10), (128, 1)):
                    run_case(direction, "rclone", "small", workers, False, trial,
                             fast_list=True, pacer_ms=pacer)
    elif args.phase == "limits":
        for direction in ("download", "upload", "cloud-copy"):
            for workers, pacer in ((128, 10), (64, 5), (128, 5), (128, 1)):
                print(f"Concurrency/pacing limit: {direction}, {workers}, {pacer}ms", flush=True)
                run_case(direction, "rclone", "small", workers, False, 3,
                         fast_list=True, pacer_ms=pacer)
        for workers in (8, 32):
            print(f"Multipart upload cutoff experiment: {workers} workers", flush=True)
            run_case("upload", "rclone", "large", workers, False, 3,
                fast_list=True, pacer_ms=10, chunk_mib=64, upload_cutoff_mib=64)
    else:
        completed = [json.loads(line) for line in RESULTS.read_text().splitlines()]
        for profile in ("small", "large", "many"):
            for workers, restart in ((16, True), (8, False), (16, False), (32, False), (64, False)):
                if any(r["profile"] == profile and r["backend"] == "robocopy" and r["workers"] == workers and r["restartable"] == restart and r.get("warm") and r["status"] == "ok" for r in completed):
                    continue
                print(f"Explicitly warmed download: {profile}, {workers}, restart={restart}", flush=True)
                run_case("download", "robocopy", profile, workers, restart, 3, warm=True)
            if not any(r["profile"] == profile and r["backend"] == "python" and r.get("warm") and r["status"] == "ok" for r in completed):
                run_case("download", "python", profile, 1, False, 3, warm=True)
    time.sleep(1)


if __name__ == "__main__":
    main()
