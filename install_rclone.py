"""Download official rclone for Windows and verify its published SHA256 checksum."""
import hashlib
import io
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent


def install():
    version = urllib.request.urlopen("https://downloads.rclone.org/version.txt", timeout=30).read().decode().strip().split()[-1]
    name = f"rclone-{version}-windows-amd64.zip"
    base = f"https://downloads.rclone.org/{version}/"
    checksums = urllib.request.urlopen(base + "SHA256SUMS", timeout=30).read().decode()
    expected = next(line.split()[0] for line in checksums.splitlines() if line.split() and line.split()[-1].lstrip("*") == name)
    payload = urllib.request.urlopen(base + name, timeout=120).read()
    if hashlib.sha256(payload).hexdigest() != expected:
        raise RuntimeError("Official download checksum did not match")
    destination = ROOT / ".local" / "bin"
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        entry = next(n for n in archive.namelist() if n.endswith("/rclone.exe"))
        (destination / "rclone.exe").write_bytes(archive.read(entry))
    print(f"Installed {version}; official SHA256 verified: {expected}", flush=True)
    return destination / "rclone.exe"


if __name__ == "__main__":
    install()
