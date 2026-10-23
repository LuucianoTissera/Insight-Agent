"""Agregación determinística de resultados y render del reporte (sin llamadas al modelo)."""
from __future__ import annotations

from collections import Counter

from .schema import ExtractionResult


def build_summary(results: list[ExtractionResult]) -> dict:
    valid = [r for r in results if r.data is not None]
    relevant = [r for r in valid if r.data.is_relevant]
    return {
        "total_documents": len(results),
        "by_status": dict(Counter(r.status for r in results)),
        "by_category": dict(Counter(r.data.category for r in relevant)),
        "by_severity": dict(Counter(r.data.severity or "sin_dato" for r in relevant)),
        "by_product_area": dict(Counter(r.data.product_area or "sin_dato" for r in relevant)),
        "avg_confidence": round(sum(r.data.confidence for r in valid) / len(valid), 3) if valid else None,
        "improvement_opportunities": [
            {"doc_id": r.doc_id, "opportunity": r.data.improvement_opportunity}
            for r in relevant
            if r.data.improvement_opportunity
        ],
        "needs_review": [r.doc_id for r in results if r.status == "needs_review"],
        "irrelevant": [r.doc_id for r in results if r.status == "irrelevant"],
        "failed": [{"doc_id": r.doc_id, "error": r.error} for r in results if r.status == "failed"],
        "truncated": [r.doc_id for r in results if r.truncated],
    }


def _table(counter: dict) -> str:
    if not counter:
        return "_Sin datos_\n"
    rows = "\n".join(f"| {k} | {v} |" for k, v in sorted(counter.items(), key=lambda kv: -kv[1]))
    return f"| Valor | Cantidad |\n|---|---|\n{rows}\n"


def render_markdown(summary: dict, results: list[ExtractionResult], model: str) -> str:
    out = ["# Reporte de análisis de documentos", ""]
    out.append(f"- Modelo: `{model}`")
    out.append(f"- Documentos procesados: **{summary['total_documents']}**")
    out.append(f"- Confianza promedio: **{summary['avg_confidence']}**")
    out.append("")
    out.append("## Estado del procesamiento")
    out.append(_table(summary["by_status"]))
    out.append("## Categorías (documentos relevantes)")
    out.append(_table(summary["by_category"]))
    out.append("## Severidad")
    out.append(_table(summary["by_severity"]))
    out.append("## Áreas de producto")
    out.append(_table(summary["by_product_area"]))

    out.append("## Oportunidades de mejora detectadas")
    if summary["improvement_opportunities"]:
        out += [f"- **{o['doc_id']}**: {o['opportunity']}" for o in summary["improvement_opportunities"]]
    else:
        out.append("_Ninguna_")
    out.append("")

    out.append("## Requieren revisión humana")
    by_id = {r.doc_id: r for r in results}
    if summary["needs_review"]:
        for d in summary["needs_review"]:
            r = by_id[d]
            out.append(f"- **{d}** (confianza {r.data.confidence}, campos faltantes: {r.data.missing_fields or 'ninguno'}): {r.data.summary}")
    else:
        out.append("_Ninguno_")
    out.append("")

    out.append("## Descartados por irrelevantes")
    out += [f"- {d}" for d in summary["irrelevant"]] or ["_Ninguno_"]
    out.append("")

    out.append("## Fallos")
    out += [f"- **{f['doc_id']}**: `{f['error']}`" for f in summary["failed"]] or ["_Ninguno_"]
    out.append("")
    if summary["truncated"]:
        out.append("## Advertencia\nDocumentos truncados por exceder el límite de entrada: " + ", ".join(summary["truncated"]))
        out.append("")
    return "\n".join(out)
