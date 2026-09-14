# Work log

## 2026-09-13 — Open-source release

At the user's explicit request, added an MIT license and README licensing notice
for publication at https://github.com/Hung-Chi970104/parallel-copy. Credentials,
downloaded engines and generated benchmark payloads remain ignored. Application
code and measured results are unchanged.

## 2026-09-13 — Extract and optimize the personal copy application

User request: "Sure why dont you make it as a personal project, and put the thing
in there, btw help me also see if it speeds up transferring files in google drive
not just cloud to local. If not build it and fully test it and report how good is
the performance. I wanna see the performance comparison for cloud to local, local
to cloud, and cloud to cloud". Follow-ups require measurement-driven iteration
until further changes are no longer meaningful and explicit testing of large
folders with many small files.

Moved the existing Python window, launcher and tests out of workspace tools into
this independent personal project. Added a verified portable rclone installation,
separate OAuth login, cloud folder browsing and direct Drive transfers. The user
completed Google's consent page and enabled Drive API for their existing desktop
OAuth client. Calendar tokens were not reused or changed.

Benchmark design: synthetic incompressible binary data only; serial test cases,
unique destinations, retained raw outcomes, complete path/size/MD5 validation.
Warm DriveFS reads are separate from uncached direct downloads. Filesystem upload
times and remote-observed completion times are distinct. Initial tuning screens
sequential Python, the original Robocopy settings, Robocopy without restartable
mode, and several rclone transfer counts. Final results and limits belong in
PERFORMANCE.md, generated from the retained measurements by `report.py`.

Completed 143 timed folder transfers: all full path/size/MD5 comparisons passed.
The study covers all three directions, 128-file flat folders, 2,048 files across
64 subfolders, 4 x 16 MiB files, and 2 x 256 MiB files. Finalists were repeated;
single-run larger-payload screening and cache limitations are explicit in the
report. Increasing concurrency or splitting every workload into independent
processes did not universally help. The selected presets retain the improvements
that held up on their represented workload; raw results include slower variants.

The user also requested: "Hey btw remember to clean up the junks when done, and
the app should also do the same once done it should automatically clean up the
junk". Each application job now owns and removes its temporary logs/cache after
reading the final output, including Stop. Cancellation kills owned child processes.
Folder-picker workers are stopped when closed. Launching the GUI avoids generating
Python bytecode caches. Credentials and the installed engine remain; sources,
completed destinations and Google's managed cache are preserved. Interrupted
destination files can remain for retry, as documented in README.

All 18 local application tests pass, including a real GUI copy and process-tree
cancellation. Live Drive conformance passes uploads, downloads, server copies,
Unicode, empty files/folders, keep-existing and replacement choices, the many-file
GUI route, and its scratch cleanup. Evidence is under `results/`.

Archived and integrity-tested the benchmark logs and manifests, permanently
removed the exact generated cloud folder after checking its identity and recorded
runs, verified its absence, and removed local payloads/test caches. Removed the two
completed prototype fixture logs and the original completed TIGP copy log. The
cleanup receipt records cloud and local completion. The initial cleanup identity
check stopped safely because rooted rclone stat omits the expected name; resolving
the unique folder through its parent listing supplied the verified identity.
