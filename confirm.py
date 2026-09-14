"""Repeat finalists and interleave a second original-copier baseline."""
from benchmark import run_case


def main():
    for trial in (5, 6):
        for direction in ("download", "upload", "cloud-copy"):
            if trial == 5 and direction != "download":
                run_case(direction, "robocopy", "many", 16, True, trial)
            backend = "rclone" if direction == "download" else "folders"
            run_case(direction, backend, "many", 128, False, trial,
                     fast_list=True, pacer_ms=1, folder_jobs=16)
            if direction == "download":
                run_case(direction, "rclone", "many", 64, False, trial,
                         fast_list=True, pacer_ms=1)
            if trial == 6 and direction != "download":
                run_case(direction, "folders", "many", 64, False, trial,
                         fast_list=True, pacer_ms=10, folder_jobs=8)
        for direction in ("download", "upload", "cloud-copy"):
            run_case(direction, "rclone", "large", 8, False, trial,
                     fast_list=True, pacer_ms=10, chunk_mib=64)


if __name__ == "__main__":
    main()
