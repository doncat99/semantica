"""Durable, input-fenced work already completed by one snapshot build."""
from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime, timezone
from hashlib import sha256, file_digest
import json
import os
from pathlib import Path
import tempfile
from typing import Any


class SnapshotCheckpointError(ValueError):
    """A checkpoint is corrupt or belongs to different immutable inputs."""


def _bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()


def _atomic_json(path: Path, value: Any) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_bytes(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class SnapshotCheckpoint:
    def __init__(self, request: Any):
        self.root = Path(request.output_dir).resolve() / "checkpoint"
        self.root.mkdir(parents=True, exist_ok=True)
        sources = []
        for source in request.sources:
            with Path(source.file_path).open("rb") as stream:
                actual_digest = "sha256:" + file_digest(stream, "sha256").hexdigest()
            sources.append({**source.model_dump(mode="json", by_alias=True, exclude={"file_path"}), "actualDigest": actual_digest})
        baseline = request.base_snapshot.model_dump(mode="json", by_alias=True, exclude={"snapshot_path"}) if request.base_snapshot else None
        inputs = {"protocol": "semantica.project-checkpoint.v1", "projectId": request.project_id,
            "inputRevision": request.input_revision, "baseSnapshot": baseline,
            "sources": sorted(sources, key=lambda item: item["sourceId"]),
            "recipe": request.recipe.model_dump(mode="json", by_alias=True),
            "documentProcessing": request.document_processing.model_dump(mode="json", by_alias=True),
            "release": request.release.model_dump(mode="json", by_alias=True),
            "relays": {name: {"modelId": relay.model_id, "bindingId": relay.binding_id, "capability": relay.capability} for name, relay in request.relays.items()}}
        self.fence = _digest(_bytes(inputs))
        manifest = self.root / "manifest.json"
        if manifest.exists():
            try:
                previous = json.loads(manifest.read_bytes())
            except (ValueError, OSError) as exc:
                raise SnapshotCheckpointError("snapshot checkpoint manifest is unreadable") from exc
            if not isinstance(previous, dict) or previous.get("fence") != self.fence or previous.get("inputs") != inputs:
                raise SnapshotCheckpointError("snapshot checkpoint inputs changed; start a new build")
            self.created_at = previous.get("createdAt")
            try:
                datetime.fromisoformat(self.created_at)
            except (TypeError, ValueError) as exc:
                raise SnapshotCheckpointError("snapshot checkpoint build timestamp is invalid") from exc
        else:
            self.created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            _atomic_json(manifest, {"fence": self.fence, "inputs": inputs, "createdAt": self.created_at})

    def _path(self, kind: str, key: Any) -> Path:
        return self.root / f"{kind}-{sha256(_bytes(key)).hexdigest()}.json"

    def read(self, kind: str, key: Any) -> Any | None:
        path = self._path(kind, key)
        if not path.exists():
            return None
        try:
            entry = json.loads(path.read_bytes())
            payload = entry["payload"]
            if entry["fence"] != self.fence or entry["digest"] != _digest(_bytes(payload)):
                raise ValueError("digest mismatch")
            return payload
        except (ValueError, KeyError, TypeError, OSError) as exc:
            raise SnapshotCheckpointError(f"snapshot checkpoint entry failed verification: {path.name}") from exc

    def write(self, kind: str, key: Any, payload: Any) -> None:
        _atomic_json(self._path(kind, key), {"fence": self.fence, "digest": _digest(_bytes(payload)), "payload": payload})


active_checkpoint: ContextVar[SnapshotCheckpoint | None] = ContextVar("snapshot_checkpoint", default=None)
