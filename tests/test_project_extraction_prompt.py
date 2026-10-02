import json
from types import SimpleNamespace

from semantica.project_snapshot_pipeline import _structured_extract
from semantica.project_snapshot_schema import ModelReceipt


def test_initial_prompt_matches_qualifier_validation(monkeypatch):
    def relay(_binding, payload, operation):
        prompt = payload["messages"][0]["content"]
        assert "Allow only polarity, condition, time, unit, value" in prompt
        assert "Do not extract page numbers, table-of-contents entries" in prompt
        receipt = ModelReceipt(
            id="receipt:1", operation=operation, provider="test", model="model-1",
            input_digest="sha256:" + "1" * 64, output_digest="sha256:" + "2" * 64,
        )
        return {"model": "model-1", "choices": [{"message": {"content": json.dumps({"entities": [], "relations": []})}}]}, receipt

    monkeypatch.setattr("semantica.project_snapshot_pipeline._relay_json", relay)
    _structured_extract("Social Factors | 219", SimpleNamespace(model_id="model-1"))
