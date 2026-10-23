import pytest

from doc_insight.llm import LLMError


class FakeClient:
    """Cliente falso: devuelve respuestas encoladas (dict) o lanza excepciones (LLMError)."""

    model = "fake-model"

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def complete_structured(self, system, user, schema):
        self.calls.append(user)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def make_valid(**overrides):
    base = {
        "is_relevant": True,
        "category": "bug",
        "severity": "high",
        "product_area": "login",
        "summary": "El usuario no puede iniciar sesión desde ayer.",
        "sentiment": "negative",
        "improvement_opportunity": None,
        "evidence": [],
        "confidence": 0.9,
        "missing_fields": [],
    }
    base.update(overrides)
    return base


@pytest.fixture
def fake():
    return FakeClient


@pytest.fixture
def valid():
    return make_valid


@pytest.fixture
def llm_error():
    return LLMError
