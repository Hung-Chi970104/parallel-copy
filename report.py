"""Render all retained measurements and explicit production-setting comparisons."""
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics

from summarize import rows, groups

ROOT = Path(__file__).resolve().parent


def median(data, field="verified_seconds"):
    return statistics.median(r[field] for r in data)


def selected(row):
    if row["backend"] != "rclone" or not row.get("fast_list"):
        return False
    if row["profile"] == "large":
        return (row["workers"], row["pacer_ms"], row["chunk_mib"], row.get("upload_cutoff_mib", 8)) == (8, 10, 64, 8)
    return row["workers"] == 128 and row["pacer_ms"] == 1


def main():
    data = rows()
    good = [r for r in data if r["status"] == "ok"]
    lines = ["# Transfer performance", "", "Measured on 2026-09-13 on this computer and Google Drive account.", "",
        f"**{len(good)}/{len(data)} measured transfers passed complete path, size and MD5 validation.**",
        "Raw measurements include every completed case, including failures if present. See [measurements.jsonl](results/measurements.jsonl).", "",
        "## Production settings versus the original copier", "",
        "Times below include full destination verification. For mounted uploads/copies, this waits for matching cloud metadata; the early filesystem return is not counted as completion.", "",
        "| Dataset | Direction | Original seconds | Direct API seconds, median (range) | Direct runs | Ratio, original/direct |",
        "|---|---|---:|---:|---:|---:|"]
    summary = []
    for profile in ("small", "large", "many"):
        for direction in ("download", "upload", "cloud-copy"):
            base = [r for r in good if r["profile"] == profile and r["direction"] == direction and r["backend"] == "robocopy" and r["workers"] == 16 and r["restartable"] and not r.get("warm")]
            chosen = [r for r in good if r["profile"] == profile and r["direction"] == direction and selected(r)]
            if not base or not chosen:
                continue
            before, after = median(base), median(chosen)
            low, high = min(r["verified_seconds"] for r in chosen), max(r["verified_seconds"] for r in chosen)
            lines.append(f"| {profile} | {direction} | {before:.2f} (n={len(base)}) | {after:.2f} ({low:.2f}–{high:.2f}) | {len(chosen)} | {before / after:.2f}× |")
            summary.append(dict(profile=profile, direction=direction, original_verified_seconds=before,
                                direct_verified_seconds=after, direct_runs=len(chosen), ratio=before/after))
    lines += ["", "**Download rows are different cache conditions:** the original path uses Drive for desktop's cache (warm/unspecified); direct API reads bypass that cache. A ratio below one means the cached filesystem route won. It does not show slower local disk copying by the direct engine.", "",
        "## Explicitly cached downloads", "", "All source bytes were read immediately before each timed case. These measure copying cached content, not Internet download throughput.", "",
        "| Dataset | Method | Workers | Restartable | Verified seconds |", "|---|---|---:|---|---:|"]
    for r in good:
        if r.get("warm"):
            lines.append(f"| {r['profile']} | {r['backend']} | {r['workers']} | {r['restartable']} | {r['verified_seconds']:.3f} |")
    lines += ["", "## Method and scope", "",
        "- `small`: 128 × 32 KiB files, 4 MiB total, one folder.",
        "- `large`: 4 × 16 MiB files, 64 MiB total. This is a medium-size file test, not a multi-gigabyte stress test.",
        "- `many`: 2,048 × 8 KiB files, 16 MiB total across 64 subfolders.",
        "- Synthetic incompressible bytes, fresh destination for every case, source unchanged, all relative paths, sizes and MD5s compared.",
        "- Windows 11 Home 25H2, i7-13650HX (14 cores / 20 threads), 32 GB installed RAM, Python 3.13.15, rclone 1.75.1.",
        "- Serial network experiments on the user's normal machine and account. OS scheduling, other applications, network and Google service load were not controlled.",
        "- Mounted paths use `G:/My Drive`; API paths use a separately authenticated `gdrive:` remote. All cloud cases use the same account.",
        "- Verification of cloud destinations polls API-visible metadata until all hashes match. Reported time is an upper bound including listing/polling delay, not the exact server completion timestamp.",
        "- Direct API copy time is also preserved in the raw data. Rclone returns after the API transfer; the additional independent manifest check occurs afterward.",
        "- Baseline settings are Robocopy `/MT:16 /Z`; the screen also includes Python's sequential copy, other worker counts, pacing, listing, upload chunks, download streams/cutoffs and independent folder processes.",
        "- Most screening settings have one observation; finalists have repeated observations. Ranges and sample counts matter more than a single fastest observation.",
        "- Coverage does not include native Google Docs/Sheets, shortcuts, shared-drive permissions, cross-account copies, million-file trees or multi-gigabyte files.", "",
        "## Why these routes behave differently", "",
        "Google Drive for desktop can serve streamed files from its local cache, which explains sub-second cached reads. See [Google's streaming/cache documentation](https://support.google.com/drive/answer/13470231?hl=en).",
        "Rclone can perform server-side copies when supported by the remote, avoiding a local download/upload round trip. See [rclone copy](https://rclone.org/commands/rclone_copy/) and [Drive backend options](https://rclone.org/drive/).",
        "Robocopy supports parallel workers and restartable copying; restartable mode has a recovery benefit and can have overhead. See [Microsoft's Robocopy documentation](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/robocopy).", "",
        "## Complete setting summary", "",
        "Each row groups identical measured settings. All times are seconds. `p` is minimum Drive pacing in milliseconds; `jobs` is independent folder processes. Raw records retain additional flags and exact timestamps.", "",
        "| Direction | Dataset | Backend | Workers | Z | Fast list | p | Chunk MiB | Streams | Cutoff MiB | Warm | Upload cutoff MiB | Jobs | n | Copy median | Verified median |",
        "|---|---|---|---:|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|"]
    for key, values in sorted(groups(data).items()):
        passed = [r for r in values if r["status"] == "ok"]
        if not passed:
            lines.append(f"| {key} | FAILED |")
            continue
        d, p, b, w, z, f, pace, chunk, streams, cutoff, seed, warm, upload, jobs = key
        lines.append(f"| {d} | {p} | {b} | {w} | {z} | {f} | {pace} | {chunk} | {streams} | {cutoff} | {warm} | {upload} | {jobs} | {len(passed)} | {median(passed, 'copy_seconds'):.3f} | {median(passed):.3f} |")
    (ROOT / "PERFORMANCE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (ROOT / "results" / "comparison.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
