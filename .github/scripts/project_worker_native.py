"""Fetch pinned native inputs and relocate a complete interpreter/Office runtime."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request


def download(url, destination, digest):
    if not destination.exists():
        with urllib.request.urlopen(url, timeout=300) as response, destination.open("wb") as target:
            shutil.copyfileobj(response, target)
    with destination.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != digest:
        raise ValueError(f"native input digest mismatch: {url}")


def prepare(target, output):
    lock = json.loads(Path(".github/requirements/project-worker-native.json").read_text())
    platform = lock["platforms"][target]
    output.mkdir(parents=True, exist_ok=True)
    download(lock["wordPerfectFixture"]["url"], output / "wp6.wpd", lock["wordPerfectFixture"]["sha256"])
    download(platform["pythonUrl"], output / "python.tar.gz", platform["pythonSha256"])
    with tarfile.open(output / "python.tar.gz") as archive:
        archive.extractall(output, filter="data")
    installer = output / ("office.dmg" if target.startswith("darwin") else "office.msi" if target.startswith("win") else "office.tar.gz")
    download(platform["officeUrl"], installer, platform["officeSha256"])
    with tempfile.TemporaryDirectory(prefix="semantica-office-install-") as temporary:
        scratch = Path(temporary)
        if target.startswith("darwin"):
            mount = scratch / "mounted"
            subprocess.run(["hdiutil", "attach", "-readonly", "-nobrowse", "-mountpoint", str(mount), str(installer)], check=True)
            try:
                shutil.copytree(mount / "LibreOffice.app", output / "office", symlinks=False)
            finally:
                subprocess.run(["hdiutil", "detach", str(mount)], check=True)
        elif target.startswith("win"):
            subprocess.run(["msiexec.exe", "/a", str(installer.resolve()), "/qn", f"TARGETDIR={scratch}"], check=True)
            executable = next(scratch.rglob("soffice.com"))
            shutil.copytree(executable.parent.parent, output / "office", symlinks=False)
        else:
            with tarfile.open(installer) as archive:
                archive.extractall(scratch, filter="data")
            unpacked = scratch / "unpacked"
            for package in scratch.rglob("*.deb"):
                subprocess.run(["dpkg-deb", "-x", str(package), str(unpacked)], check=True)
            office = next((unpacked / "opt").glob("libreoffice*"))
            shutil.copytree(office, output / "office", symlinks=False)
    (output / "office-release.json").write_text(json.dumps({"version": lock["officeVersion"], "executable": platform["officeExecutable"],
        "url": platform["officeUrl"], "sha256": platform["officeSha256"]}, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=["darwin-arm64", "linux-x64", "win-x64"])
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    prepare(args.target, args.output)
