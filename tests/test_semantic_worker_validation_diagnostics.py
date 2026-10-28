import json

import pytest
from pydantic import ValidationError

from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest
from semantica.semantic_worker import _response


def test_validation_diagnostic_keeps_schema_path_without_input_values():
    with pytest.raises(ValidationError) as error:
        SemanticArtifactBuildRequest.model_validate({"privateDocumentText": "confidential"})

    response = _response("request-1", False, error=error.value)
    encoded = json.dumps(response)

    assert "confidential" not in encoded
    assert "privateDocumentText" not in encoded
    assert response["error"]["message"] == "Semantica request validation failed"
    diagnostic = response["error"]["diagnostic"]
    assert diagnostic["validationErrorCount"] > 0
    assert {"location": ["projectId"], "type": "missing"} in diagnostic["validationErrors"]


def test_wrapped_typed_output_failure_retains_safe_validation_diagnostic():
    from types import SimpleNamespace
    from semantica.semantic_artifact_builder import _ProjectModelProvider
    from semantica.utils.exceptions import ProcessingError

    provider = _ProjectModelProvider(SimpleNamespace(model_id="test"))
    provider.generate = lambda *args, **kwargs: '{}'
    with pytest.raises(ProcessingError) as failure:
        provider.generate_typed("private prompt", SemanticArtifactBuildRequest, max_retries=1)
    response = _response("typed", False, error=failure.value)
    assert response["error"]["code"] == "MODEL_OUTPUT_SCHEMA_INVALID"
    diagnostic = response["error"]["diagnostic"]
    assert diagnostic["validationErrorCount"] > 0
    assert {"location": ["projectId"], "type": "missing"} in diagnostic["validationErrors"]
    assert "private prompt" not in json.dumps(response)
