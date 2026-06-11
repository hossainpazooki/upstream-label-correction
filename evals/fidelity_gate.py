"""Fidelity gate — stage ② of the CLUE loop: *detectable-by-construction*.

Before measuring how well a detector finds the planted swaps (stage ③,
``evals.mislabel_detection``), confirm the synthetic cohort actually **carries
the signal a real detector relies on**: the molecular-swapped samples must
separate from the clean samples on the model-free cross-omics mismatch score,
*independent of any decision threshold*. If they do not, a high detector F1
would be scoring noise — the cohort is unfit to transfer conclusions to real
data, and the loop should not trust it.

This is the construction-validity counterpart to stage ③, and deliberately
distinct from it:

* Stage ③ (*measure*) applies a decision threshold and reports precision /
  recall / F1 for one detector configuration — "how good is the detector?"
* Stage ② (*this gate*) asks whether a separable signal exists **at all**,
  threshold-free — "is there anything there to detect?"

Metric: **AUROC** of the continuous mismatch frequency at ranking
molecular-swap samples above clean ones. AUROC is rank-based and threshold-free
by design, so it measures the cohort's intrinsic separability rather than any
one operating point. ``1.0`` = the planted corruption perfectly separates from
clean; ``0.5`` = the swap left no cross-omics trace (a broken or signal-free
cohort) and the gate should fail.

Scope mirrors :mod:`evals.mislabel_detection`: clinical-only swaps exchange
labels but leave **both** molecular matrices intact, so they carry no
cross-omics signal *by construction* and are neither positives nor negatives —
including them would wrongly drag the AUROC down. They are excluded and counted
separately in ``details``.

The detector invocation itself (:func:`evals.mislabel_detection.mismatch_frequencies`)
is reused verbatim so stage ② and stage ③ score the *same* signal.
"""

from __future__ import annotations

from statistics import median

import numpy as np
from sklearn.metrics import roc_auc_score

from evals import EvalResult
from evals.mislabel_detection import MOLECULAR_SWAP_TYPES, mismatch_frequencies

#: Default pass threshold on AUROC. 0.80 demands strong, threshold-free rank
#: separation between swapped and clean samples — well above the 0.5 of a
#: signal-free cohort.
DEFAULT_AUROC_THRESHOLD = 0.80


def _median_or_none(values: list[float]) -> float | None:
    return median(values) if values else None


def fidelity_auroc(
    cohort: dict,
    distance_method: str = "expression_rank",
) -> tuple[float | None, dict]:
    """Score how separably the planted molecular corruption shows up.

    Runs the cross-omics distance detector to get each sample's continuous
    mismatch frequency, then computes the AUROC of that score at ranking
    molecular-swap samples (positives) above clean samples (negatives).

    Returns
    -------
    (auroc, breakdown)
        ``auroc`` is ``None`` when the cohort has no molecular swaps *or* no
        clean samples — AUROC is undefined with only one class, and there is
        nothing for the gate to verify. ``breakdown`` always carries the
        supporting counts and per-group median scores.
    """
    frequencies, shared_samples = mismatch_frequencies(cohort, distance_method)
    mislabel_type: dict[str, str] = cohort["ground_truth"].get("mislabel_type", {})

    shared = set(shared_samples)
    positives = {sid for sid, t in mislabel_type.items() if t in MOLECULAR_SWAP_TYPES and sid in shared}
    # Clinical swaps carry no molecular signal by construction, so they are
    # neither positives nor part of the clean negative baseline.
    clinical = {sid for sid, t in mislabel_type.items() if t == "clinical" and sid in shared}
    negatives = shared - positives - clinical

    breakdown = {
        "n_molecular_swaps": len(positives),
        "n_clean": len(negatives),
        "n_clinical_excluded": len(clinical),
        "median_freq_swapped": _median_or_none([frequencies.get(s, 0.0) for s in positives]),
        "median_freq_clean": _median_or_none([frequencies.get(s, 0.0) for s in negatives]),
        "distance_method": distance_method,
    }

    if not positives or not negatives:
        return None, breakdown

    scored = sorted(positives | negatives)
    y_true = [1 if sid in positives else 0 for sid in scored]
    scores = [frequencies.get(sid, 0.0) for sid in scored]
    auroc = float(roc_auc_score(y_true, scores))

    breakdown["separation"] = breakdown["median_freq_swapped"] - breakdown["median_freq_clean"]
    return auroc, breakdown


#: Two mechanically distinct distance primitives for the dual fidelity gate
#: (gap #3): rank correlation (1-|spearman|) and the MSE-residual linear model.
#: Their failure modes differ, so a cohort cleared by BOTH does not rest on a
#: single detector's blind spot. Both still read the SAME synthetic matrices, so
#: this is a *decorrelated second scorer*, NOT an external oracle — gap #1
#: (no held-out oracle, blocked on real data) remains open.
DEFAULT_DUAL_METHODS = ("expression_rank", "linear_model")


def fidelity_auroc_dual(
    cohort: dict,
    methods: tuple[str, ...] = DEFAULT_DUAL_METHODS,
) -> dict[str, tuple[float | None, dict]]:
    """Score separability under each distance primitive independently.

    Returns ``{method: (auroc, breakdown)}`` by calling :func:`fidelity_auroc`
    once per method (the single-method function is reused verbatim, so each
    score is deterministic and unchanged).
    """
    return {m: fidelity_auroc(cohort, distance_method=m) for m in methods}


def generate_signal_free_cohort(cohort: dict, seed: int = 42) -> dict:
    """Null control: destroy cross-omics concordance while keeping the swap labels.

    Deterministically re-pairs each sample's RNA-Seq profile with a different
    sample's, so no sample's two modalities agree. The planted ``ground_truth``
    swap labels are unchanged, but the molecular signal that distinguishes
    swapped from clean is gone — so a gate with real discriminating power must
    DROP both detectors' AUROC below threshold rather than pass by construction.
    Used by tests to prove the dual gate can fail.
    """
    rng = np.random.RandomState(seed)
    rna = cohort["rnaseq"].copy()
    ids = rna["sample_id"].to_numpy().copy()
    # Roll by a fixed nonzero offset so EVERY sample is re-paired (no fixed points),
    # then add an extra deterministic shuffle of the offset for good measure.
    perm = (np.arange(len(ids)) + 1 + rng.randint(0, len(ids))) % len(ids)
    feats = rna.drop(columns=["sample_id"]).reset_index(drop=True)
    feats.insert(0, "sample_id", ids[perm])
    out = dict(cohort)
    out["rnaseq"] = feats
    return out


class FidelityGateEval:
    """Gate a synthetic cohort on detectable-by-construction corruption (stage ②)."""

    def evaluate(
        self,
        cohort: dict,
        threshold: float = DEFAULT_AUROC_THRESHOLD,
        distance_method: str = "expression_rank",
    ) -> EvalResult:
        """Score one cohort's fidelity.

        PASS if the molecular-swap-vs-clean AUROC >= ``threshold``.

        A cohort with no molecular swaps (or no clean baseline) makes no claim
        the gate can falsify: AUROC is undefined, so it passes *vacuously* with
        ``details["applicable"] = False`` rather than being scored as a failure.
        This is the right behaviour for a clean (``mislabel_fraction=0``) cohort
        — there is no injected corruption whose detectability needs verifying.
        """
        auroc, breakdown = fidelity_auroc(cohort, distance_method)

        if auroc is None:
            return EvalResult(
                name="fidelity_gate",
                passed=True,
                score=1.0,
                threshold=threshold,
                details={
                    **breakdown,
                    "applicable": False,
                    "reason": "no molecular swaps or no clean samples; AUROC undefined",
                },
            )

        return EvalResult(
            name="fidelity_gate",
            passed=auroc >= threshold,
            score=auroc,
            threshold=threshold,
            details={**breakdown, "auroc": auroc, "applicable": True},
        )

    def evaluate_dual(
        self,
        cohort: dict,
        threshold: float = DEFAULT_AUROC_THRESHOLD,
        methods: tuple[str, ...] = DEFAULT_DUAL_METHODS,
    ) -> EvalResult:
        """Gate on TWO mechanically independent detectors (gap #3 mitigation).

        PASS only if the molecular-swap-vs-clean AUROC clears ``threshold`` under
        EVERY method in ``methods`` — an AND gate, never a relaxation of
        :meth:`evaluate`. The score is the minimum AUROC across methods, and
        ``details["detectors_disagree"]`` flags when the methods straddle the
        threshold (one clears it, one does not) — a diagnostic the single-scorer
        gate could not produce. Vacuous pass (``applicable=False``) if ANY method
        has no positives or no clean baseline, exactly as :meth:`evaluate`.

        This breaks the verbatim shared-scorer symmetry (fidelity_gate and
        mislabel_detection both used the single ``expression_rank`` detector): the
        MSE-residual ``linear_model`` fails differently from ``1-|spearman|``. It
        does NOT create a held-out oracle — both detectors read the same
        generator's matrices, so corruption the generator never planted is
        invisible to both (gap #1, blocked on real held-out data, stays open).
        """
        scored = fidelity_auroc_dual(cohort, methods)
        per_method = {m: {"auroc": a, **b} for m, (a, b) in scored.items()}

        if any(auroc is None for auroc, _ in scored.values()):
            return EvalResult(
                name="fidelity_gate",
                passed=True,
                score=1.0,
                threshold=threshold,
                details={
                    "applicable": False,
                    "reason": "no molecular swaps or no clean samples; AUROC undefined",
                    "methods": list(methods),
                    "per_method": per_method,
                },
            )

        aurocs = [a for a, _ in scored.values()]
        lo, hi = min(aurocs), max(aurocs)
        return EvalResult(
            name="fidelity_gate",
            passed=lo >= threshold,
            score=lo,
            threshold=threshold,
            details={
                "applicable": True,
                "methods": list(methods),
                "per_method": per_method,
                "detectors_disagree": (lo < threshold) != (hi < threshold),
            },
        )

    def evaluate_generator(
        self,
        generator,
        threshold: float = DEFAULT_AUROC_THRESHOLD,
        distance_method: str = "expression_rank",
    ) -> EvalResult:
        """Generate a cohort from ``generator`` and gate it."""
        return self.evaluate(
            generator.generate_cohort(),
            threshold=threshold,
            distance_method=distance_method,
        )
