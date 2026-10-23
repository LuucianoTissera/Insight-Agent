"""Evaluación contra casos etiquetados: permite medir y comparar modelos/prompts."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .schema import ExtractionResult

FIELDS = ("is_relevant", "category", "severity", "status")


def _actual(result: ExtractionResult) -> dict:
    d = result.data
    return {
        "is_relevant": d.is_relevant if d else None,
        "category": d.category if d else None,
        "severity": d.severity if d else None,
        "status": result.status,
    }


def _matches(expected, actual) -> bool:
    options = expected if isinstance(expected, list) else [expected]
    return actual in options


def case_type(doc_id: str) -> str:
    """El tipo de caso se deduce del prefijo del archivo: normal_, ambiguous_, incomplete_, ..."""
    return doc_id.split("_", 1)[0]


def evaluate(results: list[ExtractionResult], expected_dir: Path) -> dict:
    per_doc, tally = [], defaultdict(lambda: defaultdict(lambda: [0, 0]))  # tipo -> campo -> [aciertos, total]
    for r in results:
        path = expected_dir / f"{r.doc_id}.json"
        if not path.exists():
            continue
        expected = json.loads(path.read_text(encoding="utf-8"))
        actual = _actual(r)
        row = {"doc_id": r.doc_id, "checks": {}}
        for f in FIELDS:
            if f not in expected:
                continue
            ok = _matches(expected[f], actual[f])
            row["checks"][f] = {"expected": expected[f], "actual": actual[f], "ok": ok}
            tally[case_type(r.doc_id)][f][0] += int(ok)
            tally[case_type(r.doc_id)][f][1] += 1
        per_doc.append(row)

    by_type = {
        t: {f: {"correct": c, "total": n, "accuracy": round(c / n, 3)} for f, (c, n) in fields.items()}
        for t, fields in tally.items()
    }
    all_c = sum(c for t in tally.values() for c, _ in t.values())
    all_n = sum(n for t in tally.values() for _, n in t.values())
    return {
        "overall_accuracy": round(all_c / all_n, 3) if all_n else None,
        "by_case_type": by_type,
        "documents": per_doc,
    }
