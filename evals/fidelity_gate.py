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
