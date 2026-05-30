"""Tests for the CLUE closed loop (stage ④): generate → measure → improve → regenerate.

Uses a small, fast cohort config; the generator and the detector's internal
subsampling are both seeded, so every assertion is deterministic.
"""

from __future__ import annotations

import pytest

from core.synthetic import SyntheticCohortGenerator
from evals.mislabel_detection import (
    DEFAULT_FLAG_THRESHOLD,
    detect_molecular_mismatches,
    score_molecular_detection,
)

pytest.importorskip("scipy")
pytest.importorskip("sklearn")

from clue.loop import CLUELoop, LoopResult, RoundResult, tune_decision_threshold  # noqa: E402

# Small but signal-bearing config; recall is 1.0 here so F1 is driven by precision.
SMALL = dict(n_samples=30, n_genes_proteomics=150, n_genes_rnaseq=200)


def _cohort(fraction=0.20, seed=7):
    return SyntheticCohortGenerator(mislabel_fraction=fraction, seed=seed, **SMALL).generate_cohort()


def test_tune_is_never_worse_than_default_threshold():
    cohort = _cohort()
    best_threshold, best_metrics = tune_decision_threshold(cohort)

    # The improve step must not degrade F1 relative to the detector's default τ.
    flagged_default, shared = detect_molecular_mismatches(cohort, flag_threshold=DEFAULT_FLAG_THRESHOLD)
    default_metrics = score_molecular_detection(flagged_default, cohort["ground_truth"]["mislabel_type"], shared)
    assert best_metrics["f1"] >= default_metrics["f1"]
    assert best_threshold in (0.3, 0.4, 0.5, 0.6, 0.7)


def test_loop_records_wellformed_history():
    result = CLUELoop(target_f1=0.8, start_fraction=0.10, max_rounds=3, seed=7, **SMALL).run()
    assert isinstance(result, LoopResult)
    assert result.rounds
    for r in result.rounds:
        assert isinstance(r, RoundResult)
        assert 0.0 <= r.f1 <= 1.0
        assert r.best_threshold in (0.3, 0.4, 0.5, 0.6, 0.7)
        assert r.n_molecular_swaps >= 0


def test_loop_escalates_corruption_and_records_frontier():
    result = CLUELoop(target_f1=0.8, start_fraction=0.10, fraction_step=0.10, max_rounds=3, seed=7, **SMALL).run()

    passed = [r for r in result.rounds if r.passed]
    assert len(passed) >= 2, "expected the tuned detector to clear several rounds"

    # Each cleared round probes a strictly harder corruption rate (curriculum).
    fractions = [r.mislabel_fraction for r in passed]
    assert fractions == sorted(fractions)
    assert len(set(fractions)) == len(fractions)

    # Frontier is the hardest rate the tuned detector still cleared.
    assert result.frontier_fraction == passed[-1].mislabel_fraction


def test_loop_stops_at_detector_ceiling():
    # An unreachable target: the detector cannot clear it even after tuning.
    result = CLUELoop(target_f1=1.01, start_fraction=0.10, max_rounds=3, seed=7, **SMALL).run()
    assert len(result.rounds) == 1
    assert result.rounds[0].passed is False
    assert result.frontier_fraction is None


def test_loop_is_deterministic():
    a = CLUELoop(target_f1=0.8, start_fraction=0.10, max_rounds=3, seed=7, **SMALL).run()
    b = CLUELoop(target_f1=0.8, start_fraction=0.10, max_rounds=3, seed=7, **SMALL).run()
    assert [r.f1 for r in a.rounds] == [r.f1 for r in b.rounds]
    assert a.frontier_fraction == b.frontier_fraction


def test_best_round_is_max_f1():
    result = CLUELoop(target_f1=0.8, start_fraction=0.10, max_rounds=3, seed=7, **SMALL).run()
    assert result.best_round is not None
    assert result.best_round.f1 == max(r.f1 for r in result.rounds)
