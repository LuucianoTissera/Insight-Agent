"""Núcleo del agente: prompt -> respuesta estructurada -> validación -> reintento con feedback."""
from __future__ import annotations

import logging
import re

from pydantic import ValidationError

from .llm import LLMClient, LLMError, MalformedResponse
from .prompts import RETRY_FEEDBACK_TEMPLATE, SYSTEM_PROMPT, USER_TEMPLATE
from .schema import Extraction, ExtractionResult

log = logging.getLogger(__name__)

MAX_CHARS = 20_000          # límite de entrada; más allá se trunca y se marca el resultado
LOW_CONFIDENCE = 0.6        # por debajo, el resultado pasa a revisión humana


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def check_grounding(data: Extraction, document: str) -> list[str]:
    """Verifica que cada fragmento de `evidence` exista realmente en el documento."""
    doc = _norm(document)
    return [
        f"evidence no aparece textualmente en el documento: {e!r}"
        for e in data.evidence
        if _norm(e) not in doc
    ]


class Extractor:
    def __init__(self, client: LLMClient, max_attempts: int = 3):
        self.client = client
        self.max_attempts = max_attempts
        self.schema = Extraction.model_json_schema()

    def extract(self, doc_id: str, text: str) -> ExtractionResult:
        text = text.strip()
        if not text:
            # Evita gastar una llamada en un caso que no puede producir resultado útil.
            return ExtractionResult(doc_id=doc_id, status="failed", error="empty_document")

        truncated = len(text) > MAX_CHARS
        document = text[:MAX_CHARS]

        feedback = ""
        last_error = ""
        for attempt in range(1, self.max_attempts + 1):
            user = USER_TEMPLATE.format(document=document, feedback=feedback)
            try:
                raw = self.client.complete_structured(SYSTEM_PROMPT, user, self.schema)
            except LLMError as e:
                # Errores de infraestructura: no tiene sentido reintentar con otro prompt.
                log.error("[%s] error de LLM: %s", doc_id, e)
                return ExtractionResult(
                    doc_id=doc_id, status="failed", attempts=attempt, error=f"llm_error: {e}", truncated=truncated
                )
            except MalformedResponse as e:
                errors = [str(e)]  # respuesta no-JSON: se trata como error de validación
            else:
                validated = self._validate(raw, document)
                if isinstance(validated, Extraction):
                    return ExtractionResult(
                        doc_id=doc_id,
                        status=self._status(validated),
                        data=validated,
                        attempts=attempt,
                        truncated=truncated,
                    )
                errors = validated
            last_error = "; ".join(errors)
            log.warning("[%s] intento %d inválido: %s", doc_id, attempt, last_error)
            feedback = RETRY_FEEDBACK_TEMPLATE.format(errors="\n".join(f"- {e}" for e in errors))

        return ExtractionResult(
            doc_id=doc_id,
            status="failed",
            attempts=self.max_attempts,
            error=f"validation_failed: {last_error}",
            truncated=truncated,
        )

    @staticmethod
    def _validate(raw: dict, document: str) -> Extraction | list[str]:
        try:
            data = Extraction.model_validate(raw)
        except ValidationError as e:
            return [f"{'.'.join(map(str, err['loc'])) or 'root'}: {err['msg']}" for err in e.errors()]
        grounding = check_grounding(data, document)
        return grounding if grounding else data

    @staticmethod
    def _status(data: Extraction) -> str:
        if not data.is_relevant:
            return "irrelevant"
        if data.confidence < LOW_CONFIDENCE or data.missing_fields:
            return "needs_review"
        return "ok"
