"""Typed generation sends a native strict schema even through custom gateways."""
import json

import httpx
import pytest
from openai import OpenAI
from pydantic import BaseModel, ConfigDict

from semantica.semantic_extract.providers import OpenAIProvider


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    results: list[str]


@pytest.mark.parametrize("failure", [None, "shape", "refusal", "length", "unsupported"])
def test_native_schema_without_semantic_fallback(failure):
    calls = []

    def respond(request):
        body = json.loads(request.content)
        calls.append(body)
        assert body["response_format"] == {
            "type": "json_schema", "json_schema": {
                "name": "Answer", "strict": True,
                "schema": {"title": "Answer", "type": "object", "additionalProperties": False,
                    "required": ["results"], "properties": {"results": {
                        "title": "Results", "type": "array", "items": {"type": "string"}}}}}}
        if failure == "unsupported":
            return httpx.Response(400, json={"error": {"message": "unsupported schema"}})
        message = {"role": "assistant", "content": json.dumps(
            {"wrong": []} if failure == "shape" else {"results": ["verified"]})}
        if failure == "refusal":
            message.update(content=None, refusal="refused")
        return httpx.Response(200, json={"id": "native-test", "object": "chat.completion",
            "created": 0, "model": "test", "choices": [{"index": 0, "message": message,
                "finish_reason": "length" if failure == "length" else "stop"}]})

    provider = OpenAIProvider(model="test", api_key="test", base_url="https://custom.test/v1")
    provider.client.close()
    with OpenAI(api_key="test", base_url="https://custom.test/v1", max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(respond))) as client:
        provider.client = client
        if failure:
            with pytest.raises(Exception):
                provider.generate_typed("Return the answer", Answer)
        else:
            assert provider.generate_typed("Return the answer", Answer) == Answer(results=["verified"])
    assert len(calls) == 1
