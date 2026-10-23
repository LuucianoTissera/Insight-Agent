from doc_insight.extractor import MAX_CHARS, Extractor

DOC = "Hola, no puedo iniciar sesión. Aparece Error 500 al validar credenciales."


def test_happy_path(fake, valid):
    client = fake(valid(evidence=["Error 500 al validar credenciales"]))
    res = Extractor(client).extract("d1", DOC)
    assert res.status == "ok" and res.attempts == 1 and res.data.category == "bug"


def test_retry_after_invalid_response_includes_feedback(fake, valid):
    client = fake(valid(category="urgente"), valid())
    res = Extractor(client).extract("d1", DOC)
    assert res.status == "ok" and res.attempts == 2
    assert "rechazado por el validador" in client.calls[1]
    assert "category" in client.calls[1]


def test_fails_after_max_attempts(fake, valid):
    client = fake(*[valid(confidence=9)] * 3)
    res = Extractor(client, max_attempts=3).extract("d1", DOC)
    assert res.status == "failed" and res.attempts == 3
    assert res.error.startswith("validation_failed")


def test_hallucinated_evidence_is_rejected_then_corrected(fake, valid):
    client = fake(valid(evidence=["frase inventada que no está"]), valid(evidence=["error 500"]))
    res = Extractor(client).extract("d1", DOC)
    assert res.attempts == 2 and res.status == "ok"
    assert "no aparece textualmente" in client.calls[1]


def test_llm_error_does_not_retry(fake, llm_error):
    client = fake(llm_error("RateLimitError"))
    res = Extractor(client).extract("d1", DOC)
    assert res.status == "failed" and res.attempts == 1 and "llm_error" in res.error


def test_low_confidence_needs_review(fake, valid):
    res = Extractor(fake(valid(confidence=0.4))).extract("d1", DOC)
    assert res.status == "needs_review"


def test_missing_fields_needs_review(fake, valid):
    res = Extractor(fake(valid(severity=None, missing_fields=["severity"]))).extract("d1", DOC)
    assert res.status == "needs_review"


def test_irrelevant_document(fake, valid):
    r = valid(is_relevant=False, category="other", severity=None, product_area=None, confidence=0.95)
    res = Extractor(fake(r)).extract("d1", "Receta de milanesas")
    assert res.status == "irrelevant"


def test_empty_document_skips_llm(fake):
    client = fake()
    res = Extractor(client).extract("d1", "   \n ")
    assert res.status == "failed" and res.error == "empty_document" and client.calls == []


def test_long_document_is_truncated_and_flagged(fake, valid):
    client = fake(valid())
    res = Extractor(client).extract("d1", "a" * (MAX_CHARS + 500))
    assert res.truncated is True
    assert len(client.calls[0]) < MAX_CHARS + 1000
