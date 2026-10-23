import json

import httpx
import pytest

from doc_insight.extractor import Extractor
from doc_insight.llm import (
    GeminiClient,
    LLMError,
    MalformedResponse,
    OpenAICompatClient,
    create_client,
    parse_json_object,
)

SCHEMA = {"type": "object"}


def _http(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _gemini_body(text):
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def _openai_body(text):
    return {"choices": [{"message": {"content": text}}]}


# ---- parseo de JSON
def test_parse_plain_fenced_and_wrapped_json():
    assert parse_json_object('{"a": 1}') == {"a": 1}
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_object('Claro, acá está: {"a": 1} Espero que sirva') == {"a": 1}


@pytest.mark.parametrize("bad", ["", "hola", "[1, 2]", "{no es json}"])
def test_parse_rejects_invalid(bad):
    with pytest.raises(MalformedResponse):
        parse_json_object(bad)


# ---- Gemini
def test_gemini_success_and_request_shape():
    seen = {}

    def handler(req):
        seen["url"], seen["key"], seen["body"] = str(req.url), req.headers["x-goog-api-key"], json.loads(req.content)
        return httpx.Response(200, json=_gemini_body('{"ok": true}'))

    c = GeminiClient(model="gemini-x", api_key="K", http=_http(handler))
    assert c.complete_structured("sys", "user", SCHEMA) == {"ok": True}
    assert seen["url"].endswith("/models/gemini-x:generateContent") and seen["key"] == "K"
    assert seen["body"]["generationConfig"]["responseMimeType"] == "application/json"
    assert "JSON Schema" in seen["body"]["systemInstruction"]["parts"][0]["text"]


def test_gemini_blocked_response_is_llm_error():
    c = GeminiClient(api_key="K", http=_http(lambda r: httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}})))
    with pytest.raises(LLMError, match="sin contenido"):
        c.complete_structured("s", "u", SCHEMA)


def test_missing_api_key(monkeypatch):
    for v in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    with pytest.raises(LLMError, match="GEMINI_API_KEY"):
        GeminiClient()
    with pytest.raises(LLMError, match="GROQ_API_KEY"):
        OpenAICompatClient("groq")


# ---- reintentos ante rate limit
def test_retries_on_429_then_succeeds_with_backoff():
    calls, waits = [], []

    def handler(req):
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(429, text="RESOURCE_EXHAUSTED", headers={"retry-after": "2"})
        return httpx.Response(200, json=_gemini_body('{"ok": 1}'))

    c = GeminiClient(api_key="K", http=_http(handler), sleep=waits.append)
    assert c.complete_structured("s", "u", SCHEMA) == {"ok": 1}
    assert len(calls) == 3 and waits == [2.0, 2.0]


def test_gives_up_after_max_retries():
    waits = []
    c = GeminiClient(api_key="K", max_retries=2, http=_http(lambda r: httpx.Response(429, text="quota")), sleep=waits.append)
    with pytest.raises(LLMError, match="reintentos"):
        c.complete_structured("s", "u", SCHEMA)
    assert len(waits) == 2


def test_auth_error_is_not_retried_and_has_hint():
    calls = []
    c = GeminiClient(api_key="K", http=_http(lambda r: (calls.append(1), httpx.Response(403, text="forbidden"))[1]), sleep=lambda s: None)
    with pytest.raises(LLMError, match="región"):
        c.complete_structured("s", "u", SCHEMA)
    assert len(calls) == 1


# ---- compatibles con OpenAI (Groq / OpenRouter / Mistral)
def test_openai_compat_success_uses_bearer_and_base_url():
    seen = {}

    def handler(req):
        seen["url"], seen["auth"], seen["body"] = str(req.url), req.headers["authorization"], json.loads(req.content)
        return httpx.Response(200, json=_openai_body('```json\n{"ok": true}\n```'))

    c = OpenAICompatClient("groq", api_key="G", http=_http(handler))
    assert c.complete_structured("s", "u", SCHEMA) == {"ok": True}
    assert seen["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert seen["auth"] == "Bearer G" and seen["body"]["response_format"] == {"type": "json_object"}


def test_openai_compat_falls_back_without_response_format_on_400():
    bodies = []

    def handler(req):
        body = json.loads(req.content)
        bodies.append(body)
        if "response_format" in body:
            return httpx.Response(400, text="response_format not supported")
        return httpx.Response(200, json=_openai_body('{"ok": 2}'))

    c = OpenAICompatClient("openrouter", api_key="O", http=_http(handler))
    assert c.complete_structured("s", "u", SCHEMA) == {"ok": 2}
    assert "response_format" not in bodies[-1] and len(bodies) == 2


def test_custom_requires_base_url_and_model(monkeypatch):
    monkeypatch.setenv("DOC_INSIGHT_API_KEY", "x")
    with pytest.raises(LLMError, match="--base-url"):
        OpenAICompatClient("custom")


def test_create_client_unknown_provider():
    with pytest.raises(LLMError, match="desconocido"):
        create_client("nope")


# ---- integración con el extractor: respuesta no-JSON se reintenta con feedback
def test_non_json_reply_is_retried_by_extractor(valid):
    replies = iter(["Lo siento, no puedo", json.dumps(valid())])

    def handler(req):
        return httpx.Response(200, json=_gemini_body(next(replies)))

    client = GeminiClient(api_key="K", http=_http(handler))
    res = Extractor(client).extract("d1", "no puedo iniciar sesión, error 500")
    assert res.status == "ok" and res.attempts == 2


# ---- listado de modelos
def test_gemini_list_models_filters_by_generate_content():
    body = {"models": [
        {"name": "models/gemini-b", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/embed-x", "supportedGenerationMethods": ["embedContent"]},
        {"name": "models/gemini-a", "supportedGenerationMethods": ["generateContent", "countTokens"]},
    ]}
    c = GeminiClient(api_key="K", http=_http(lambda r: httpx.Response(200, json=body)))
    assert c.list_models() == ["gemini-a", "gemini-b"]


def test_openai_compat_list_models():
    c = OpenAICompatClient("groq", api_key="G", http=_http(lambda r: httpx.Response(200, json={"data": [{"id": "m2"}, {"id": "m1"}]})))
    assert c.list_models() == ["m1", "m2"]


def test_404_suggests_models_command():
    c = OpenAICompatClient("groq", api_key="G", http=_http(lambda r: httpx.Response(404, text="model_not_found")))
    with pytest.raises(LLMError, match="doc-insight models --provider groq"):
        c.complete_structured("s", "u", SCHEMA)
