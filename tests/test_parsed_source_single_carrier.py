"""Knowledge publication references the admitted parser output without copying it."""
from hashlib import sha256
from pathlib import Path
import pytest
from pydantic import ValidationError

from semantica.semantic_worker import handle_request
from semantica.semantic_artifact_errors import SemanticArtifactError
from semantica.semantic_artifact_schema import ParsedSourceRef, SourceBuildInput
from semantica.semantic_source_artifact import _load_parsed_source
from tests.test_semantic_artifact import _request


def test_worker_references_parsed_source_without_another_document(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("Ada designed the Engine.", encoding="utf-8")
    request = _request(source, tmp_path / "output")
    parsed = request["params"]["parsedSources"][0]
    original = Path(parsed['artifactPath'])
    directory = tmp_path / 'content-addressed'
    directory.mkdir()
    path = directory / 'representation-digest.json'
    index = directory / 'independent-index-digest.sqlite'
    original.rename(path)
    Path(parsed['readerIndexPath']).rename(index)
    parsed.update(artifactPath=str(path), readerIndexPath=str(index))
    assert not path.with_suffix('.reader.sqlite').exists()
    identity = path.stat()
    digest = 'sha256:' + sha256(path.read_bytes()).hexdigest()
    result = handle_request(request)["result"]
    assert set(result) == {'publication', 'semanticStore', 'relayReceipts', 'relayReceiptManifest', 'nativeIndexes'}
    assert result['publication']['source_count'] == 1
    assert result['publication']['canonical_count'] > 0
    assert path.stat() == identity
    assert 'sha256:' + sha256(path.read_bytes()).hexdigest() == digest == parsed['artifactDigest']
    assert not list((tmp_path / "output").glob("*.json"))
    assert not list((tmp_path / "output").glob("*.sqlite"))


def test_parsed_source_revision_is_bound_to_the_requested_receipt(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("Ada designed the Engine.", encoding="utf-8")
    params = _request(source, tmp_path / "output")["params"]
    ref = dict(params["parsedSources"][0], representationRevision="sha256:" + "f" * 64)
    with pytest.raises(SemanticArtifactError, match="representation revision changed"):
        _load_parsed_source(SourceBuildInput.model_validate(params["sources"][0]),
                            ParsedSourceRef.model_validate(ref), False, {"mode": "local"})


def test_parsed_source_reference_requires_a_digest_revision():
    ref = {"artifactPath": "/tmp/canonical.json", "artifactDigest": "sha256:" + "a" * 64, "sourceId": "source-1"}
    with pytest.raises(ValidationError, match="representationRevision"):
        ParsedSourceRef.model_validate(ref)
    with pytest.raises(ValidationError, match="representationRevision"):
        ParsedSourceRef.model_validate(dict(ref, representationRevision="unbound"))
