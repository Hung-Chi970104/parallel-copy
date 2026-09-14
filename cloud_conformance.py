"""Live correctness checks, separate from timings. Only generated fixture files.

Exercises the actual GUI's transfer planner for uploads, downloads and server
copies, including Unicode names, empty files/folders and replacement semantics.
"""
import json
from pathlib import Path
import subprocess
import time
from benchmark import DATA, CLOUD_ROOT, manifest, remote_manifest
from transfer_engine import direct_plan, rclone_base


def copy(source, parent, replace=False, profile="Small files"):
    log = DATA / f"conformance-{time.time_ns()}.log"
    plan = direct_plan(source, parent, 16, replace, log, profile=profile)
    result = subprocess.run(plan.command, capture_output=True, timeout=180)
    if result.returncode:
        raise RuntimeError(f"Live correctness transfer failed: {result.returncode}; log {log.name}")
    return plan.target


def main():
    source = DATA / "conformance" / "Unicode 板"
    source.mkdir(parents=True, exist_ok=True)
    (source / "empty folder").mkdir(exist_ok=True)
    (source / "empty.bin").write_bytes(b"")
    (source / "space and ü.txt").write_text("Original fixture", encoding="utf-8")
    cloud_parent = f"gdrive:{CLOUD_ROOT}/conformance-{time.time_ns()}"
    target = copy(source, cloud_parent)
    expected = manifest(source)
    assert remote_manifest(target) == expected, "Upload manifest mismatch"
    (source / "space and ü.txt").write_text("Changed fixture with different size", encoding="utf-8")
    copy(source, cloud_parent, replace=False)
    assert remote_manifest(target) == expected, "Keep-existing option overwrote a cloud file"
    copy(source, cloud_parent, replace=True)
    expected = manifest(source)
    assert remote_manifest(target) == expected, "Replacement did not update the cloud file"
    cloud_copy = copy(target, cloud_parent + "/copy")
    assert remote_manifest(cloud_copy) == expected, "Cloud-to-cloud manifest mismatch"
    destination = DATA / "conformance-download"
    destination.mkdir(exist_ok=True)
    download = copy(cloud_copy, destination, replace=True)
    assert manifest(Path(download)) == expected, "Download manifest mismatch"
    assert (Path(download) / "empty folder").is_dir(), "Empty folder not preserved"
    # Exercise the actual window, worker cleanup and new many-file route live.
    import tkinter as tk
    from parallel_copy import CopyApp
    root = tk.Tk()
    root.withdraw()
    try:
        app = CopyApp(root, str(source), cloud_parent + "/gui")
        app.profile.set("Many small files")
        app.workers.set("128")
        app.start()
        assert app.process is not None, "GUI failed to start cloud transfer"
        scratch_root = app.scratch.root
        deadline = time.monotonic() + 180
        while app.process is not None and time.monotonic() < deadline:
            root.update()
            time.sleep(.02)
        assert app.process is None, "GUI cloud copy timed out"
        assert "acknowledged" in app.status.get(), app.status.get()
        assert not scratch_root.exists(), "GUI did not clean transfer scratch"
        assert remote_manifest(app.target) == expected, "GUI cloud manifest mismatch"
    finally:
        if app.process:
            app.stop()
        root.destroy()
    many_copy = copy(target, cloud_parent + "/many-copy", profile="Many small files")
    assert remote_manifest(many_copy) == expected, "Many-file cloud-copy manifest mismatch"
    many_download_parent = DATA / "many-conformance-download"
    many_download_parent.mkdir(exist_ok=True)
    many_download = copy(many_copy, many_download_parent, profile="Many small files")
    assert manifest(many_download) == expected, "Many-file download manifest mismatch"
    result = {"status": "pass", "checks": ["unicode", "empty file", "empty folder",
              "upload", "download", "cloud-to-cloud", "keep existing", "replace changed",
              "many-file GUI upload", "GUI scratch cleanup", "many-file cloud-copy", "many-file download"],
              "fixture_remote": cloud_parent}
    (Path(__file__).resolve().parent / "results" / "cloud-conformance.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
