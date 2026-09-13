# Work log

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
PERFORMANCE.md; this entry does not claim all measurements are complete yet.
