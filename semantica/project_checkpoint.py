"""Durable, input-fenced work already completed by one snapshot build."""
from __future__ import annotations

from contextvars import ContextVar
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256, file_digest
import json
import os
import shutil
from contextlib import contextmanager
from pathlib import Path
import tempfile
from typing import Any


class SnapshotCheckpointError(ValueError):
    """A checkpoint is corrupt or belongs to different immutable inputs."""


def _bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()


def _canonical_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    """Return only business inputs that determine reusable output bytes.

    Model/provider/build identity is provenance, not a validity fence.  Keeping
    this projection in one place also lets an older manifest be migrated once
    after its original fence and payload digests have been verified.
    """
    recipe = inputs.get("recipe", inputs.get("provenance", {}).get("recipe", {}))
    if not isinstance(recipe, dict):
        recipe = {}
    result = {key: value for key, value in inputs.items()
              if key in {"protocol", "projectId", "scopeId", "identityPropertySchema"}}
    requirements = inputs.get("requirements", recipe)
    if not isinstance(requirements, dict):
        raise ValueError("missing business requirements")
    result["requirements"] = {
        "extractionSpec": requirements.get("extractionSpec"),
        "classificationProfile": requirements.get("classificationProfile"),
        "forceOcrSourceIds": sorted(set(requirements.get("forceOcrSourceIds", []))),
        "formulaSemanticsSourceIds": sorted(set(requirements.get("formulaSemanticsSourceIds", []))),
    }
    def source_identity(source):
        return {key: value for key, value in source.items()
                if key in {"sourceId", "materialRevision", "mimeType", "actualDigest"}}
    if "sources" in inputs:
        result["sources"] = sorted([source_identity(source) for source in inputs["sources"]], key=lambda s: s["sourceId"])
    if "source" in inputs:
        result["source"] = source_identity(inputs["source"])
    return result


# Processing labels are provenance; actual business requirements own reuse.
PROCESSING_CONTRACTS = {
    "chunkExtraction": "structural-grounded-v2",
    "embedding": "gateway-batch-space-v1",
    "sourceDocument": "located-document-v2",
    "identityResolution": "native-conflict-veto-v1",
}


def _sync_directory(path: Path) -> None:
    if os.name != "nt":
        directory = os.open(path, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


def _atomic_json(path: Path, value: Any, *, exclusive: bool = False) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_bytes(value))
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive:
            os.link(temporary, path)
        else:
            os.replace(temporary, path)
        _sync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def _directory_lock(path):
    with path.open("a+b") as stream:
        if os.name == "nt":
            import msvcrt
            stream.write(b"0")
            stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


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
            "documentProcessing": request.document_processing.model_dump(mode="json", by_alias=True),
            "identityPropertySchema": request.identity_property_schema,
            "provenance": {"recipe": request.recipe.lineage_payload(),
              "release": request.release.model_dump(mode="json", by_alias=True),
              "relays": {name: {
                "modelId": relay.model_id,
                "bindingId": relay.binding_id,
                "capability": relay.capability,
                **({"contextWindowTokens": relay.context_window_tokens}
                   if relay.context_window_tokens is not None else {}),
                **({"maxOutputTokens": relay.max_output_tokens}
                   if relay.max_output_tokens is not None else {}),
            } for name, relay in request.relays.items()}}}
        self._initialize(request.output_dir, request.resume_checkpoint_dirs, inputs, request.checkpoint_dir)

    @classmethod
    def for_source(cls, source, *, output_dir, scope_id, recipe, created_at):
        """Use the same verified persistence for a single grounded-source build."""
        with Path(source.file_path).open("rb") as stream:
            digest = "sha256:" + file_digest(stream, "sha256").hexdigest()
        instance = cls.__new__(cls)
        instance._initialize(output_dir, [], {"protocol": "semantica.source-checkpoint.v1",
            "scopeId": scope_id, "createdAt": created_at,
            "processingContracts": deepcopy(PROCESSING_CONTRACTS),
            "provenance": {"recipe": recipe},
            "source": {**source.model_dump(mode="json", by_alias=True, exclude={"file_path"}),
                       "actualDigest": digest}})
        return instance

    def _initialize(self, output_dir, resume_dirs, inputs, checkpoint_dir=None):
        self.root = Path(checkpoint_dir).resolve() if checkpoint_dir else Path(output_dir).resolve() / "checkpoint"
        self.root.parent.mkdir(parents=True, exist_ok=True)
        with _directory_lock(self.root.parent / ".checkpoint.lock"):
            self._finish_migration()
            self._import(inputs, resume_dirs)

    def _finish_migration(self):
        journal = self.root.parent / ".checkpoint-migration.json"
        if not journal.exists():
            return
        try:
            plan = json.loads(journal.read_bytes())
        except (ValueError, OSError) as exc:
            raise SnapshotCheckpointError("checkpoint migration journal is unreadable; preserve and repair it") from exc
        if (not isinstance(plan, dict) or set(plan) != {"staging", "archive"} or not all(isinstance(v, str) for v in plan.values())
                or not plan["staging"].startswith(".checkpoint-next-")
                or Path(plan["staging"]).name != plan["staging"]
                or not plan["archive"].startswith("checkpoint-next-")
                or Path(plan["archive"]).name != plan["archive"]):
            raise SnapshotCheckpointError("checkpoint migration journal is invalid")
        staging = self.root.parent / plan["staging"]
        archive = self.root.parent / "evidence" / plan["archive"]
        if staging.exists():
            if self.root.exists():
                archive.parent.mkdir(exist_ok=True)
                if archive.exists():
                    raise SnapshotCheckpointError("checkpoint evidence destination already exists")
                self.root.rename(archive)
                _sync_directory(archive.parent)
                _sync_directory(self.root.parent)
            staging.rename(self.root)
            _sync_directory(self.root.parent)
        if not (self.root / "manifest.json").exists():
            raise SnapshotCheckpointError("checkpoint migration is incomplete")
        journal.unlink()
        _sync_directory(journal.parent)

    def _import(self, provenance, resume_dirs):
        inputs = _canonical_inputs(provenance)
        self.fence = _digest(_bytes(inputs))
        imports_dir = self.root.parent / "imports"
        pending = sorted(imports_dir.iterdir()) if imports_dir.exists() else []
        for root in pending:
            if (self.root.parent / "evidence" / root.name).exists():
                raise SnapshotCheckpointError(f"checkpoint evidence destination already exists: {root.name}")
        roots = ([self.root] if self.root.exists() else [])
        for carrier in pending:
            roots.extend(self._carrier_roots(carrier))
        roots.extend(Path(p).resolve() for p in resume_dirs)
        entries = {}
        self.created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        local_current = False
        changed_entries = False
        def remember_recipe(origin):
            if origin.get("protocol") != "semantica.project-checkpoint.v1":
                return
            recipe = origin.get("recipe", origin.get("provenance", {}).get("recipe"))
            if recipe is None:
                return
            if not isinstance(recipe, dict):
                raise SnapshotCheckpointError("checkpoint recipe provenance is invalid")
            key = _digest(_bytes(recipe))
            name = self._path("recipe-provenance", key).name
            entry = {"fence": self.fence, "key": key, "digest": key, "payload": recipe}
            if name in entries and entries[name] != entry:
                raise SnapshotCheckpointError("conflicting recipe provenance")
            entries[name] = entry

        for root in roots:
            try:
                if root.is_symlink() or not root.is_dir():
                    raise ValueError("checkpoint directory is not a regular directory")
                previous = json.loads((root / "manifest.json").read_bytes())
                prior_inputs = previous["inputs"]
                prior_fence = previous["fence"]
                if prior_fence != _digest(_bytes(prior_inputs)):
                    raise ValueError("manifest failed verification")
                prior_business = _canonical_inputs(prior_inputs)
                if {k: prior_business.get(k) for k in ("protocol", "projectId", "scopeId")} != {
                        k: inputs.get(k) for k in ("protocol", "projectId", "scopeId")}:
                    raise ValueError("inputs changed; explicit import belongs to different business content")
                datetime.fromisoformat(previous["createdAt"])
                if root == self.root or roots[0] == root:
                    self.created_at = previous["createdAt"]
                local_current = root == self.root and prior_inputs == inputs
                for file in root.iterdir():
                    if file.name == "manifest.json":
                        continue
                    # Atomic writers never publish these files as completed work.
                    if file.name.startswith(".pending-") and file.is_file() and not file.is_symlink():
                        file.unlink()
                        continue
                    if file.is_symlink() or not file.is_file() or file.suffix != ".json":
                        raise ValueError(f"unknown completed work carrier: {file.name}")
                    entry = json.loads(file.read_bytes())
                    # Native production keys carry their own dependencies. Unknown
                    # opaque units cannot cross a business-input change safely.
                    if prior_business != inputs and not file.name.startswith((
                            "document-", "source-windows-", "extraction-", "extraction-origin-",
                            "relay-", "product-result-", "grounded-explanation-", "remote-docling-", "rejected-", "recipe-provenance-")):
                        raise ValueError("inputs changed; unscoped result belongs to different business content")
                    name, normalized = self._import_entry(file.name, entry, prior_inputs, prior_fence,
                        previous.get("entryIdentity") == "business-content-v1")
                    if name != file.name and any(root.glob("rejected-" + file.stem + "-*.json")):
                        raise ValueError("rejected historical document requires explicit identity recovery")
                    changed_entries |= name != file.name or normalized != entry
                    entry = normalized
                    if name in entries and entries[name] != entry:
                        raise ValueError(f"conflicting completed work: {name}")
                    entries[name] = entry
                before = len(entries)
                remember_recipe(previous.get("provenance", prior_inputs))
                changed_entries |= len(entries) != before
                # Remember prior source coverage even after removal/readdition.
                # Missing plans must never silently repeat already-paid work.
                if any(root.glob("extraction-entities-*.json")) or any(root.glob("extraction-relations-*.json")):
                    for source in prior_business.get("sources", []):
                        key = {"sourceId": source["sourceId"], "materialRevision": source["materialRevision"],
                               "forceOcr": source["sourceId"] in prior_business["requirements"]["forceOcrSourceIds"]}
                        name = self._path("extraction-origin", key).name
                        marker = {"fence": self.fence, "key": key, "digest": _digest(_bytes(True)), "payload": True}
                        changed_entries |= name not in entries
                        entries[name] = marker
            except (ValueError, KeyError, TypeError, OSError) as exc:
                raise SnapshotCheckpointError(f"checkpoint import failed verification: {root}: {exc}") from exc
        before = len(entries)
        remember_recipe(provenance)
        changed_entries |= len(entries) != before
        if local_current and len(roots) == 1 and not changed_entries and previous.get("entryIdentity") == "business-content-v1":
            return
        # Commit a fully verified dataset in one recoverable directory transaction.
        staging = Path(tempfile.mkdtemp(prefix=".checkpoint-next-", dir=self.root.parent))
        try:
            for name, entry in entries.items():
                _atomic_json(staging / name, entry)
            _atomic_json(staging / "manifest.json", {"fence": self.fence, "inputs": inputs,
                "entryIdentity": "business-content-v1", "provenance": provenance, "createdAt": self.created_at})
            _atomic_json(self.root.parent / ".checkpoint-migration.json",
                {"staging": staging.name, "archive": staging.name.removeprefix(".")})
            self._finish_migration()
        except BaseException:
            # Once journaled, the transaction is resumed by the next initialization.
            if not (self.root.parent / ".checkpoint-migration.json").exists() and staging.exists():
                shutil.rmtree(staging)
            raise
        for root in pending:
            evidence = self.root.parent / "evidence" / root.name
            evidence.parent.mkdir(exist_ok=True)
            if evidence.exists():
                raise SnapshotCheckpointError(f"checkpoint evidence destination already exists: {root.name}")
            root.rename(evidence)
            _sync_directory(evidence.parent)
            _sync_directory(imports_dir)

    def _carrier_roots(self, carrier):
        """Finish relocated dataset transactions before verified one-time import."""
        if carrier.is_symlink() or not carrier.is_dir():
            raise SnapshotCheckpointError("checkpoint import carrier is not a regular directory")
        if (carrier / "manifest.json").is_file():
            return [carrier]
        owner = self.__class__.__new__(self.__class__)
        owner.root = carrier / "checkpoint"
        owner._finish_migration()
        roots = [owner.root] if owner.root.exists() else []
        imports = carrier / "imports"
        if imports.exists():
            for child in sorted(imports.iterdir()):
                roots.extend(self._carrier_roots(child))
        if not roots:
            raise SnapshotCheckpointError("checkpoint dataset has no recoverable completed work")
        return roots

    def _import_entry(self, name, entry, inputs, fence, business_keys):
        if name.startswith("rejected-"):
            if not isinstance(entry, dict) or set(entry) != {"kind", "keyDigest", "payloadDigest"}:
                raise ValueError("invalid rejection marker")
            kind, key_digest, payload_digest = entry["kind"], entry["keyDigest"], entry["payloadDigest"]
            if (not all(isinstance(v, str) for v in (kind, key_digest, payload_digest))
                    or any(not v.startswith("sha256:") or len(v) != 71
                           or any(c not in "0123456789abcdef" for c in v[7:]) for v in (key_digest, payload_digest))
                    or name != f"rejected-{kind}-{key_digest[7:]}-{payload_digest[7:]}.json"):
                raise ValueError("rejection marker locator mismatch")
            return name, entry
        if not isinstance(entry, dict) or entry.get("fence") != fence or entry.get("digest") != _digest(_bytes(entry["payload"])):
            raise ValueError("entry digest or fence mismatch")
        key = entry.get("key")
        if name.startswith("recipe-provenance-") and (not isinstance(entry["payload"], dict) or key != entry["digest"]):
            raise ValueError("recipe provenance identity mismatch")
        if key is not None and not name.endswith("-" + sha256(_bytes(key)).hexdigest() + ".json"):
            raise ValueError("entry key does not match its locator")
        if name.startswith("extraction-") and (key is None or not business_keys):
            raise ValueError("opaque historical extraction key requires verified import; refusing paid recomputation")
        if name.startswith("relay-"):
            receipt = entry["payload"].get("receipt", {}) if isinstance(entry["payload"], dict) else {}
            if receipt.get("operation") not in (None, "embedding") and (not isinstance(key, dict) or "context" not in key):
                raise ValueError("historical prompt-bound result requires verified business identity import; refusing paid recomputation")
        if name.startswith("document-"):
            if key is None:
                candidates = []
                recipe = inputs.get("recipe", inputs.get("provenance", {}).get("recipe", {}))
                for source in inputs.get("sources", [inputs.get("source", {})]):
                    candidate = {"sourceId": source.get("sourceId"), "contentHash": source.get("materialRevision"),
                                 "forceOcr": source.get("sourceId") in recipe.get("forceOcrSourceIds", []) if isinstance(recipe, dict) else False}
                    for candidate_key in (candidate, {**candidate, "documentProcessing": inputs.get("documentProcessing")}):
                        if name == "document-" + sha256(_bytes(candidate_key)).hexdigest() + ".json":
                            candidates.append(candidate_key)
                if len(candidates) != 1:
                    raise ValueError("historical document identity cannot be recovered")
                key = candidates[0]
            key = {k: v for k, v in key.items() if k != "documentProcessing"}
            name = "document-" + sha256(_bytes(key)).hexdigest() + ".json"
            entry = {**entry, "key": key}
        return name, {**entry, "fence": self.fence}

    def has_prior_extraction(self, source_key) -> bool:
        return self.read("extraction-origin", source_key) is True

    def _path(self, kind: str, key: Any) -> Path:
        return self.root / f"{kind}-{sha256(_bytes(key)).hexdigest()}.json"

    def _rejection_path(self, root: Path, kind: str, key: Any, payload_digest: str) -> Path:
        key_digest = sha256(_bytes(key)).hexdigest()
        return root / f"rejected-{kind}-{key_digest}-{payload_digest.removeprefix('sha256:')}.json"

    def _is_rejected(self, kind: str, key: Any, payload_digest: str) -> bool:
        expected = {"kind": kind, "keyDigest": _digest(_bytes(key)), "payloadDigest": payload_digest}
        marker = self._rejection_path(self.root, kind, key, payload_digest)
        if not marker.is_file():
            return False
        try:
            if json.loads(marker.read_bytes()) != expected:
                raise ValueError("rejection marker mismatch")
        except (ValueError, OSError) as exc:
            raise SnapshotCheckpointError(f"snapshot checkpoint rejection failed verification: {marker.name}") from exc
        return True

    def read(self, kind: str, key: Any) -> Any | None:
        path = self._path(kind, key)
        if not path.is_file():
            return None
        try:
            entry = json.loads(path.read_bytes())
            payload = entry["payload"]
            if entry["fence"] != self.fence or entry["digest"] != _digest(_bytes(payload)) \
                    or entry.get("key") != key:
                raise ValueError("digest or key mismatch")
            return None if self._is_rejected(kind, key, entry["digest"]) else payload
        except (ValueError, KeyError, TypeError, OSError) as exc:
            raise SnapshotCheckpointError(f"snapshot checkpoint entry failed verification: {path.name}") from exc

    def write(self, kind: str, key: Any, payload: Any) -> None:
        entry = {"fence": self.fence, "key": key, "digest": _digest(_bytes(payload)), "payload": payload}
        path = self._path(kind, key)
        with _directory_lock(self.root.parent / ".checkpoint.lock"):
            try:
                _atomic_json(path, entry, exclusive=True)
            except FileExistsError:
                try:
                    existing = json.loads(path.read_bytes())
                    if existing == entry:
                        return
                    if (existing["fence"] != self.fence or existing.get("key") != key
                            or existing["digest"] != _digest(_bytes(existing["payload"]))
                            or not self._is_rejected(kind, key, existing["digest"])):
                        raise ValueError("accepted result is immutable")
                    evidence = self.root.parent / "evidence"
                    evidence.mkdir(exist_ok=True)
                    saved = evidence / (path.stem + "-" + existing["digest"][7:] + ".json")
                    if saved.exists() and json.loads(saved.read_bytes()) != existing:
                        raise ValueError("rejected evidence conflict")
                    _atomic_json(saved, existing)
                    _atomic_json(path, entry)
                except (ValueError, KeyError, TypeError, OSError) as exc:
                    raise SnapshotCheckpointError(f"conflicting completed work: {kind}: {exc}") from exc

    def reject(self, kind: str, key: Any, payload: Any) -> None:
        payload_digest = _digest(_bytes(payload))
        _atomic_json(self._rejection_path(self.root, kind, key, payload_digest), {
            "kind": kind, "keyDigest": _digest(_bytes(key)), "payloadDigest": payload_digest,
        })


active_checkpoint: ContextVar[SnapshotCheckpoint | None] = ContextVar("snapshot_checkpoint", default=None)
