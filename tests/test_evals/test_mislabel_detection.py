"""Tests for the mislabel-detection eval (CLUE measurement edge, stage ③).

Scores the cross-omics distance detector against the synthetic generator's
planted ground truth. All cohorts are generated with a fixed seed and the
detector's internal subsampling is seeded, so results are deterministic.
"""

from __future__ import annotations

import pytest

from core.synthetic import SyntheticCohortGenerator
from evals import EvalResult
from evals.mislabel_detection import MOLECULAR_SWAP_TYPES, MislabelDetectionEval

pytest.importorskip("scipy")
pytest.importorskip("sklearn")


# A cohort large enough to carry detectable cross-omics signal. With
# mislabel_fraction=0.30 the generator injects 6 swap pairs cycling through
# proteomics / rnaseq / clinical, so the cohort contains both molecular swaps
# (in scope) and clinical swaps (out of scope) — exercising both code paths.
def _powered_cohort():
    gen = SyntheticCohortGenerator(
        n_samples=40,
        n_genes_proteomics=400,
        n_genes_rnaseq=600,
        mislabel_fraction=0.30,
        seed=42,
    )
    return gen.generate_cohort()


def test_returns_wellformed_eval_result():
    result = MislabelDetectionEval().evaluate(_powered_cohort())
    assert isinstance(result, EvalResult)
    assert result.name == "mislabel_detection"
    for key in ("precision", "recall", "f1", "n_molecular_swaps", "n_flagged"):
        assert key in result.details
    assert 0.0 <= result.score <= 1.0


def test_detects_all_molecular_swaps():
    result = MislabelDetectionEval().evaluate(_powered_cohort(), threshold=0.70)
    # The distance detector recovers every molecular swap in a powered cohort.
    assert result.details["recall"] == 1.0
    assert result.score >= 0.70  # F1
    assert result.passed is True


def test_ground_truth_bookkeeping_matches_generator():
    cohort = _powered_cohort()
    result = MislabelDetectionEval().evaluate(cohort)

    mislabel_type = cohort["ground_truth"]["mislabel_type"]
    expected_molecular = {sid for sid, t in mislabel_type.items() if t in MOLECULAR_SWAP_TYPES}
    expected_clinical = {sid for sid, t in mislabel_type.items() if t == "clinical"}

    assert result.details["n_molecular_swaps"] == len(expected_molecular)
    assert set(result.details["clinical_swaps_out_of_scope"]) == expected_clinical


def test_clinical_swaps_excluded_from_scoring():
    cohort = _powered_cohort()
    result = MislabelDetectionEval().evaluate(cohort)
    d = result.details

    clinical = set(d["clinical_swaps_out_of_scope"])
    assert clinical, "expected the powered cohort to contain clinical swaps"

    # Clinical swaps must never count as true/false positives or negatives —
    # they are outside the distance path's remit.
    scored = set(d["true_positives"]) | set(d["false_positives"]) | set(d["false_negatives"])
    assert scored.isdisjoint(clinical)


def test_deterministic_across_runs():
    a = MislabelDetectionEval().evaluate(_powered_cohort())
    b = MislabelDetectionEval().evaluate(_powered_cohort())
    assert a.score == b.score
    assert a.details["true_positives"] == b.details["true_positives"]


def test_sweep_returns_one_result_per_rate():
    fractions = [0.10, 0.20, 0.30]
    results = MislabelDetectionEval().sweep(
        fractions, n_samples=40, n_genes_proteomics=400, n_genes_rnaseq=600, seed=42
    )
    assert len(results) == len(fractions)
    assert [r.details["mislabel_fraction"] for r in results] == fractions
    # More corruption → at least as many molecular swaps to find.
    swap_counts = [r.details["n_molecular_swaps"] for r in results]
    assert swap_counts == sorted(swap_counts)


def test_evaluate_generator_equivalent_to_evaluate():
    gen = SyntheticCohortGenerator(
        n_samples=40,
        n_genes_proteomics=400,
        n_genes_rnaseq=600,
        mislabel_fraction=0.30,
        seed=42,
    )
    via_generator = MislabelDetectionEval().evaluate_generator(gen)
    via_cohort = MislabelDetectionEval().evaluate(
        SyntheticCohortGenerator(
            n_samples=40,
            n_genes_proteomics=400,
            n_genes_rnaseq=600,
            mislabel_fraction=0.30,
            seed=42,
        ).generate_cohort()
    )
    assert via_generator.score == via_cohort.score
