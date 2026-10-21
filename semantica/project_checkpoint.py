"""Durable, input-fenced work already completed by one snapshot build."""
from __future__ import annotations

from contextvars import ContextVar
from copy import deepcopy
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


# These identify processing semantics, independently of package/build identity.
PROCESSING_CONTRACTS = {
    "chunkExtraction": "structural-grounded-v2",
    "embedding": "gateway-batch-space-v1",
    "sourceDocument": "located-document-v2",
    "identityResolution": "native-conflict-veto-v1",
}


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
        sources = []
        for source in request.sources:
            with Path(source.file_path).open("rb") as stream:
                actual_digest = "sha256:" + file_digest(stream, "sha256").hexdigest()
            sources.append({**source.model_dump(mode="json", by_alias=True, exclude={"file_path"}), "actualDigest": actual_digest})
        baseline = request.base_snapshot.model_dump(mode="json", by_alias=True, exclude={"snapshot_path"}) if request.base_snapshot else None
        inputs = {"protocol": "semantica.project-checkpoint.v1", "projectId": request.project_id,
            "inputRevision": request.input_revision, "baseSnapshot": baseline,
            "processingContracts": deepcopy(PROCESSING_CONTRACTS),
            "sources": sorted(sources, key=lambda item: item["sourceId"]),
            "recipe": request.recipe.lineage_payload(),
            "documentProcessing": request.document_processing.model_dump(mode="json", by_alias=True),
            "identityPropertySchema": request.identity_property_schema,
            "release": request.release.model_dump(mode="json", by_alias=True),
            "relays": {name: {
                "modelId": relay.model_id,
                "bindingId": relay.binding_id,
                "capability": relay.capability,
                **({"contextWindowTokens": relay.context_window_tokens}
                   if relay.context_window_tokens is not None else {}),
                **({"maxOutputTokens": relay.max_output_tokens}
                   if relay.max_output_tokens is not None else {}),
            } for name, relay in request.relays.items()}}
        self._initialize(request.output_dir, request.resume_checkpoint_dirs, inputs)

    @classmethod
    def for_source(cls, source, *, output_dir, scope_id, recipe, created_at):
        """Use the same verified persistence for a single grounded-source build."""
        with Path(source.file_path).open("rb") as stream:
            digest = "sha256:" + file_digest(stream, "sha256").hexdigest()
        instance = cls.__new__(cls)
        instance._initialize(output_dir, [], {"protocol": "semantica.source-checkpoint.v1",
            "scopeId": scope_id, "createdAt": created_at, "recipe": recipe,
            "processingContracts": deepcopy(PROCESSING_CONTRACTS),
            "source": {**source.model_dump(mode="json", by_alias=True, exclude={"file_path"}),
                       "actualDigest": digest}})
        return instance

    def _initialize(self, output_dir, resume_dirs, inputs):
        self.root = Path(output_dir).resolve() / "checkpoint"
        self.root.mkdir(parents=True, exist_ok=True)
        resume_roots = [Path(item).resolve() for item in resume_dirs]
        self.fence = _digest(_bytes(inputs))
        self.resume_roots = []
        for root in resume_roots:
            try:
                previous = json.loads((root / "manifest.json").read_bytes())
            except (ValueError, OSError) as exc:
                raise SnapshotCheckpointError(f"resume checkpoint manifest is unreadable: {root}") from exc
            previous_inputs = previous.get("inputs") if isinstance(previous, dict) else None
            previous_fence = previous.get("fence") if isinstance(previous, dict) else None
            if not isinstance(previous_fence, str) or previous_fence != _digest(_bytes(previous_inputs)):
                raise SnapshotCheckpointError(f"resume checkpoint manifest failed verification: {root}")
            if previous_inputs != inputs:
                raise SnapshotCheckpointError(f"resume checkpoint inputs changed; start a new build: {root}")
            self.resume_roots.append(root)
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

    def _rejection_path(self, root: Path, kind: str, key: Any, payload_digest: str) -> Path:
        key_digest = sha256(_bytes(key)).hexdigest()
        return root / f"rejected-{kind}-{key_digest}-{payload_digest.removeprefix('sha256:')}.json"

    def _is_rejected(self, kind: str, key: Any, payload_digest: str) -> bool:
        expected = {"kind": kind, "keyDigest": _digest(_bytes(key)), "payloadDigest": payload_digest}
        for root in [self.root, *self.resume_roots]:
            marker = self._rejection_path(root, kind, key, payload_digest)
            if not marker.is_file():
                continue
            try:
                if json.loads(marker.read_bytes()) != expected:
                    raise ValueError("rejection marker mismatch")
            except (ValueError, OSError) as exc:
                raise SnapshotCheckpointError(f"snapshot checkpoint rejection failed verification: {marker.name}") from exc
            return True
        return False

    def read(self, kind: str, key: Any) -> Any | None:
        local_path = self._path(kind, key)
        paths = [local_path]
        # Exact input fences and payload digests admit current-format entries only.
        paths.extend(root / local_path.name for root in self.resume_roots)
        for path in paths:
            if not path.is_file():
                continue
            try:
                entry = json.loads(path.read_bytes())
                payload = entry["payload"]
                local = path.parent == self.root
                if entry["fence"] != self.fence or entry["digest"] != _digest(_bytes(payload)):
                    raise ValueError("digest mismatch")
                if self._is_rejected(kind, key, entry["digest"]):
                    continue
                if not local:
                    self.write(kind, key, payload)
                return payload
            except (ValueError, KeyError, TypeError, OSError) as exc:
                raise SnapshotCheckpointError(f"snapshot checkpoint entry failed verification: {path.name}") from exc
        return None

    def write(self, kind: str, key: Any, payload: Any) -> None:
        _atomic_json(self._path(kind, key), {"fence": self.fence, "digest": _digest(_bytes(payload)), "payload": payload})

    def reject(self, kind: str, key: Any, payload: Any) -> None:
        payload_digest = _digest(_bytes(payload))
        _atomic_json(self._rejection_path(self.root, kind, key, payload_digest), {
            "kind": kind, "keyDigest": _digest(_bytes(key)), "payloadDigest": payload_digest,
        })


active_checkpoint: ContextVar[SnapshotCheckpoint | None] = ContextVar("snapshot_checkpoint", default=None)
