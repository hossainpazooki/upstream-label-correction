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

from clue.loop import (  # noqa: E402
    CLUELoop,
    LoopResult,
    RoundResult,
    build_classifier_xy,
    select_threshold_holdout,
    tune_decision_threshold,
)

# Small but signal-bearing config; recall is 1.0 here so F1 is driven by precision.
SMALL = dict(n_samples=30, n_genes_proteomics=150, n_genes_rnaseq=200)


def _cohort(fraction=0.20, seed=7):
    return SyntheticCohortGenerator(mislabel_fraction=fraction, seed=seed, **SMALL).generate_cohort()


def test_select_threshold_holdout_selects_on_tune_scores_on_measure():
    """Held-out helper picks tau on the tune cohort and scores the disjoint measure cohort."""
    measure = _cohort(seed=7)
    tune = _cohort(seed=7 + 1000)

    threshold, measure_metrics, tune_metrics = select_threshold_holdout(tune, measure)

    # The selected threshold is the argmax on the TUNE cohort, not the measure cohort.
    tune_threshold, expected_tune_metrics = tune_decision_threshold(tune)
    assert threshold == tune_threshold
    assert tune_metrics["f1"] == expected_tune_metrics["f1"]

    # measure_metrics is that fixed threshold applied to the held-out measure cohort.
    flagged, shared = detect_molecular_mismatches(measure, flag_threshold=threshold)
    expected = score_molecular_detection(flagged, measure["ground_truth"]["mislabel_type"], shared)
    assert measure_metrics["f1"] == expected["f1"]

    # Deterministic per seed.
    again = select_threshold_holdout(_cohort(seed=7 + 1000), _cohort(seed=7))
    assert again[0] == threshold and again[1]["f1"] == measure_metrics["f1"]


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


# ---------------------------------------------------------------------------
# Retrain lever (improve_mode = "retrain"/"both"). These are kept separate from
# the threshold-path tests above, which sit at the float/BLAS-sensitive
# target_f1=0.8 boundary; the retrain assertions below test ranges, None-ness,
# the no-leakage seed boundary, and same-machine determinism — never a
# hardcoded F1 — so they don't inherit that platform fragility.
# ---------------------------------------------------------------------------

RETRAIN_KW = dict(target_f1=0.8, start_fraction=0.10, fraction_step=0.10, max_rounds=2, seed=7, **SMALL)


def test_threshold_mode_is_byte_identical_to_default():
    # The explicit default must reproduce the implicit default exactly: same
    # f1, threshold, frontier, and no retrain fields populated.
    implicit = CLUELoop(**RETRAIN_KW).run()
    explicit = CLUELoop(improve_mode="threshold", **RETRAIN_KW).run()

    assert [r.f1 for r in implicit.rounds] == [r.f1 for r in explicit.rounds]
    assert [r.best_threshold for r in implicit.rounds] == [r.best_threshold for r in explicit.rounds]
    assert implicit.frontier_fraction == explicit.frontier_fraction
    for r in explicit.rounds:
        assert r.improve_mode == "threshold"
        assert r.retrain_f1 is None
        assert r.train_seed is None


def test_retrain_populates_held_out_fields():
    result = CLUELoop(improve_mode="retrain", **RETRAIN_KW).run()
    assert result.improve_mode == "retrain"
    for r in result.rounds:
        assert r.improve_mode == "retrain"
        assert r.retrain_f1 is not None and 0.0 <= r.retrain_f1 <= 1.0
        assert r.retrain_precision is not None and 0.0 <= r.retrain_precision <= 1.0
        assert r.retrain_recall is not None and 0.0 <= r.retrain_recall <= 1.0
        assert r.train_seed is not None


def test_retrain_train_seed_is_disjoint_from_measure_seeds():
    # The no-leakage guarantee: the train cohort's seed never coincides with any
    # measure cohort's seed (self.seed + iteration for iteration in range).
    seed, offset, max_rounds = 7, 1000, 2
    result = CLUELoop(
        improve_mode="retrain",
        target_f1=0.8,
        start_fraction=0.10,
        fraction_step=0.10,
        max_rounds=max_rounds,
        seed=seed,
        train_seed_offset=offset,
        **SMALL,
    ).run()
    measure_seeds = {seed + i for i in range(max_rounds)}
    for r in result.rounds:
        assert r.train_seed == seed + offset + r.iteration
        assert r.train_seed not in measure_seeds


def test_retrain_is_deterministic_per_seed():
    a = CLUELoop(improve_mode="retrain", **RETRAIN_KW).run()
    b = CLUELoop(improve_mode="retrain", **RETRAIN_KW).run()
    assert [r.retrain_f1 for r in a.rounds] == [r.retrain_f1 for r in b.rounds]
    assert [r.train_seed for r in a.rounds] == [r.train_seed for r in b.rounds]


def test_both_mode_reports_both_and_preserves_threshold_path():
    both = CLUELoop(improve_mode="both", **RETRAIN_KW).run()
    threshold_only = CLUELoop(improve_mode="threshold", **RETRAIN_KW).run()

    # The distance-threshold path (which drives loop control) is unchanged by
    # turning the retrain lever on alongside it.
    assert [r.f1 for r in both.rounds] == [r.f1 for r in threshold_only.rounds]
    assert [r.best_threshold for r in both.rounds] == [r.best_threshold for r in threshold_only.rounds]
    assert both.frontier_fraction == threshold_only.frontier_fraction
    for r in both.rounds:
        assert r.retrain_f1 is not None


def test_build_classifier_xy_shapes_and_labels():
    cohort = _cohort(fraction=0.20, seed=7)
    X, y_gender, y_msi, mismatch = build_classifier_xy(cohort)
    n = len(cohort["clinical"])
    assert X.shape[0] == n
    assert y_gender.shape == (n,) and set(y_gender.tolist()) <= {0, 1}
    assert y_msi.shape == (n,) and set(y_msi.tolist()) <= {0, 1}
    assert mismatch.shape == (n,)
    assert int(mismatch.sum()) == len(set(cohort["ground_truth"]["mislabeled_samples"]))


def test_invalid_improve_mode_is_rejected():
    with pytest.raises(ValueError, match="improve_mode"):
        CLUELoop(improve_mode="bogus", **SMALL)
