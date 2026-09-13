"""Serial benchmark rounds: no overlapping measured transfers."""
import argparse
import json
import random
import time
from benchmark import run_case, DATA, RESULTS


def screen():
    cases = []
    for direction in ("download", "upload", "cloud-copy"):
        for profile in ("small", "large"):
            for backend, workers, restart in [("python", 1, False), ("robocopy", 16, True),
                ("robocopy", 16, False), ("rclone", 1, False), ("rclone", 8, False), ("rclone", 32, False)]:
                cases.append((direction, backend, profile, workers, restart, 1))
    random.Random(20260913).shuffle(cases)
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", help="JSON list of explicit case argument lists")
    args = parser.parse_args()
    cases = json.loads(args.cases) if args.cases else screen()
    completed = []
    if RESULTS.exists():
        completed = [json.loads(line) for line in RESULTS.read_text().splitlines()]
    for index, case in enumerate(cases):
        direction, backend, profile, workers, restart, trial = case[:6]
        defaults = {"streams": 4, "seed": "seed", "fast_list": False, "pacer_ms": 100, "chunk_mib": 8, "cutoff_mib": 256}
        defaults["warm"] = False
        keys = ("direction", "backend", "profile", "workers", "restartable", "trial", "streams", "seed", "fast_list", "pacer_ms", "chunk_mib", "cutoff_mib", "warm")
        if any(all(row.get(key, defaults.get(key)) == value for key, value in zip(keys, case))
            for row in completed):
            print(f"SKIP {case}: already recorded", flush=True)
            continue
        print(f"START {index + 1}/{len(cases)} {case}", flush=True)
        run_case(*case)
        # Let transient completion/listing work settle before the next run.
        time.sleep(1)


if __name__ == "__main__":
    main()
