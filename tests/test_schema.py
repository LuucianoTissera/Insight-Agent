import pytest
from pydantic import ValidationError

from doc_insight.schema import Extraction


def test_valid_extraction(valid):
    assert Extraction.model_validate(valid()).category == "bug"


def test_rejects_invalid_enum(valid):
    with pytest.raises(ValidationError):
        Extraction.model_validate(valid(category="urgente"))


def test_rejects_confidence_out_of_range(valid):
    with pytest.raises(ValidationError):
        Extraction.model_validate(valid(confidence=1.5))


def test_null_field_must_be_declared_missing(valid):
    with pytest.raises(ValidationError, match="missing_fields"):
        Extraction.model_validate(valid(severity=None))
    ok = Extraction.model_validate(valid(severity=None, missing_fields=["severity"]))
    assert ok.severity is None


def test_irrelevant_must_be_category_other(valid):
    with pytest.raises(ValidationError):
        Extraction.model_validate(valid(is_relevant=False, category="bug"))
    Extraction.model_validate(valid(is_relevant=False, category="other", severity=None, product_area=None))


def test_summary_too_short(valid):
    with pytest.raises(ValidationError):
        Extraction.model_validate(valid(summary="corto"))
