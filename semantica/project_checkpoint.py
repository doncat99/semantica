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


def _resume_compatible(previous: Any, current: dict[str, Any]) -> bool:
    if not isinstance(previous, dict):
        return False
    candidate = deepcopy(previous)
    if candidate == current:
        return True
    previous_relays = candidate.get("relays")
    current_relays = current.get("relays")
    previous_model = previous_relays.get("model") if isinstance(previous_relays, dict) else None
    current_model = current_relays.get("model") if isinstance(current_relays, dict) else None
    if not isinstance(previous_model, dict) or not isinstance(current_model, dict):
        return False
    previous_limit = previous_model.get("maxOutputTokens")
    current_limit = current_model.get("maxOutputTokens")
    if not isinstance(previous_limit, int) or not isinstance(current_limit, int) or previous_limit <= current_limit:
        return False
    previous_model["maxOutputTokens"] = current_limit
    candidate["inputRevision"] = current["inputRevision"]
    return candidate == current


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
        resume_roots = [Path(item).resolve() for item in request.resume_checkpoint_dirs]
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
            "relays": {name: {
                "modelId": relay.model_id,
                "bindingId": relay.binding_id,
                "capability": relay.capability,
                **({"contextWindowTokens": relay.context_window_tokens}
                   if relay.context_window_tokens is not None else {}),
                **({"maxOutputTokens": relay.max_output_tokens}
                   if relay.max_output_tokens is not None else {}),
            } for name, relay in request.relays.items()}}
        self.fence = _digest(_bytes(inputs))
        self.resume_root_fences = {}
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
            if _resume_compatible(previous_inputs, inputs):
                self.resume_roots.append(root)
                self.resume_root_fences[root] = previous_fence
        self.resume_model_token_limits = {
            Path(path).resolve(): limit for path, limit in request.resume_checkpoint_model_token_limits.items()
            if Path(path).resolve() in self.resume_root_fences
        }
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
        # Every completed production artifact is resumable.  Restricting
        # resume roots to relay responses forced a restarted build to issue
        # no new model calls yet still rebuild all extracted chunks and
        # embeddings in memory.  The input fence and payload digest protect
        # each copied artifact, so document, chunk and embedding entries can
        # safely be reused across process boundaries.
        paths.extend(root / local_path.name for root in self.resume_roots)
        for path in paths:
            if not path.is_file():
                continue
            try:
                entry = json.loads(path.read_bytes())
                payload = entry["payload"]
                local = path.parent == self.root
                expected_fence = self.fence if local else self.resume_root_fences[path.parent]
                if entry["fence"] != expected_fence or entry["digest"] != _digest(_bytes(payload)):
                    raise ValueError("digest mismatch")
                if self._is_rejected(kind, key, entry["digest"]):
                    continue
                if not local:
                    self.write(kind, key, payload)
                return payload
            except (ValueError, KeyError, TypeError, OSError) as exc:
                raise SnapshotCheckpointError(f"snapshot checkpoint entry failed verification: {path.name}") from exc
        return None

    def read_with_lower_model_limit(self, key: dict[str, Any]) -> Any | None:
        payload = key.get("payload")
        if not isinstance(payload, dict) or not isinstance(payload.get("max_tokens"), int):
            return None
        current_limit = payload["max_tokens"]
        for root in self.resume_roots:
            prior_limit = self.resume_model_token_limits.get(root)
            if prior_limit is None or prior_limit <= current_limit:
                continue
            old_key = {**key, "payload": {**payload, "max_tokens": prior_limit}}
            candidate = self._path("relay", old_key).name
            path = root / candidate
            if not path.is_file():
                continue
            try:
                entry = json.loads(path.read_bytes())
                stored = entry["payload"]
                if entry["fence"] != self.resume_root_fences[root] or entry["digest"] != _digest(_bytes(stored)):
                    raise ValueError("digest mismatch")
                response = stored["response"]
                choices = response["choices"]
                usage = response["usage"]
                if (len(choices) != 1 or choices[0].get("finish_reason") != "stop"
                        or not isinstance(usage.get("completion_tokens"), int)
                        or usage["completion_tokens"] > current_limit):
                    continue
                if self._is_rejected("relay", old_key, entry["digest"]) or self._is_rejected("relay", key, entry["digest"]):
                    continue
                self.write("relay", key, stored)
                return stored
            except (ValueError, KeyError, TypeError, OSError) as exc:
                raise SnapshotCheckpointError(f"snapshot checkpoint entry failed verification: {candidate}") from exc
        return None

    def write(self, kind: str, key: Any, payload: Any) -> None:
        _atomic_json(self._path(kind, key), {"fence": self.fence, "digest": _digest(_bytes(payload)), "payload": payload})

    def reject(self, kind: str, key: Any, payload: Any) -> None:
        payload_digest = _digest(_bytes(payload))
        _atomic_json(self._rejection_path(self.root, kind, key, payload_digest), {
            "kind": kind, "keyDigest": _digest(_bytes(key)), "payloadDigest": payload_digest,
        })


active_checkpoint: ContextVar[SnapshotCheckpoint | None] = ContextVar("snapshot_checkpoint", default=None)
