"""Tests for the BenchmarkComparisonEval evaluator."""

from pathlib import Path

import pytest

from evals.benchmark_comparison import DEFAULT_BENCHMARK_JACCARD, BenchmarkComparisonEval

FIXTURES_PATH = str(Path(__file__).resolve().parent.parent.parent / "evals" / "fixtures" / "known_msi_signatures.json")


@pytest.fixture
def evaluator():
    return BenchmarkComparisonEval(fixtures_path=FIXTURES_PATH)


class TestBenchmarkComparisonEval:
    def test_exact_match(self, evaluator):
        """Agent panel identical to a benchmark -> Jaccard 1.0."""
        # Use the small top5 benchmark
        panel = ["S100A14", "ROCK2", "FHDC1", "PGM2", "GAR1"]
        result = evaluator.evaluate(panel, benchmark_name="precisionFDA_top5_proteomics")
        assert result.passed is True
        assert result.score == 1.0
        comp = result.details["comparisons"]["precisionFDA_top5_proteomics"]
        assert comp["jaccard"] == 1.0
        assert comp["overlap_count"] == 5

    def test_partial_overlap(self, evaluator):
        """Partial overlap with a benchmark."""
        panel = ["S100A14", "ROCK2", "FAKE_GENE"]
        result = evaluator.evaluate(panel, benchmark_name="precisionFDA_top5_proteomics")
        comp = result.details["comparisons"]["precisionFDA_top5_proteomics"]
        # overlap = {S100A14, ROCK2}, union = {S100A14, ROCK2, FHDC1, PGM2, GAR1, FAKE_GENE}
        assert comp["jaccard"] == pytest.approx(2 / 6)
        assert comp["overlap_count"] == 2
        assert "FAKE_GENE" in comp["unique_to_agent"]
        assert "FHDC1" in comp["unique_to_benchmark"]

    def test_no_overlap(self, evaluator):
        """No overlap at all -> Jaccard 0."""
        panel = ["FAKE1", "FAKE2", "FAKE3"]
        result = evaluator.evaluate(panel, benchmark_name="precisionFDA_top5_proteomics")
        assert result.passed is False
        assert result.score == 0.0
        comp = result.details["comparisons"]["precisionFDA_top5_proteomics"]
        assert comp["jaccard"] == 0.0

    def test_specific_benchmark_name(self, evaluator):
        """Passing a benchmark_name limits comparison to that single benchmark."""
        panel = ["TAP1", "LCP1"]
        result = evaluator.evaluate(panel, benchmark_name="precisionFDA_msi_proteomics")
        assert len(result.details["comparisons"]) == 1
        assert "precisionFDA_msi_proteomics" in result.details["comparisons"]

    def test_multiple_benchmarks_best_jaccard(self, evaluator):
        """Without benchmark_name, compares against all and returns best Jaccard."""
        # Use genes from the top5 benchmark for highest overlap there
        panel = ["S100A14", "ROCK2", "FHDC1", "PGM2", "GAR1"]
        result = evaluator.evaluate(panel)
        assert result.passed is True
        # Should have all 3 benchmarks compared
        assert len(result.details["comparisons"]) == 3
        # Best Jaccard should be 1.0 from the top5 match
        assert result.score == 1.0

    def test_empty_agent_panel(self, evaluator):
        """Empty panel -> Jaccard 0 for all benchmarks."""
        result = evaluator.evaluate([])
        assert result.passed is False
        assert result.score == 0.0
        for comp in result.details["comparisons"].values():
            assert comp["jaccard"] == 0.0
            assert comp["overlap_count"] == 0

    def test_trivial_overlap_no_longer_passes(self, evaluator):
        """A single-gene fluke (tiny Jaccard) must FAIL — the old 0.0 no-op gate is gone."""
        panel = ["S100A14"] + [f"FAKE{i}" for i in range(19)]  # 1 real of 20 vs top5
        result = evaluator.evaluate(panel, benchmark_name="precisionFDA_top5_proteomics")
        comp = result.details["comparisons"]["precisionFDA_top5_proteomics"]
        assert comp["overlap_count"] == 1
        assert result.score < DEFAULT_BENCHMARK_JACCARD  # ~1/24
        assert result.passed is False

    def test_default_threshold_is_meaningful(self, evaluator):
        """The reported threshold is the non-trivial floor, not 0.0."""
        result = evaluator.evaluate(["S100A14", "ROCK2"], benchmark_name="precisionFDA_top5_proteomics")
        assert result.threshold == DEFAULT_BENCHMARK_JACCARD
        assert result.threshold > 0.0

    def test_threshold_override_is_honoured(self, evaluator):
        """A caller can demand stronger recovery; partial overlap fails a high bar."""
        panel = ["S100A14", "ROCK2", "FAKE_GENE"]  # Jaccard 2/6 = 0.333
        assert evaluator.evaluate(panel, benchmark_name="precisionFDA_top5_proteomics", threshold=0.5).passed is False
        assert evaluator.evaluate(panel, benchmark_name="precisionFDA_top5_proteomics", threshold=0.3).passed is True

    def test_reference_flagged_not_independent(self, evaluator):
        """Honesty: the eval declares its reference is NOT an external oracle."""
        result = evaluator.evaluate(["TAP1"], benchmark_name="precisionFDA_msi_proteomics")
        assert result.details["independent_reference"] is False
        assert "reference_note" in result.details

    def test_details_structure(self, evaluator):
        """Verify the comparison details have all expected keys."""
        panel = ["TAP1", "GBP1", "PTPRC"]
        result = evaluator.evaluate(panel, benchmark_name="precisionFDA_msi_proteomics")
        comp = result.details["comparisons"]["precisionFDA_msi_proteomics"]
        expected_keys = {
            "jaccard",
            "overlap_count",
            "overlap_genes",
            "unique_to_agent",
            "unique_to_benchmark",
            "agent_panel_size",
            "benchmark_size",
        }
        assert set(comp.keys()) == expected_keys
        assert comp["agent_panel_size"] == 3
        assert comp["benchmark_size"] == 26
