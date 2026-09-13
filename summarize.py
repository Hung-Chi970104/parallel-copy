"""Summarize raw benchmark outcomes without selecting or hiding failed cases."""
from collections import defaultdict
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parent


def rows():
    path = ROOT / "results" / "measurements.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def groups(data):
    result = defaultdict(list)
    for row in data:
        key = (row["direction"], row["profile"], row["backend"], row["workers"], row["restartable"],
               row.get("fast_list", False), row.get("pacer_ms", 100), row.get("chunk_mib", 8),
               row.get("streams", 4), row.get("cutoff_mib", 256), row.get("seed", "seed"), row.get("warm", False), row.get("upload_cutoff_mib", 8), row.get("folder_jobs", 8))
        result[key].append(row)
    return result


def main():
    data = rows()
    print(f"{len(data)} completed cases; {sum(r['status'] != 'ok' for r in data)} failed")
    for key, values in sorted(groups(data).items()):
        passed = [r for r in values if r["status"] == "ok"]
        if not passed:
            print(key, "FAILED", values[-1].get("error"))
            continue
        copy = statistics.median(r["copy_seconds"] for r in passed)
        verified = statistics.median(r["verified_seconds"] for r in passed)
        print(f"{str(key):95} n={len(passed)} copy={copy:8.3f}s verified={verified:8.3f}s")


if __name__ == "__main__":
    main()
