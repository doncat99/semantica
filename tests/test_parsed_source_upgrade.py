"""Historical carrier upgrades preserve paid content without loading a parser."""
import json
from hashlib import sha256
from pathlib import Path

import pytest

from semantica.semantic_worker import handle_request
from semantica.semantic_artifact_errors import SemanticArtifactError


def fixture(tmp_path):
    revision = "sha256:" + "b" * 64
    payload = {"protocol": "semantica.parsed-source.v1", "sourceId": "one",
        "materialRevision": "b3-" + "a" * 64, "mimeType": "text/plain", "name": "one.txt",
        "forceOcr": False, "origin": "native", "parser": "text", "parserVersion": "1",
        "documentProcessing": {"mode": "local"}, "document": {
            "content_hash": "b3-" + "a" * 64, "representation_revision": revision,
            "mime_type": "text/plain", "source": "one.txt", "text": "Paid historical content",
            "pages": [{"page": 1, "text": "Paid historical content"}], "metadata": {"saved": True}}}
    source = tmp_path / "old.json"
    source.write_text(json.dumps(payload))
    params = {"artifactPath": str(source), "artifactDigest": "sha256:" + sha256(source.read_bytes()).hexdigest(),
        "representationRevision": revision, "representationId": "representation:one:" + "b" * 64,
        "outputDir": str(tmp_path / "upgraded")}
    return payload, params


def test_upgrade_preserves_identity_and_does_not_invent_producer(tmp_path, monkeypatch):
    import semantica.semantic_source_artifact as owner
    monkeypatch.setattr(owner, "parse_source", lambda *a, **k: pytest.fail("migration must not parse"))
    payload, params = fixture(tmp_path)
    result = handle_request({"id": "upgrade", "method": "upgrade_parsed_source", "params": params})["result"]
    converted = json.loads(Path(result["artifactPath"]).read_bytes())
    assert converted == {**payload, "protocol": "semantica.parsed-source.v2"}
    assert result["representationRevision"] == params["representationRevision"]
    assert result["representationId"] == params["representationId"]
    assert "processingRevision" not in result
    assert handle_request({"id": "again", "method": "upgrade_parsed_source", "params": params})["result"] == result


@pytest.mark.parametrize("field,value", [("artifactDigest", "sha256:" + "0" * 64),
    ("representationRevision", "sha256:" + "0" * 64), ("representationId", "representation:other:" + "b" * 64)])
def test_upgrade_rejects_untrusted_identity(tmp_path, field, value):
    _, params = fixture(tmp_path)
    params[field] = value
    with pytest.raises(SemanticArtifactError, match="digest|identity|revision"):
        handle_request({"id": "upgrade", "method": "upgrade_parsed_source", "params": params})
    assert not (tmp_path / "upgraded").exists()
