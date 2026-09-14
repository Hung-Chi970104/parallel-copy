"""Delete ONLY this study's generated cloud dataset after recording its identity.

Run after every benchmark and live check has finished. Never called by normal
copies. Payloads are disposable; raw measurements and archived logs are retained.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import zipfile

from benchmark import CLOUD_ROOT, DATA, RESULTS
from transfer_engine import ROOT, rclone_base


def listing(remote, *options):
    result = subprocess.run(rclone_base() + ["lsjson", remote, *options],
                            check=True, capture_output=True, text=True, encoding="utf-8", timeout=180)
    return json.loads(result.stdout)


def main():
    def require(condition, message):
        if not condition:
            raise RuntimeError(message)
    require(CLOUD_ROOT == "ParallelCopy-benchmark-20260913", "Unexpected benchmark namespace")
    remote = "gdrive:" + CLOUD_ROOT
    proof_path = ROOT / "results" / "cleanup.json"
    archive = ROOT / "results" / "benchmark-logs.zip"
    require(DATA.resolve().is_relative_to(ROOT.resolve()) and DATA.name == "benchmark", "Unexpected local benchmark path")
    # Retain all per-case logs and source manifests before removing payloads.
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as out:
        for path in sorted(DATA.glob("*.log")) + sorted(DATA.glob("*.json")):
            out.write(path, path.name)
    matches = [item for item in listing("gdrive:", "--dirs-only") if item["Name"] == CLOUD_ROOT]
    require(len(matches) == 1 and matches[0]["IsDir"], "Missing or ambiguous cloud folder identity")
    metadata = matches[0]
    children = listing(remote)
    require(all(item["IsDir"] and (item["Name"] in ("seed", "runs") or item["Name"].startswith("conformance-")) for item in children), "Unexpected content in benchmark root: cleanup refused")
    expected = {json.loads(line)["id"] for line in RESULTS.read_text().splitlines()}
    runs = listing(remote + "/runs", "--dirs-only")
    require(all(item["Name"] in expected for item in runs), "Unrecorded run folder: cleanup refused")
    proof = dict(utc=datetime.now(timezone.utc).isoformat(), remote=remote,
                 folder_id=metadata["ID"], top_level_names=[item["Name"] for item in children],
                 recorded_cloud_run_folders=len(runs), logs_archive=archive.name,
                 cloud_deleted=False, local_deleted=False)
    proof_path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    subprocess.run(rclone_base() + ["purge", remote, "--drive-use-trash=false"], check=True, timeout=600)
    remaining = listing("gdrive:", "--dirs-only", "--max-depth", "1")
    require(all(item["ID"] != metadata["ID"] and item["Name"] != CLOUD_ROOT for item in remaining), "Benchmark root still exists")
    proof["cloud_deleted"] = True
    proof_path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(proof), flush=True)
    print("Cloud dataset removed and absence verified. Remove only the resolved local benchmark directory next.")


if __name__ == "__main__":
    main()
