"""Fetch and verify only the model bytes admitted by the native-worker release lock."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import urllib.request


CHUNK_BYTES = 4 * 1024 * 1024
MAX_CONNECTIONS = 32
DOWNLOAD_TIMEOUT = 300
CONTENT_RANGE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")


def digest_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def range_total(url: str) -> int:
    request = urllib.request.Request(url, headers={"Range": "bytes=0-0"})
    with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT) as response:
        match = CONTENT_RANGE.fullmatch(response.headers.get("Content-Range", ""))
        if response.status != 206 or not match or (match.group(1), match.group(2)) != ("0", "0"):
            raise ValueError(f"model server does not honor byte ranges: {url}")
        if len(response.read()) != 1:
            raise ValueError(f"invalid byte-range probe response: {url}")
        return int(match.group(3))


def download_range(url: str, start: int, end: int, total: int, part: Path) -> None:
    partial = part.with_name(part.name + ".partial")
    request = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}"})
    try:
        with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT) as response:
            match = CONTENT_RANGE.fullmatch(response.headers.get("Content-Range", ""))
            if (response.status != 206 or not match
                    or tuple(map(int, match.groups())) != (start, end, total)):
                raise ValueError(f"invalid model range response {start}-{end}/{total}: {url}")
            with partial.open("wb") as stream:
                shutil.copyfileobj(response, stream)
        expected = end - start + 1
        if partial.stat().st_size != expected:
            raise ValueError(f"incomplete model range {start}-{end}/{total}: {url}")
        os.replace(partial, part)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise


def download_file(url: str, target: Path, expected_sha256: str) -> None:
    parts = target.with_name(target.name + ".parts")
    assembled = target.with_name(target.name + ".partial")
    if target.exists():
        if digest_file(target) == expected_sha256:
            shutil.rmtree(parts, ignore_errors=True)
            assembled.unlink(missing_ok=True)
            return
        target.unlink()

    total = range_total(url)
    if total <= 0:
        raise ValueError(f"empty model response: {url}")
    parts.mkdir(parents=True, exist_ok=True)
    ranges = [(start, min(start + CHUNK_BYTES, total) - 1)
              for start in range(0, total, CHUNK_BYTES)]
    pending = []
    for start, end in ranges:
        part = parts / f"{start}-{end}.part"
        if not part.exists() or part.stat().st_size != end - start + 1:
            part.unlink(missing_ok=True)
            pending.append((start, end, part))

    with ThreadPoolExecutor(max_workers=MAX_CONNECTIONS) as pool:
        futures = [pool.submit(download_range, url, start, end, total, part)
                   for start, end, part in pending]
        for future in as_completed(futures):
            future.result()

    try:
        with assembled.open("wb") as stream:
            for start, end in ranges:
                with (parts / f"{start}-{end}.part").open("rb") as part:
                    shutil.copyfileobj(part, stream)
        if assembled.stat().st_size != total or digest_file(assembled) != expected_sha256:
            raise ValueError(f"model digest mismatch: {target.name}")
        os.replace(assembled, target)
    except BaseException:
        assembled.unlink(missing_ok=True)
        shutil.rmtree(parts, ignore_errors=True)
        raise
    shutil.rmtree(parts)


def main() -> None:
    manifest = json.loads(Path(sys.argv[1]).read_text())
    output = Path(sys.argv[2])
    for item in manifest["files"]:
        directory, relative = item["path"].split("/", 1)
        if directory == "RapidOcr":
            url = manifest["rapidocr"]["base"] + manifest["rapidocr"]["paths"][relative]
        else:
            repository = directory.replace("--", "/", 1)
            revision = manifest["huggingface"][repository]
            url = f"https://huggingface.co/{repository}/resolve/{revision}/{relative}"
        target = output / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        download_file(url, target, item["sha256"])
        print(item["path"], item["sha256"], flush=True)


if __name__ == "__main__":
    main()
