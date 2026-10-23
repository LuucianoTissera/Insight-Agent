"""Capa de acceso a modelos de IA.

Proveedores soportados:
  - gemini      Google AI Studio (API REST nativa)
  - groq        API compatible con OpenAI
  - openrouter  API compatible con OpenAI (modelos ':free')
  - mistral     API compatible con OpenAI
  - custom      Cualquier endpoint compatible con OpenAI (--base-url)
  - anthropic   Opcional (requiere `pip install -e ".[anthropic]"`)

Se define un Protocol mínimo para poder cambiar de proveedor/modelo (útil para comparar
alternativas) y para testear sin red usando un cliente falso.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Callable, Protocol

import httpx

TOOL_NAME = "submit_extraction"


class LLMError(Exception):
    """Fallo de infraestructura: red, auth, cuota agotada, respuesta bloqueada o vacía."""


class MalformedResponse(Exception):
    """El modelo respondió, pero no con un objeto JSON interpretable. Se trata como error de validación (reintentable)."""


class LLMClient(Protocol):
    model: str

    def complete_structured(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]: ...


# --------------------------------------------------------------------------- utilidades


def json_instructions(schema: dict[str, Any]) -> str:
    return (
        "\n\nFormato de salida: respondé ÚNICAMENTE con un objeto JSON válido (sin texto adicional "
        "ni bloques de código) que cumpla este JSON Schema:\n" + json.dumps(schema, ensure_ascii=False)
    )


def parse_json_object(text: str) -> dict[str, Any]:
    """Extrae un objeto JSON de la respuesta, tolerando bloques ```json y texto alrededor."""
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip(), flags=re.I)
    try:
        obj = json.loads(t)
    except json.JSONDecodeError:
        start, end = t.find("{"), t.rfind("}")
        if start == -1 or end <= start:
            raise MalformedResponse("La respuesta no es un objeto JSON válido.") from None
        try:
            obj = json.loads(t[start : end + 1])
        except json.JSONDecodeError:
            raise MalformedResponse("La respuesta contiene JSON mal formado.") from None
    if not isinstance(obj, dict):
        raise MalformedResponse("La respuesta JSON debe ser un objeto, no una lista ni un valor suelto.")
    return obj


class _HTTPClient:
    """Base HTTP con reintentos y backoff exponencial ante 429 / 5xx / errores de red."""

    provider = "http"
    RETRY_STATUS = {429, 500, 502, 503, 504}

    def __init__(
        self,
        model: str,
        api_key: str,
        max_retries: int = 6,
        timeout: float = 60.0,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.model = model
        self.api_key = api_key
        self.max_retries = max_retries
        self.http = http or httpx.Client(timeout=timeout)
        self.sleep = sleep

    def _post(self, url: str, headers: dict, payload: dict) -> httpx.Response:
        last = ""
        for attempt in range(self.max_retries + 1):
            wait = float(min(30, 2 ** (attempt + 1)))  # 2, 4, 8, 16, 30, 30 s
            try:
                r = self.http.post(url, headers=headers, json=payload)
            except httpx.TransportError as e:
                last = f"{type(e).__name__}: {e}"
            else:
                if r.status_code not in self.RETRY_STATUS:
                    return r  # éxito o error no reintentable: lo interpreta el llamador
                last = f"HTTP {r.status_code}: {r.text[:200]}"
                try:
                    wait = min(60.0, float(r.headers.get("retry-after", wait)))
                except ValueError:
                    pass
            if attempt < self.max_retries:
                self.sleep(wait)
        raise LLMError(f"[{self.provider}] se agotaron los reintentos. Último error: {last}")

    def _check(self, r: httpx.Response) -> None:
        if r.status_code < 400:
            return
        hint = ""
        if r.status_code in (401, 403):
            hint = " (revisá la API key y si el servicio está disponible en tu región)"
        elif r.status_code == 404:
            hint = f" (el modelo '{self.model}' no existe o no tenés acceso: listá los disponibles con `doc-insight models --provider {self.provider}` y usá --model)"
        raise LLMError(f"[{self.provider}] HTTP {r.status_code}{hint}: {r.text[:300]}")


# --------------------------------------------------------------------------- Gemini


class GeminiClient(_HTTPClient):
    provider = "gemini"
    BASE = "https://generativelanguage.googleapis.com/v1beta/models"
    DEFAULT_MODEL = "gemini-3.8-flash"  # los nombres cambian: usá `doc-insight models` para ver los disponibles

    def __init__(self, model: str | None = None, api_key: str | None = None, **kw):
        key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise LLMError("Falta GEMINI_API_KEY. Generala en https://aistudio.google.com/apikey y ponela en .env")
        super().__init__(model or self.DEFAULT_MODEL, key, **kw)

    def complete_structured(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "systemInstruction": {"parts": [{"text": system + json_instructions(schema)}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 4096, "responseMimeType": "application/json"},
        }
        r = self._post(
            f"{self.BASE}/{self.model}:generateContent",
            {"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
            payload,
        )
        self._check(r)
        data = r.json()
        try:
            text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError, TypeError):
            raise LLMError(f"[gemini] respuesta sin contenido (¿bloqueada por filtros?): {str(data)[:200]}") from None
        return parse_json_object(text)


    def list_models(self) -> list[str]:
        """Modelos que la key puede usar para generar texto (ListModels)."""
        try:
            r = self.http.get(self.BASE, headers={"x-goog-api-key": self.api_key}, params={"pageSize": 200})
        except httpx.TransportError as e:
            raise LLMError(f"[gemini] error de red: {e}") from e
        self._check(r)
        return sorted(
            m["name"].removeprefix("models/")
            for m in r.json().get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", [])
        )


# --------------------------------------------------------------------------- compatibles con OpenAI

# provider -> (base_url, variable de entorno con la key, modelo por defecto)
OPENAI_COMPAT = {
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY", "llama-3.3-70b-versatile"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", "meta-llama/llama-3.3-70b-instruct:free"),
    "mistral": ("https://api.mistral.ai/v1", "MISTRAL_API_KEY", "mistral-small-latest"),
    "custom": (None, "DOC_INSIGHT_API_KEY", None),
}


class OpenAICompatClient(_HTTPClient):
    def __init__(
        self,
        provider: str,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        **kw,
    ):
        default_url, env_var, default_model = OPENAI_COMPAT[provider]
        key = api_key or os.getenv(env_var)
        if not key:
            raise LLMError(f"Falta {env_var}. Ponela en tu archivo .env (ver .env.example).")
        self.provider = provider
        self.base_url = (base_url or default_url or "").rstrip("/")
        model = model or default_model
        if not self.base_url or not model:
            raise LLMError("El proveedor 'custom' requiere --base-url y --model.")
        super().__init__(model, key, **kw)

    def complete_structured(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system + json_instructions(schema)},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
            "max_tokens": 2048,
            "response_format": {"type": "json_object"},
        }
        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        r = self._post(url, headers, payload)
        if r.status_code == 400:
            # Algunos modelos (p. ej. varios ':free' de OpenRouter) no soportan response_format: reintento sin él.
            payload.pop("response_format")
            r = self._post(url, headers, payload)
        self._check(r)
        data = r.json()
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise LLMError(f"[{self.provider}] respuesta inesperada: {str(data)[:200]}") from None
        return parse_json_object(text)


    def list_models(self) -> list[str]:
        try:
            r = self.http.get(f"{self.base_url}/models", headers={"Authorization": f"Bearer {self.api_key}"})
        except httpx.TransportError as e:
            raise LLMError(f"[{self.provider}] error de red: {e}") from e
        self._check(r)
        return sorted(m["id"] for m in r.json().get("data", []))


# --------------------------------------------------------------------------- Anthropic (opcional)


class AnthropicClient:
    provider = "anthropic"

    def __init__(self, model: str | None = None, api_key: str | None = None, max_tokens: int = 1024):
        try:
            import anthropic
        except ImportError as e:
            raise LLMError('Para usar Anthropic instalá la dependencia: pip install -e ".[anthropic]"') from e
        key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise LLMError("Falta ANTHROPIC_API_KEY (la API de Anthropic es de pago).")
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=key, max_retries=3, timeout=60.0)
        self.model = model or "claude-sonnet-4-6"
        self.max_tokens = max_tokens

    def complete_structured(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=0,
                system=system,
                tools=[{"name": TOOL_NAME, "description": "Registra la información extraída.", "input_schema": schema}],
                tool_choice={"type": "tool", "name": TOOL_NAME},  # fuerza salida estructurada
                messages=[{"role": "user", "content": user}],
            )
        except self._anthropic.APIError as e:
            raise LLMError(f"[anthropic] {type(e).__name__}: {e}") from e
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use" and block.name == TOOL_NAME:
                return dict(block.input)
        raise LLMError("[anthropic] la respuesta no contiene la llamada a la herramienta esperada.")


# --------------------------------------------------------------------------- fábrica

PROVIDERS = ["gemini", "groq", "openrouter", "mistral", "custom", "anthropic"]


def create_client(
    provider: str, model: str | None = None, base_url: str | None = None, max_retries: int | None = None
) -> LLMClient:
    provider = provider.lower()
    kw = {} if max_retries is None else {"max_retries": max_retries}
    if provider == "gemini":
        return GeminiClient(model=model, **kw)
    if provider == "anthropic":
        return AnthropicClient(model=model)
    if provider in OPENAI_COMPAT:
        return OpenAICompatClient(provider, model=model, base_url=base_url, **kw)
    raise LLMError(f"Proveedor desconocido: {provider!r}. Opciones: {', '.join(PROVIDERS)}")
