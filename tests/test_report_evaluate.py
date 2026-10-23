import json

from doc_insight.evaluate import evaluate
from doc_insight.extractor import Extractor
from doc_insight.report import build_summary, render_markdown


def _results(fake, valid):
    docs = {
        "normal_a": valid(),
        "normal_b": valid(category="feature_request", severity="low", product_area="reportes",
                          improvement_opportunity="Exportar a Excel"),
        "ambiguous_c": valid(confidence=0.4),
        "irrelevant_d": valid(is_relevant=False, category="other", severity=None, product_area=None),
    }
    ex = Extractor(fake(*docs.values()))
    res = [ex.extract(k, f"texto {k}") for k in docs]
    res.append(Extractor(fake()).extract("incomplete_e", ""))
    return res


def test_summary_counts(fake, valid):
    s = build_summary(_results(fake, valid))
    assert s["total_documents"] == 5
    assert s["by_status"] == {"ok": 2, "needs_review": 1, "irrelevant": 1, "failed": 1}
    assert s["by_category"] == {"bug": 2, "feature_request": 1}
    assert s["needs_review"] == ["ambiguous_c"]
    assert s["failed"][0]["error"] == "empty_document"
    assert s["improvement_opportunities"][0]["opportunity"] == "Exportar a Excel"


def test_markdown_renders_sections(fake, valid):
    res = _results(fake, valid)
    md = render_markdown(build_summary(res), res, "fake-model")
    for section in ("## Estado del procesamiento", "## Oportunidades de mejora", "## Requieren revisión humana", "## Fallos"):
        assert section in md


def test_evaluate_accepts_lists_and_counts(fake, valid, tmp_path):
    res = _results(fake, valid)
    (tmp_path / "normal_a.json").write_text(json.dumps({"category": "bug", "status": ["ok"]}))
    (tmp_path / "normal_b.json").write_text(json.dumps({"category": "bug"}))  # error esperado
    (tmp_path / "ambiguous_c.json").write_text(json.dumps({"status": ["ok", "needs_review"]}))
    out = evaluate(res, tmp_path)
    assert out["by_case_type"]["normal"]["category"] == {"correct": 1, "total": 2, "accuracy": 0.5}
    assert out["by_case_type"]["ambiguous"]["status"]["accuracy"] == 1.0
