"""Tests for the intent assurance loop (eval integration)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from evals import EvalResult
from intents.assurance import AssuranceLoop
from intents.models import Intent


@pytest.fixture
def assurance():
    return AssuranceLoop()


@pytest.fixture
def analysis_intent():
    return Intent(
        intent_id="analysis-test",
        intent_type="analysis",
        params={
            "target": "msi",
            "dataset": "train",
            "genes": ["TAP1", "LCP1", "PTPN6", "GBP1", "ICAM1"],
        },
    )


# ---------------------------------------------------------------------------
# Gene extraction
# ---------------------------------------------------------------------------


def test_extract_genes_from_params():
    intent = Intent(
        intent_id="test",
        intent_type="analysis",
        params={"genes": ["TAP1", "LCP1", "PTPN6"]},
    )
    genes = AssuranceLoop._extract_genes(intent)
    assert genes == ["TAP1", "LCP1", "PTPN6"]


def test_extract_genes_empty():
    intent = Intent(
        intent_id="test",
        intent_type="analysis",
        params={},
    )
    genes = AssuranceLoop._extract_genes(intent)
    assert genes == []


def test_extract_interpretations_from_params():
    interps = [{"gene": "TAP1", "pmid": "12345"}]
    intent = Intent(
        intent_id="test",
        intent_type="validation",
        params={"interpretations": interps},
    )
    result = AssuranceLoop._extract_interpretations(intent)
    assert result == interps


# ---------------------------------------------------------------------------
# Biological validity eval integration
# ---------------------------------------------------------------------------


def test_biological_validity_passes(assurance, analysis_intent):
    """Known MSI genes should pass biological validity at 0.60 threshold."""
    with patch("evals.biological_validity.BiologicalValidityEval") as MockEval:
        mock_eval = MagicMock()
        mock_eval.evaluate.return_value = EvalResult(
            name="biological_validity",
            passed=True,
            score=0.75,
            threshold=0.60,
            details={"pathways_covered": 3, "total_pathways": 4},
        )
        MockEval.return_value = mock_eval

        import asyncio

        result = asyncio.run(assurance._run_biological_validity(analysis_intent, 0.60))

        assert result.passed is True
        assert result.score == 0.75
        assert result.threshold == 0.60


def test_biological_validity_fails(assurance):
    """Empty gene list should fail biological validity."""
    intent = Intent(
        intent_id="test",
        intent_type="analysis",
        params={"genes": []},
    )

    with patch("evals.biological_validity.BiologicalValidityEval") as MockEval:
        mock_eval = MagicMock()
        mock_eval.evaluate.return_value = EvalResult(
            name="biological_validity",
            passed=False,
            score=0.0,
            threshold=0.60,
            details={"pathways_covered": 0, "total_pathways": 4},
        )
        MockEval.return_value = mock_eval

        import asyncio

        result = asyncio.run(assurance._run_biological_validity(intent, 0.60))

        assert result.passed is False
        assert result.score == 0.0


# ---------------------------------------------------------------------------
# Full evaluate method
# ---------------------------------------------------------------------------


def test_evaluate_all_pass(assurance, analysis_intent):
    """When all evals pass, all_passed returns True."""
    from intents.types import AnalysisIntentSpec

    spec = AnalysisIntentSpec()

    async def fake_bio(intent, threshold):
        return EvalResult(name="biological_validity", passed=True, score=0.75, threshold=0.60)

    async def fake_repro(intent, threshold):
        return EvalResult(name="reproducibility", passed=True, score=0.90, threshold=0.85)

    assurance._registry["biological_validity"] = fake_bio
    assurance._registry["reproducibility"] = fake_repro

    import asyncio

    results = asyncio.run(assurance.evaluate(analysis_intent, spec.eval_criteria))

    assert assurance.all_passed(results) is True
    assert results["biological_validity"].passed is True
    assert results["reproducibility"].passed is True


def test_evaluate_partial_fail(assurance, analysis_intent):
    """When one eval fails, all_passed returns False."""
    from intents.types import AnalysisIntentSpec

    spec = AnalysisIntentSpec()

    async def fake_bio(intent, threshold):
        return EvalResult(name="biological_validity", passed=True, score=0.75, threshold=0.60)

    async def fake_repro(intent, threshold):
        return EvalResult(name="reproducibility", passed=False, score=0.50, threshold=0.85)

    assurance._registry["biological_validity"] = fake_bio
    assurance._registry["reproducibility"] = fake_repro

    import asyncio

    results = asyncio.run(assurance.evaluate(analysis_intent, spec.eval_criteria))

    assert assurance.all_passed(results) is False
    assert results["reproducibility"].passed is False


# ---------------------------------------------------------------------------
# Training intent (no eval criteria)
# ---------------------------------------------------------------------------


def test_training_intent_no_evals(assurance):
    """Training intents have no eval criteria — evaluate returns empty dict."""
    from intents.types import TrainingIntentSpec

    spec = TrainingIntentSpec()
    intent = Intent(
        intent_id="training-test",
        intent_type="training",
        params={"model_type": "slm"},
    )

    import asyncio

    results = asyncio.run(assurance.evaluate(intent, spec.eval_criteria))

    assert results == {}
    assert assurance.all_passed(results) is True


# ---------------------------------------------------------------------------
# Eval error handling
# ---------------------------------------------------------------------------


def test_eval_error_returns_failed(assurance, analysis_intent):
    """If an eval runner raises, the result should be marked as failed."""

    async def _failing_eval(intent, threshold):
        raise RuntimeError("eval crashed")

    assurance._registry["biological_validity"] = _failing_eval

    import asyncio

    results = asyncio.run(assurance.evaluate(analysis_intent, (("biological_validity", 0.60),)))

    assert results["biological_validity"].passed is False
    assert "error" in results["biological_validity"].details
