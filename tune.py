"""Second-round tuning after the initial screen; run serially, never concurrently."""
import argparse
import json
import random
import subprocess
import time
from benchmark import CLOUD_ROOT, DATA, RESULTS, run_case
from transfer_engine import rclone_base


def run(cases):
    random.Random(260913).shuffle(cases)
    for index, case in enumerate(cases):
        print(f"TUNE {index + 1}/{len(cases)} {case}", flush=True)
        run_case(*case)
        time.sleep(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["pacing", "many", "seed-many"])
    args = parser.parse_args()
    if args.phase == "seed-many":
        command = rclone_base() + ["copy", str(DATA / "source" / "many"),
            f"gdrive:{CLOUD_ROOT}/seed/many", "--transfers", "32", "--drive-pacer-min-sleep", "10ms",
            "--stats", "5s", "--stats-one-line", "--log-level", "NOTICE"]
        subprocess.run(command, check=True)
        return
    cases = []
    if args.phase == "pacing":
        for direction in ("download", "upload", "cloud-copy"):
            for workers in (8, 16, 32, 64):
                cases.append([direction, "rclone", "small", workers, False, 2, 4, "seed", True, 10])
        for direction in ("download", "upload", "cloud-copy"):
            cases.append([direction, "rclone", "large", 8, False, 2, 4, "seed", True, 10, 64])
    elif args.phase == "many":
        for direction in ("download", "upload", "cloud-copy"):
            cases.append([direction, "robocopy", "many", 16, True, 1])
            for workers in (32, 64):
                cases.append([direction, "rclone", "many", workers, False, 2, 4, "seed", True, 10])
    run(cases)


if __name__ == "__main__":
    main()
