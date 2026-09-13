# Parallel Copy

Personal Windows Python application for measured, non-destructive folder copying.
Use Robocopy for filesystem paths and rclone for direct Google Drive transfers.
Never use sync, mirror, move, purge or delete as a normal transfer operation.
Keep tokens, downloaded executables and generated benchmark payloads in ignored `.local/`.
Benchmark only generated data inside an explicitly named benchmark directory.
Distinguish cached filesystem completion from cloud API completion. Report failed
and incomplete runs; do not claim a warm-cache result measures Internet download speed.
Preserve raw measurements under `results/`, and describe limitations in the report.
Run `python -m unittest discover -s tests -v` before committing code.

