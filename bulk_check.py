"""Larger payload confirmation and actual parallel-range download comparisons."""
import subprocess
from benchmark import prepare, DATA, CLOUD_ROOT, run_case
from transfer_engine import rclone_base


def main():
    prepare()
    subprocess.run(rclone_base() + ["copy", str(DATA / "source" / "bulk"),
        f"gdrive:{CLOUD_ROOT}/seed/bulk", "--transfers", "8", "--drive-chunk-size", "64M",
        "--drive-pacer-min-sleep", "10ms", "--stats", "5s"], check=True)
    # This is the first mounted read of a freshly API-seeded payload, but DriveFS
    # cache remains externally managed. Do not claim a controlled cold-cache test.
    for direction in ("download", "upload", "cloud-copy"):
        run_case(direction, "robocopy", "bulk", 16, True, 6)
        run_case(direction, "rclone", "bulk", 8, False, 6,
                 fast_list=True, pacer_ms=10, chunk_mib=64)
    for streams in (0, 4, 8):
        run_case("download", "rclone", "bulk", 8, False, 6,
                 streams=streams, fast_list=True, pacer_ms=10,
                 chunk_mib=64, cutoff_mib=64)


if __name__ == "__main__":
    main()
