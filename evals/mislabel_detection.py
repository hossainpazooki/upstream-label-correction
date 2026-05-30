"""Mislabel-detection eval — the measurement edge of the CLUE loop (stage ③).

Generate a synthetic cohort with known injected swaps, run the cross-omics
distance detector, and score its flags against the generator's planted
``swap_pairs`` as precision / recall / F1.

Scope: the cross-omics *distance* path compares each sample's proteomics and
RNA-Seq profiles, so it surfaces **molecular** swaps (``proteomics`` / ``rnaseq``
mislabel types) where a sample's two modalities no longer agree. A
``clinical``-only swap exchanges MSI/gender labels but leaves both molecular
matrices intact, so it is invisible to this path (it is the classification
path's job). Clinical-swap samples are therefore excluded from the scored set
and reported separately in ``details`` — scoring them as errors would penalise
the distance detector for something outside its remit.

The reusable building blocks here (:func:`mismatch_frequencies` and
:func:`score_molecular_detection`) are shared with the CLUE closed loop
(``clue/loop.py``) so that the "measure" and "improve" stages score detection
identically.
"""

from __future__ import annotations

from core.cross_omics_matcher import CrossOmicsMatcher
from core.synthetic import SyntheticCohortGenerator
from evals import EvalResult

#: Mislabel types that alter molecular data and are therefore detectable by the
#: cross-omics distance path.
MOLECULAR_SWAP_TYPES = ("proteomics", "rnaseq")

#: Default decision threshold on per-sample mismatch frequency (matches the
#: detector's built-in ``is_flagged = frequency > 0.5``).
DEFAULT_FLAG_THRESHOLD = 0.5


def mismatch_frequencies(
    cohort: dict,
    distance_method: str = "expression_rank",
) -> tuple[dict[str, float], list[str]]:
    """Run the cross-omics distance detector and return per-sample scores.

    Returns
    -------
    (frequencies, shared_sample_ids)
        ``frequencies`` maps each sample to its mismatch frequency in [0, 1] —
        the continuous detector score before any decision threshold is applied.
    """
    matcher = CrossOmicsMatcher()
    proteomics = cohort["proteomics"].set_index("sample_id")
    rnaseq = cohort["rnaseq"].set_index("sample_id")

    shared_samples = sorted(set(proteomics.index) & set(rnaseq.index))
    shared_genes = sorted(set(proteomics.columns) & set(rnaseq.columns))

    distance_matrix = matcher.build_distance_matrix(proteomics, rnaseq, shared_genes, method=distance_method)
    results = matcher.identify_mismatches(distance_matrix, shared_samples)
    frequencies = {r["sample_id"]: float(r["mismatch_frequency"]) for r in results}
    return frequencies, shared_samples


def detect_molecular_mismatches(
    cohort: dict,
    distance_method: str = "expression_rank",
    flag_threshold: float = DEFAULT_FLAG_THRESHOLD,
) -> tuple[set[str], list[str]]:
    """Run the detector and apply a decision threshold.

    Returns ``(flagged_sample_ids, shared_sample_ids)``.
    """
    frequencies, shared_samples = mismatch_frequencies(cohort, distance_method)
    flagged = {sid for sid, freq in frequencies.items() if freq > flag_threshold}
    return flagged, shared_samples


def score_molecular_detection(
    flagged: set[str],
    mislabel_type: dict[str, str],
    shared_samples: list[str],
) -> dict:
    """Score flagged samples against the planted molecular-swap ground truth.

    Clinical swaps are excluded from the scored set (out of scope for the
    distance path) and reported separately.
    """
    shared_set = set(shared_samples)
    positives = {sid for sid, t in mislabel_type.items() if t in MOLECULAR_SWAP_TYPES and sid in shared_set}
    clinical_swaps = {sid for sid, t in mislabel_type.items() if t == "clinical" and sid in shared_set}

    scored = shared_set - clinical_swaps
    flagged_scored = flagged & scored

    tp = flagged_scored & positives
    fp = flagged_scored - positives
    fn = positives - flagged_scored

    n_tp, n_fp, n_fn = len(tp), len(fp), len(fn)
    precision = n_tp / (n_tp + n_fp) if (n_tp + n_fp) else 0.0
    recall = n_tp / (n_tp + n_fn) if (n_tp + n_fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "n_molecular_swaps": len(positives),
        "n_flagged": len(flagged_scored),
        "true_positives": sorted(tp),
        "false_positives": sorted(fp),
        "false_negatives": sorted(fn),
        "clinical_swaps_out_of_scope": sorted(clinical_swaps),
        "clinical_swaps_incidentally_flagged": sorted(flagged & clinical_swaps),
    }


class MislabelDetectionEval:
    """Score cross-omics mislabel detection against synthetic ground truth."""

    def evaluate(
        self,
        cohort: dict,
        threshold: float = 0.50,
        distance_method: str = "expression_rank",
        flag_threshold: float = DEFAULT_FLAG_THRESHOLD,
    ) -> EvalResult:
        """Score the detector on one cohort.

        PASS if F1 of molecular-swap detection >= ``threshold``.
        """
        mislabel_type: dict[str, str] = cohort["ground_truth"].get("mislabel_type", {})

        flagged, shared_samples = detect_molecular_mismatches(cohort, distance_method, flag_threshold)
        metrics = score_molecular_detection(flagged, mislabel_type, shared_samples)

        return EvalResult(
            name="mislabel_detection",
            passed=metrics["f1"] >= threshold,
            score=metrics["f1"],
            threshold=threshold,
            details={**metrics, "distance_method": distance_method, "flag_threshold": flag_threshold},
        )

    def evaluate_generator(
        self,
        generator: SyntheticCohortGenerator,
        threshold: float = 0.50,
        distance_method: str = "expression_rank",
    ) -> EvalResult:
        """Generate a cohort from ``generator`` and score it."""
        return self.evaluate(
            generator.generate_cohort(),
            threshold=threshold,
            distance_method=distance_method,
        )

    def sweep(
        self,
        mislabel_fractions,
        *,
        n_samples: int = 80,
        n_genes_proteomics: int = 2000,
        n_genes_rnaseq: int = 4000,
        seed: int = 42,
        threshold: float = 0.50,
        distance_method: str = "expression_rank",
    ) -> list[EvalResult]:
        """Measure detection across corruption rates real data cannot probe.

        Returns one :class:`EvalResult` per fraction, each tagged with its
        ``mislabel_fraction`` in ``details``.
        """
        results: list[EvalResult] = []
        for fraction in mislabel_fractions:
            generator = SyntheticCohortGenerator(
                n_samples=n_samples,
                n_genes_proteomics=n_genes_proteomics,
                n_genes_rnaseq=n_genes_rnaseq,
                mislabel_fraction=fraction,
                seed=seed,
            )
            result = self.evaluate(
                generator.generate_cohort(),
                threshold=threshold,
                distance_method=distance_method,
            )
            result.details["mislabel_fraction"] = fraction
            results.append(result)
        return results
