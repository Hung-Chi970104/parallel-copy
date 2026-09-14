"""Run final independent phases serially; stop on a failed harness or live check."""
import subprocess
import sys
from transfer_engine import ROOT


def main():
    phases = [("refine.py", "warm"), ("refine.py", "repeat-small"),
              ("confirm.py",), ("bulk_check.py",), ("cloud_conformance.py",)]
    for script, *arguments in phases:
        print(f"FINAL PHASE: {script} {' '.join(arguments)}", flush=True)
        subprocess.run([sys.executable, str(ROOT / script), *arguments], check=True)


if __name__ == "__main__":
    main()
