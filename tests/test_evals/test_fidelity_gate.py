"""Tests for the fidelity gate (CLUE construction-validity edge, stage ②).

Checks that a powered synthetic cohort's planted molecular swaps separate from
clean samples on the threshold-free cross-omics AUROC, and that the gate's
scope and edge cases match the design: clinical swaps excluded, clean cohorts
passing vacuously, and a signal-free cohort failing. All cohorts use a fixed
seed and the detector's subsampling is seeded, so results are deterministic.
"""

from __future__ import annotations

import pytest

from core.synthetic import SyntheticCohortGenerator
from evals import EvalResult
from evals.fidelity_gate import (
    DEFAULT_DUAL_METHODS,
    FidelityGateEval,
    fidelity_auroc,
    generate_signal_free_cohort,
)

pytest.importorskip("scipy")
pytest.importorskip("sklearn")


# A cohort large enough to carry detectable cross-omics signal. With
# mislabel_fraction=0.30 the generator injects swap pairs cycling through
# proteomics / rnaseq / clinical, so the cohort holds both molecular swaps (the
# positives the gate scores) and clinical swaps (excluded by construction).
def _powered_cohort():
    gen = SyntheticCohortGenerator(
        n_samples=40,
        n_genes_proteomics=400,
        n_genes_rnaseq=600,
        mislabel_fraction=0.30,
        seed=42,
    )
    return gen.generate_cohort()


def _clean_cohort():
    gen = SyntheticCohortGenerator(
        n_samples=40,
        n_genes_proteomics=400,
        n_genes_rnaseq=600,
        mislabel_fraction=0.0,
        seed=42,
    )
    return gen.generate_cohort()


def test_returns_wellformed_eval_result():
    result = FidelityGateEval().evaluate(_powered_cohort())
    assert isinstance(result, EvalResult)
    assert result.name == "fidelity_gate"
    for key in ("n_molecular_swaps", "n_clean", "n_clinical_excluded", "applicable"):
        assert key in result.details
    assert 0.0 <= result.score <= 1.0


def test_powered_cohort_is_detectable_by_construction():
    # The whole premise of the loop: injected molecular swaps must produce a
    # separable cross-omics signal. A powered cohort clears a strong AUROC bar.
    result = FidelityGateEval().evaluate(_powered_cohort(), threshold=0.80)
    assert result.details["applicable"] is True
    assert result.score >= 0.80  # AUROC
    assert result.passed is True
    # Swapped samples sit clearly above clean ones on the mismatch score.
    assert result.details["separation"] > 0.0


def test_clinical_swaps_excluded_from_scoring():
    cohort = _powered_cohort()
    mislabel_type = cohort["ground_truth"]["mislabel_type"]
    expected_molecular = {sid for sid, t in mislabel_type.items() if t in ("proteomics", "rnaseq")}
    expected_clinical = {sid for sid, t in mislabel_type.items() if t == "clinical"}

    result = FidelityGateEval().evaluate(cohort)
    assert result.details["n_molecular_swaps"] == len(expected_molecular)
    assert result.details["n_clinical_excluded"] == len(expected_clinical)
    # Clinical swaps are not folded into the clean negative baseline either.
    n_shared = result.details["n_molecular_swaps"] + result.details["n_clean"] + result.details["n_clinical_excluded"]
    assert n_shared <= cohort["clinical"].shape[0]


def test_clean_cohort_passes_vacuously():
    # mislabel_fraction=0 injects nothing, so AUROC is undefined and the gate
    # makes no claim it can fail — it passes with applicable=False rather than
    # being scored as a failure.
    result = FidelityGateEval().evaluate(_clean_cohort())
    assert result.details["applicable"] is False
    assert result.details["n_molecular_swaps"] == 0
    assert result.passed is True


def test_signal_free_cohort_fails():
    # Destroy the cross-omics relationship by shuffling RNA-Seq rows against the
    # proteomics/clinical sample order. The labels and swaps are untouched, so
    # the planted "corruption" is no longer detectable-by-construction: the gate
    # must catch that the cohort carries no usable signal (AUROC collapses).
    cohort = _powered_cohort()
    rnaseq = cohort["rnaseq"]
    shuffled = rnaseq.sample(frac=1.0, random_state=0).reset_index(drop=True)
    shuffled["sample_id"] = rnaseq["sample_id"].to_numpy()
    cohort["rnaseq"] = shuffled

    auroc, breakdown = fidelity_auroc(cohort)
    assert auroc is not None
    # With the cross-omics correspondence broken, swapped samples no longer
    # separate from clean ones — AUROC drops toward chance and the gate fails.
    assert auroc < 0.80
    assert FidelityGateEval().evaluate(cohort, threshold=0.80).passed is False


def test_score_matches_helper():
    cohort = _powered_cohort()
    auroc, _ = fidelity_auroc(cohort)
    result = FidelityGateEval().evaluate(cohort)
    assert result.score == pytest.approx(auroc)


# --- Dual-detector gate (gap #3: break the verbatim shared-scorer blind spot) ---


def test_dual_gate_passes_powered_under_both_detectors():
    # Both mechanically distinct detectors (rank correlation AND MSE residual)
    # must clear the bar on a powered cohort. The gated score is the MINIMUM,
    # and the two agree (neither straddles the threshold).
    result = FidelityGateEval().evaluate_dual(_powered_cohort(), threshold=0.80)
    assert result.details["applicable"] is True
    assert result.passed is True
    per = result.details["per_method"]
    assert set(per) == set(DEFAULT_DUAL_METHODS)
    assert all(per[m]["auroc"] >= 0.80 for m in DEFAULT_DUAL_METHODS)
    assert result.score == pytest.approx(min(per[m]["auroc"] for m in DEFAULT_DUAL_METHODS))
    assert result.details["detectors_disagree"] is False


def test_dual_gate_fails_on_signal_free_null_control():
    # Null control: re-pair RNA-Seq with the wrong samples so NO cross-omics
    # signal survives, but keep the swap labels. A gate with real discriminating
    # power must fail under BOTH detectors (AUROC collapses toward chance),
    # proving it does not pass by construction.
    null = generate_signal_free_cohort(_powered_cohort())
    result = FidelityGateEval().evaluate_dual(null, threshold=0.80)
    assert result.details["applicable"] is True
    assert result.passed is False
    per = result.details["per_method"]
    assert all(per[m]["auroc"] < 0.80 for m in DEFAULT_DUAL_METHODS)


def test_dual_gate_vacuous_on_clean_cohort():
    # No injected swaps -> AUROC undefined under both detectors -> vacuous pass.
    result = FidelityGateEval().evaluate_dual(_clean_cohort(), threshold=0.80)
    assert result.details["applicable"] is False
    assert result.passed is True


def test_dual_gate_is_stricter_than_single():
    # The AND gate is never a relaxation: if dual passes, the single rank gate
    # passes too (the converse need not hold).
    cohort = _powered_cohort()
    if FidelityGateEval().evaluate_dual(cohort, threshold=0.80).passed:
        assert FidelityGateEval().evaluate(cohort, threshold=0.80).passed is True
