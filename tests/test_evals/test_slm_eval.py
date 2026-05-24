"""Tests for SLM evaluation suite."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from evals.slm_eval import SLMEvalSuite


@pytest.fixture
def mock_explainer():
    """Create a mock SLM explainer that returns known outputs."""
    explainer = AsyncMock()

    async def classify_gene(gene: str, target: str) -> dict:
        known_genes = {
            "PTPRC": {
                "gene": "PTPRC",
                "pathway": "immune_infiltration",
                "mechanism": "Leukocyte common antigen, marker for immune cell infiltration",
                "confidence": 0.95,
                "msi_relevant": True,
            },
            "GBP1": {
                "gene": "GBP1",
                "pathway": "interferon_response",
                "mechanism": "Guanylate-binding protein induced by IFN-gamma",
                "confidence": 0.92,
                "msi_relevant": True,
            },
            "TAP1": {
                "gene": "TAP1",
                "pathway": "antigen_presentation",
                "mechanism": "Transporter for MHC class I antigen processing",
                "confidence": 0.93,
                "msi_relevant": True,
            },
            "ACTB": {
                "gene": "ACTB",
                "pathway": "none_established",
                "mechanism": "Housekeeping gene, beta-actin",
                "confidence": 0.88,
                "msi_relevant": False,
            },
        }
        return known_genes.get(
            gene,
            {
                "gene": gene,
                "pathway": "unknown",
                "mechanism": "Not characterized",
                "confidence": 0.5,
                "msi_relevant": False,
            },
        )

    explainer.classify_gene = classify_gene
    return explainer


class TestSLMEvalSuite:
    @pytest.mark.asyncio
    async def test_run_returns_expected_keys(self, mock_explainer):
        suite = SLMEvalSuite(mock_explainer)
        result = await suite.run(["PTPRC", "GBP1", "TAP1"])

        assert "hallucination" in result
        assert "biological_validity" in result
        assert "pass" in result
        assert "latency_ms_per_gene" in result

    @pytest.mark.asyncio
    async def test_eval_results_have_expected_attrs(self, mock_explainer):
        suite = SLMEvalSuite(mock_explainer)
        result = await suite.run(["PTPRC", "GBP1"])

        for key in ("biological_validity", "hallucination"):
            eval_result = result[key]
            assert hasattr(eval_result, "name")
            assert hasattr(eval_result, "passed")
            assert hasattr(eval_result, "score")
            assert hasattr(eval_result, "threshold")
            assert hasattr(eval_result, "details")

    @pytest.mark.asyncio
    async def test_latency_is_non_negative(self, mock_explainer):
        suite = SLMEvalSuite(mock_explainer)
        result = await suite.run(["PTPRC"])

        assert result["latency_ms_per_gene"] >= 0

    @pytest.mark.asyncio
    async def test_pass_is_boolean(self, mock_explainer):
        suite = SLMEvalSuite(mock_explainer)
        result = await suite.run(["PTPRC", "GBP1", "TAP1"])

        assert isinstance(result["pass"], bool)

    @pytest.mark.asyncio
    async def test_hallucination_passes_without_citations(self, mock_explainer):
        suite = SLMEvalSuite(mock_explainer)
        result = await suite.run(["PTPRC"])

        # No pubmed_ids in mock outputs, so hallucination score should be 1.0
        assert result["hallucination"].score == 1.0
        assert result["hallucination"].passed is True

    @pytest.mark.asyncio
    async def test_empty_genes_list(self, mock_explainer):
        suite = SLMEvalSuite(mock_explainer)
        result = await suite.run([])

        assert result["latency_ms_per_gene"] == 0
