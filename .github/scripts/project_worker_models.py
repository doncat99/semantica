"""Fetch only the model bytes admitted by the native-worker release lock."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import urllib.request


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
    if not target.exists():
        with urllib.request.urlopen(url, timeout=300) as response, target.open("wb") as stream:
            shutil.copyfileobj(response, stream)
    with target.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != item["sha256"]:
        raise ValueError(f"model digest mismatch: {item['path']}")
    print(item["path"], digest, flush=True)
