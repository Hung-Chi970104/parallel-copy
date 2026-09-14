# Transfer performance

Measured on 2026-09-13 on this computer and Google Drive account.

**143/143 measured transfers passed complete path, size and MD5 validation.**
Raw measurements include every completed case, including failures if present. See [measurements.jsonl](results/measurements.jsonl).

## Production settings versus the original copier

Times below include full destination verification. For mounted uploads/copies, this waits for matching cloud metadata; the early filesystem return is not counted as completion.

| Dataset | Direction | Original seconds | Direct API seconds, median (range) | Direct runs | Ratio, original/direct |
|---|---|---:|---:|---:|---:|
| small | download | 5.08 (n=1) | 2.08 (1.97–3.44) | 3 | 2.44× |
| small | upload | 19.06 (n=1) | 6.74 (6.15–7.44) | 3 | 2.83× |
| small | cloud-copy | 18.24 (n=1) | 8.24 (6.66–10.82) | 3 | 2.21× |
| large | download | 0.24 (n=1) | 3.46 (2.78–3.57) | 3 | 0.07× |
| large | upload | 8.35 (n=1) | 7.50 (6.44–9.08) | 3 | 1.11× |
| large | cloud-copy | 11.70 (n=1) | 7.32 (6.45–9.09) | 3 | 1.60× |
| many | download | 3.56 (n=1) | 9.93 (8.95–10.73) | 3 | 0.36× |
| many | upload | 166.52 (n=2) | 106.23 (61.76–132.68) | 3 | 1.57× |
| many | cloud-copy | 162.15 (n=2) | 93.07 (91.20–122.85) | 3 | 1.74× |
| bulk | download | 9.74 (n=1) | 10.06 (10.06–10.06) | 1 | 0.97× |
| bulk | upload | 24.13 (n=1) | 14.17 (14.17–14.17) | 1 | 1.70× |
| bulk | cloud-copy | 25.51 (n=1) | 7.28 (7.28–7.28) | 1 | 3.51× |

**Download rows are different cache conditions:** the original path uses Drive for desktop's cache (warm/unspecified); direct API reads bypass that cache. A ratio below one means the cached filesystem route won. It does not show slower local disk copying by the direct engine.

## Explicitly cached downloads

All source bytes were read immediately before each timed case. These measure copying cached content, not Internet download throughput.

| Dataset | Method | Workers | Restartable | Verified seconds |
|---|---|---:|---|---:|
| small | robocopy | 16 | True | 0.358 |
| small | robocopy | 8 | False | 0.351 |
| small | robocopy | 16 | False | 0.337 |
| small | robocopy | 32 | False | 0.300 |
| small | robocopy | 64 | False | 0.302 |
| small | python | 1 | False | 0.790 |
| large | robocopy | 16 | True | 0.267 |
| large | robocopy | 8 | False | 0.242 |
| large | robocopy | 16 | False | 0.279 |
| large | robocopy | 32 | False | 0.258 |
| large | robocopy | 64 | False | 0.253 |
| large | python | 1 | False | 0.241 |
| many | robocopy | 16 | True | 4.715 |
| many | robocopy | 8 | False | 5.351 |
| many | robocopy | 16 | False | 5.288 |
| many | robocopy | 32 | False | 4.851 |
| many | robocopy | 64 | False | 3.931 |
| many | python | 1 | False | 8.690 |

## Method and scope

- `small`: 128 × 32 KiB files, 4 MiB total, one folder.
- `large`: 4 × 16 MiB files, 64 MiB total. This is a medium-size file test, not a multi-gigabyte stress test.
- `many`: 2,048 × 8 KiB files, 16 MiB total across 64 subfolders.
- `bulk`: 2 × 256 MiB files, 512 MiB total, seeded through the API before the first mounted read. DriveFS cache was not forcibly cleared.
- Synthetic incompressible bytes, fresh destination for every case, source unchanged, all relative paths, sizes and MD5s compared.
- Windows 11 Home 25H2, i7-13650HX (14 cores / 20 threads), 32 GB installed RAM, Python 3.13.15, rclone 1.75.1.
- Serial network experiments on the user's normal machine and account. OS scheduling, other applications, network and Google service load were not controlled.
- Benchmark folders accumulated during the study and Drive for desktop indexed them. Later cases therefore did not run against a freshly idle, empty sync namespace; this is a practical comparison, not a controlled service-capacity claim.
- Mounted paths use `G:/My Drive`; API paths use a separately authenticated `gdrive:` remote. All cloud cases use the same account.
- Verification of cloud destinations polls API-visible metadata until all hashes match. Reported time is an upper bound including listing/polling delay, not the exact server completion timestamp.
- Direct API copy time is also preserved in the raw data. Rclone returns after the API transfer; the additional independent manifest check occurs afterward.
- The GUI reports engine completion and uses the engine's normal checksum checks. The full independent destination manifest comparison is an additional benchmark step; GUI polling adds a small display delay.
- Baseline settings are Robocopy `/MT:16 /Z`; the screen also includes Python's sequential copy, other worker counts, pacing, listing, upload chunks, download streams/cutoffs and independent folder processes.
- Most screening settings have one observation; finalists have repeated observations. Ranges and sample counts matter more than a single fastest observation.
- One serial cache-preparation attempt was interrupted before timing and replaced by parallel prefetch; see [setup-events.jsonl](results/setup-events.jsonl). All source bytes are read before each explicitly warmed timer starts.
- Coverage does not include native Google Docs/Sheets, shortcuts, shared-drive permissions, cross-account copies, million-file trees or multi-gigabyte files.

## Optimization decisions

The GUI and this report read their default settings from `PRESETS` in `transfer_engine.py`. Worker counts remain adjustable.

- Ordinary small folders use the repeated high-concurrency direct API configuration.
- Trees containing thousands of small files use independent folder processes for remote destinations, and a single direct API process for downloads.
- Larger files use fewer transfers and larger upload chunks. Existing files are kept by default; replacement is an explicit choice.
- Grouped filter batches and the most aggressive single-process tree uploads were tested and rejected as universal defaults because they regressed on other directions or repeats.
- Cached Windows copying remains available. The cached tests did not justify removing restartable mode from the default merely to pursue small timing differences.
- Individual files remain individually accessible in Drive, so directory and per-file operations remain part of the cost.
These are the strongest measured settings for the represented workloads, not a proof of a global optimum across all networks, file trees or future Google service conditions. The repeated finalists and failed-to-improve alternatives define the stopping point for this tuning pass.

## Why these routes behave differently

Google Drive for desktop can serve streamed files from its local cache, which explains sub-second cached reads. See [Google's streaming/cache documentation](https://support.google.com/drive/answer/13470231?hl=en).
Rclone can perform server-side copies when supported by the remote, avoiding a local download/upload round trip. See [rclone copy](https://rclone.org/commands/rclone_copy/) and [Drive backend options](https://rclone.org/drive/).
Robocopy supports parallel workers and restartable copying; restartable mode has a recovery benefit and can have overhead. See [Microsoft's Robocopy documentation](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/robocopy).

## Complete setting summary

Each row groups identical measured settings. All times are seconds. `p` is minimum Drive pacing in milliseconds; `jobs` is independent folder processes. Raw records retain additional flags and exact timestamps.

| Direction | Dataset | Backend | Workers | Z | Fast list | p | Chunk MiB | Streams | Cutoff MiB | Warm | Upload cutoff MiB | Jobs | n | Copy median | Verified median |
|---|---|---|---:|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|
| cloud-copy | bulk | rclone | 8 | False | True | 10 | 64 | 4 | 256 | False | 8 | 8 | 1 | 5.935 | 7.276 |
| cloud-copy | bulk | robocopy | 16 | True | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 8.044 | 25.510 |
| cloud-copy | large | python | 1 | False | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 0.425 | 9.562 |
| cloud-copy | large | rclone | 1 | False | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 9.270 | 10.493 |
| cloud-copy | large | rclone | 8 | False | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 7.420 | 8.640 |
| cloud-copy | large | rclone | 8 | False | True | 10 | 64 | 4 | 256 | False | 8 | 8 | 3 | 6.103 | 7.315 |
| cloud-copy | large | rclone | 32 | False | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 6.194 | 7.419 |
| cloud-copy | large | robocopy | 16 | False | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 0.280 | 8.387 |
| cloud-copy | large | robocopy | 16 | True | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 0.536 | 11.699 |
| cloud-copy | many | batches | 64 | False | True | 10 | 8 | 4 | 256 | False | 8 | 8 | 1 | 120.583 | 124.398 |
| cloud-copy | many | folders | 64 | False | True | 10 | 8 | 4 | 256 | False | 8 | 8 | 2 | 103.538 | 107.635 |
| cloud-copy | many | folders | 128 | False | True | 10 | 8 | 4 | 256 | False | 8 | 16 | 3 | 89.048 | 93.072 |
| cloud-copy | many | rclone | 32 | False | True | 10 | 8 | 4 | 256 | False | 8 | 8 | 1 | 133.657 | 138.070 |
| cloud-copy | many | rclone | 64 | False | True | 10 | 8 | 4 | 256 | False | 8 | 8 | 1 | 123.021 | 126.915 |
| cloud-copy | many | rclone | 128 | False | True | 1 | 8 | 4 | 256 | False | 8 | 16 | 1 | 154.758 | 157.747 |
| cloud-copy | many | robocopy | 16 | True | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 2 | 80.506 | 162.155 |
| cloud-copy | small | python | 1 | False | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 4.036 | 19.349 |
| cloud-copy | small | rclone | 1 | False | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 152.625 | 153.996 |
| cloud-copy | small | rclone | 8 | False | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 22.447 | 23.753 |
| cloud-copy | small | rclone | 8 | False | True | 10 | 8 | 4 | 256 | False | 8 | 8 | 1 | 24.275 | 25.533 |
| cloud-copy | small | rclone | 16 | False | True | 10 | 8 | 4 | 256 | False | 8 | 8 | 1 | 14.403 | 15.709 |
| cloud-copy | small | rclone | 32 | False | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 20.286 | 21.553 |
| cloud-copy | small | rclone | 32 | False | True | 10 | 8 | 4 | 256 | False | 8 | 8 | 1 | 9.569 | 10.800 |
| cloud-copy | small | rclone | 64 | False | True | 5 | 8 | 4 | 256 | False | 8 | 8 | 1 | 6.540 | 7.850 |
| cloud-copy | small | rclone | 64 | False | True | 10 | 8 | 4 | 256 | False | 8 | 8 | 3 | 7.663 | 9.394 |
| cloud-copy | small | rclone | 128 | False | True | 1 | 8 | 4 | 256 | False | 8 | 8 | 3 | 6.887 | 8.244 |
| cloud-copy | small | rclone | 128 | False | True | 5 | 8 | 4 | 256 | False | 8 | 8 | 1 | 5.901 | 7.441 |
| cloud-copy | small | rclone | 128 | False | True | 10 | 8 | 4 | 256 | False | 8 | 8 | 1 | 6.713 | 8.042 |
| cloud-copy | small | robocopy | 16 | False | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 3.815 | 19.994 |
| cloud-copy | small | robocopy | 16 | True | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 3.640 | 18.245 |
| download | bulk | rclone | 8 | False | True | 10 | 64 | 0 | 64 | False | 8 | 8 | 1 | 10.841 | 11.781 |
| download | bulk | rclone | 8 | False | True | 10 | 64 | 4 | 64 | False | 8 | 8 | 1 | 9.008 | 9.863 |
| download | bulk | rclone | 8 | False | True | 10 | 64 | 4 | 256 | False | 8 | 8 | 1 | 9.138 | 10.060 |
| download | bulk | rclone | 8 | False | True | 10 | 64 | 8 | 64 | False | 8 | 8 | 1 | 9.967 | 10.878 |
| download | bulk | robocopy | 16 | True | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 8.717 | 9.744 |
| download | large | python | 1 | False | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 2.576 | 2.694 |
| download | large | python | 1 | False | False | 100 | 8 | 4 | 256 | True | 8 | 8 | 1 | 0.123 | 0.241 |
| download | large | rclone | 1 | False | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 4.851 | 4.938 |
| download | large | rclone | 8 | False | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 2.985 | 3.072 |
| download | large | rclone | 8 | False | True | 10 | 64 | 4 | 256 | False | 8 | 8 | 3 | 3.355 | 3.458 |
| download | large | rclone | 32 | False | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 2.817 | 2.916 |
| download | large | robocopy | 8 | False | False | 100 | 8 | 4 | 256 | True | 8 | 8 | 1 | 0.125 | 0.242 |
| download | large | robocopy | 16 | False | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 2.443 | 2.551 |
| download | large | robocopy | 16 | False | False | 100 | 8 | 4 | 256 | True | 8 | 8 | 1 | 0.147 | 0.279 |
| download | large | robocopy | 16 | True | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 0.154 | 0.240 |
| download | large | robocopy | 16 | True | False | 100 | 8 | 4 | 256 | True | 8 | 8 | 1 | 0.146 | 0.267 |
| download | large | robocopy | 32 | False | False | 100 | 8 | 4 | 256 | True | 8 | 8 | 1 | 0.141 | 0.258 |
| download | large | robocopy | 64 | False | False | 100 | 8 | 4 | 256 | True | 8 | 8 | 1 | 0.130 | 0.253 |
| download | many | batches | 64 | False | True | 10 | 8 | 4 | 256 | False | 8 | 8 | 1 | 13.705 | 14.196 |
| download | many | batches | 128 | False | True | 10 | 8 | 4 | 256 | False | 8 | 16 | 1 | 81.898 | 82.256 |
| download | many | folders | 64 | False | True | 10 | 8 | 4 | 256 | False | 8 | 8 | 1 | 68.924 | 69.410 |
| download | many | python | 1 | False | False | 100 | 8 | 4 | 256 | True | 8 | 8 | 1 | 8.273 | 8.690 |
| download | many | rclone | 32 | False | True | 10 | 8 | 4 | 256 | False | 8 | 8 | 1 | 62.324 | 62.694 |
| download | many | rclone | 64 | False | True | 1 | 8 | 4 | 256 | False | 8 | 8 | 2 | 64.951 | 65.675 |
| download | many | rclone | 64 | False | True | 10 | 8 | 4 | 256 | False | 8 | 8 | 1 | 33.668 | 33.910 |
| download | many | rclone | 128 | False | True | 1 | 8 | 4 | 256 | False | 8 | 16 | 3 | 9.357 | 9.930 |
| download | many | robocopy | 8 | False | False | 100 | 8 | 4 | 256 | True | 8 | 8 | 1 | 4.572 | 5.351 |
| download | many | robocopy | 16 | False | False | 100 | 8 | 4 | 256 | True | 8 | 8 | 1 | 4.148 | 5.288 |
| download | many | robocopy | 16 | True | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 3.123 | 3.560 |
| download | many | robocopy | 16 | True | False | 100 | 8 | 4 | 256 | True | 8 | 8 | 1 | 3.953 | 4.715 |
| download | many | robocopy | 32 | False | False | 100 | 8 | 4 | 256 | True | 8 | 8 | 1 | 4.124 | 4.851 |
| download | many | robocopy | 64 | False | False | 100 | 8 | 4 | 256 | True | 8 | 8 | 1 | 3.413 | 3.931 |
| download | small | python | 1 | False | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 0.506 | 0.530 |
| download | small | python | 1 | False | False | 100 | 8 | 4 | 256 | True | 8 | 8 | 1 | 0.764 | 0.790 |
| download | small | rclone | 1 | False | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 34.444 | 34.465 |
| download | small | rclone | 8 | False | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 6.125 | 6.144 |
| download | small | rclone | 8 | False | True | 10 | 8 | 4 | 256 | False | 8 | 8 | 1 | 5.353 | 5.372 |
| download | small | rclone | 16 | False | True | 10 | 8 | 4 | 256 | False | 8 | 8 | 1 | 3.594 | 3.614 |
| download | small | rclone | 32 | False | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 2.906 | 2.926 |
| download | small | rclone | 32 | False | True | 10 | 8 | 4 | 256 | False | 8 | 8 | 1 | 2.348 | 2.380 |
| download | small | rclone | 64 | False | True | 5 | 8 | 4 | 256 | False | 8 | 8 | 1 | 2.633 | 2.657 |
| download | small | rclone | 64 | False | True | 10 | 8 | 4 | 256 | False | 8 | 8 | 3 | 3.435 | 3.474 |
| download | small | rclone | 128 | False | True | 1 | 8 | 4 | 256 | False | 8 | 8 | 3 | 2.046 | 2.080 |
| download | small | rclone | 128 | False | True | 5 | 8 | 4 | 256 | False | 8 | 8 | 1 | 1.990 | 2.030 |
| download | small | rclone | 128 | False | True | 10 | 8 | 4 | 256 | False | 8 | 8 | 1 | 2.748 | 2.773 |
| download | small | robocopy | 8 | False | False | 100 | 8 | 4 | 256 | True | 8 | 8 | 1 | 0.292 | 0.351 |
| download | small | robocopy | 16 | False | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 4.525 | 4.565 |
| download | small | robocopy | 16 | False | False | 100 | 8 | 4 | 256 | True | 8 | 8 | 1 | 0.278 | 0.337 |
| download | small | robocopy | 16 | True | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 5.046 | 5.082 |
| download | small | robocopy | 16 | True | False | 100 | 8 | 4 | 256 | True | 8 | 8 | 1 | 0.281 | 0.358 |
| download | small | robocopy | 32 | False | False | 100 | 8 | 4 | 256 | True | 8 | 8 | 1 | 0.242 | 0.300 |
| download | small | robocopy | 64 | False | False | 100 | 8 | 4 | 256 | True | 8 | 8 | 1 | 0.244 | 0.302 |
| upload | bulk | rclone | 8 | False | True | 10 | 64 | 4 | 256 | False | 8 | 8 | 1 | 12.722 | 14.171 |
| upload | bulk | robocopy | 16 | True | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 1.602 | 24.134 |
| upload | large | python | 1 | False | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 0.356 | 8.428 |
| upload | large | rclone | 1 | False | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 12.193 | 13.490 |
| upload | large | rclone | 8 | False | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 8.693 | 9.839 |
| upload | large | rclone | 8 | False | True | 10 | 64 | 4 | 256 | False | 8 | 8 | 3 | 6.259 | 7.495 |
| upload | large | rclone | 8 | False | True | 10 | 64 | 4 | 256 | False | 64 | 8 | 1 | 5.077 | 6.202 |
| upload | large | rclone | 32 | False | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 7.807 | 9.573 |
| upload | large | rclone | 32 | False | True | 10 | 64 | 4 | 256 | False | 64 | 8 | 1 | 4.928 | 6.170 |
| upload | large | robocopy | 16 | False | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 0.331 | 11.715 |
| upload | large | robocopy | 16 | True | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 0.257 | 8.351 |
| upload | many | batches | 64 | False | True | 10 | 8 | 4 | 256 | False | 8 | 8 | 1 | 152.180 | 155.173 |
| upload | many | folders | 64 | False | True | 10 | 8 | 4 | 256 | False | 8 | 8 | 2 | 118.390 | 122.232 |
| upload | many | folders | 128 | False | True | 10 | 8 | 4 | 256 | False | 8 | 16 | 3 | 103.230 | 106.235 |
| upload | many | rclone | 32 | False | True | 10 | 8 | 4 | 256 | False | 8 | 8 | 1 | 147.259 | 151.689 |
| upload | many | rclone | 64 | False | True | 10 | 8 | 4 | 256 | False | 8 | 8 | 1 | 140.818 | 145.155 |
| upload | many | rclone | 128 | False | True | 1 | 8 | 4 | 256 | False | 8 | 16 | 1 | 317.007 | 320.071 |
| upload | many | robocopy | 16 | True | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 2 | 63.439 | 166.516 |
| upload | small | python | 1 | False | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 3.446 | 17.978 |
| upload | small | rclone | 1 | False | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 167.215 | 168.563 |
| upload | small | rclone | 8 | False | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 24.413 | 25.737 |
| upload | small | rclone | 8 | False | True | 10 | 8 | 4 | 256 | False | 8 | 8 | 1 | 23.204 | 24.525 |
| upload | small | rclone | 16 | False | True | 10 | 8 | 4 | 256 | False | 8 | 8 | 1 | 13.780 | 15.065 |
| upload | small | rclone | 32 | False | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 19.100 | 20.374 |
| upload | small | rclone | 32 | False | True | 10 | 8 | 4 | 256 | False | 8 | 8 | 1 | 8.620 | 9.988 |
| upload | small | rclone | 64 | False | True | 5 | 8 | 4 | 256 | False | 8 | 8 | 1 | 6.353 | 7.611 |
| upload | small | rclone | 64 | False | True | 10 | 8 | 4 | 256 | False | 8 | 8 | 3 | 6.092 | 7.448 |
| upload | small | rclone | 128 | False | True | 1 | 8 | 4 | 256 | False | 8 | 8 | 3 | 5.279 | 6.742 |
| upload | small | rclone | 128 | False | True | 5 | 8 | 4 | 256 | False | 8 | 8 | 1 | 5.221 | 6.562 |
| upload | small | rclone | 128 | False | True | 10 | 8 | 4 | 256 | False | 8 | 8 | 1 | 5.838 | 7.064 |
| upload | small | robocopy | 16 | False | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 3.169 | 17.583 |
| upload | small | robocopy | 16 | True | False | 100 | 8 | 4 | 256 | False | 8 | 8 | 1 | 5.324 | 19.058 |

## Correctness and cleanup evidence

[Local test results](results/tests.txt) cover copies, replacement choices, extra-file preservation, invalid paths, GUI completion, Stop, child-process termination and scoped scratch cleanup.

Live Google Drive conformance: **pass**. Checks: unicode, empty file, empty folder, upload, download, cloud-to-cloud, keep existing, replace changed, many-file GUI upload, GUI scratch cleanup, many-file cloud-copy, many-file download. See [the recorded result](results/cloud-conformance.json).

Generated cloud dataset removed and absence checked: **True**. Generated local dataset removed: **True**.
Source manifests and transfer logs are retained in [benchmark-logs.zip](results/benchmark-logs.zip); [cleanup.json](results/cleanup.json) records the exact generated folder identity.
