"""Tests for DSPy metrics and gene extraction."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from dspy_modules.metrics import (
    biological_validity_metric,
    composite_metric,
    extract_genes_from_report,
    hallucination_metric,
)


class TestExtractGenesFromReport:
    def test_extracts_standard_genes(self):
        text = "The genes BRCA1, TP53, and MLH1 were selected."
        genes = extract_genes_from_report(text)
        assert "BRCA1" in genes
        assert "TP53" in genes
        assert "MLH1" in genes

    def test_filters_stopwords(self):
        text = "THE DNA AND RNA FOR THIS BRCA1 analysis"
        genes = extract_genes_from_report(text)
        assert "BRCA1" in genes
        assert "THE" not in genes
        assert "DNA" not in genes
        assert "AND" not in genes

    def test_empty_text(self):
        genes = extract_genes_from_report("")
        assert genes == []

    def test_no_genes(self):
        text = "there are no gene names in this lowercase text"
        genes = extract_genes_from_report(text)
        assert genes == []

    def test_mixed_content(self):
        text = "TAP1 showed significance (p=0.01), along with GBP1 and IRF1."
        genes = extract_genes_from_report(text)
        assert "TAP1" in genes
        assert "GBP1" in genes
        assert "IRF1" in genes


class TestBiologicalValidityMetric:
    def test_with_valid_genes(self):
        prediction = MagicMock()
        prediction.report = "BRCA1 and MLH1 are important biomarkers"
        example = MagicMock()

        with patch("evals.biological_validity.BiologicalValidityEval") as mock_eval:
            mock_result = MagicMock()
            mock_result.score = 0.75
            mock_eval.return_value.evaluate.return_value = mock_result

            score = biological_validity_metric(example, prediction)
            assert score == 0.75

    def test_with_no_genes(self):
        prediction = MagicMock()
        prediction.report = "no genes here"
        prediction.interpretations = ""
        example = MagicMock()

        score = biological_validity_metric(example, prediction)
        assert score == 0.0


class TestHallucinationMetric:
    def test_with_no_pubmed_ids(self):
        prediction = MagicMock()
        prediction.pubmed_ids = ""
        example = MagicMock()

        score = hallucination_metric(example, prediction)
        assert score == 1.0

    def test_with_pubmed_ids(self):
        prediction = MagicMock()
        prediction.pubmed_ids = "12345678, 87654321"
        example = MagicMock()

        with patch("evals.hallucination_detection.HallucinationDetectionEval") as mock_eval:
            mock_result = MagicMock()
            mock_result.score = 0.95
            mock_eval.return_value.evaluate.return_value = mock_result

            score = hallucination_metric(example, prediction)
            assert score == 0.95


class TestCompositeMetric:
    def test_hard_fail_on_low_hallucination(self):
        prediction = MagicMock()
        prediction.report = "BRCA1 MLH1"
        prediction.pubmed_ids = "12345"
        example = MagicMock()

        with (
            patch("evals.biological_validity.BiologicalValidityEval") as mock_bio,
            patch("evals.hallucination_detection.HallucinationDetectionEval") as mock_hall,
        ):
            mock_bio.return_value.evaluate.return_value = MagicMock(score=0.80)
            mock_hall.return_value.evaluate.return_value = MagicMock(score=0.50)

            score = composite_metric(example, prediction)
            assert score == 0.0

    def test_weighted_combination(self):
        prediction = MagicMock()
        prediction.report = "BRCA1 MLH1"
        prediction.pubmed_ids = "12345"
        example = MagicMock()

        with (
            patch("evals.biological_validity.BiologicalValidityEval") as mock_bio,
            patch("evals.hallucination_detection.HallucinationDetectionEval") as mock_hall,
        ):
            mock_bio.return_value.evaluate.return_value = MagicMock(score=0.80)
            mock_hall.return_value.evaluate.return_value = MagicMock(score=0.95)

            score = composite_metric(example, prediction)
            expected = 0.6 * 0.80 + 0.4 * 0.95
            assert abs(score - expected) < 1e-6
