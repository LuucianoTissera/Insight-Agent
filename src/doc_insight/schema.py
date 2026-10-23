"""Contrato de salida del agente.

El esquema es la pieza central: define qué puede devolver el modelo y qué reglas
de consistencia debe cumplir. Si la respuesta no cumple, se rechaza y se reintenta.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

Category = Literal["bug", "feature_request", "question", "complaint", "other"]
Severity = Literal["low", "medium", "high", "critical"]
Sentiment = Literal["negative", "neutral", "positive"]
OptionalField = Literal["severity", "product_area"]


class Extraction(BaseModel):
    is_relevant: bool = Field(
        description="True si el documento es feedback/ticket de un usuario sobre un producto de software. False en cualquier otro caso."
    )
    category: Category = Field(description="Tipo de ticket. Usar 'other' si no es relevante o no encaja.")
    severity: Optional[Severity] = Field(
        default=None, description="Impacto para el usuario. null si el documento no da información para estimarlo."
    )
    product_area: Optional[str] = Field(
        default=None, description="Módulo o funcionalidad afectada, tal como la menciona el documento. null si no se menciona."
    )
    summary: str = Field(description="Resumen de 1-2 oraciones, en español, sin agregar datos que no estén en el documento.")
    sentiment: Sentiment
    improvement_opportunity: Optional[str] = Field(
        default=None, description="Oportunidad de mejora de producto que se desprende del documento, si existe."
    )
    evidence: list[str] = Field(
        default_factory=list,
        description="Fragmentos TEXTUALES copiados del documento que justifican la clasificación (máx. 3).",
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Confianza global de 0 a 1 en la extracción.")
    missing_fields: list[OptionalField] = Field(
        default_factory=list,
        description="Campos opcionales que quedaron en null porque el documento no tiene la información.",
    )

    @field_validator("summary")
    @classmethod
    def _summary_not_trivial(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 10:
            raise ValueError("summary demasiado corto (mínimo 10 caracteres)")
        if len(v) > 400:
            raise ValueError("summary demasiado largo (máximo 400 caracteres)")
        return v

    @field_validator("evidence")
    @classmethod
    def _evidence_max(cls, v: list[str]) -> list[str]:
        if len(v) > 3:
            raise ValueError("evidence admite como máximo 3 fragmentos")
        return [e.strip() for e in v if e.strip()]

    @model_validator(mode="after")
    def _consistency(self) -> "Extraction":
        if not self.is_relevant:
            if self.category != "other":
                raise ValueError("si is_relevant es false, category debe ser 'other'")
            return self
        # Documento relevante: todo campo opcional en null debe declararse en missing_fields.
        if self.severity is None and "severity" not in self.missing_fields:
            raise ValueError("severity es null pero no figura en missing_fields")
        if self.product_area is None and "product_area" not in self.missing_fields:
            raise ValueError("product_area es null pero no figura en missing_fields")
        if self.severity is not None and "severity" in self.missing_fields:
            raise ValueError("severity tiene valor pero figura en missing_fields")
        if self.product_area is not None and "product_area" in self.missing_fields:
            raise ValueError("product_area tiene valor pero figura en missing_fields")
        return self


Status = Literal["ok", "needs_review", "irrelevant", "failed"]


class ExtractionResult(BaseModel):
    """Resultado por documento: incluye el dato validado o la razón del fallo."""

    doc_id: str
    status: Status
    data: Optional[Extraction] = None
    attempts: int = 0
    error: Optional[str] = None
    truncated: bool = False
