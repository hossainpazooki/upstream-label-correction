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
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.cross_omics_matcher import CrossOmicsMatcher
from core.synthetic import SyntheticCohortGenerator
from evals import EvalResult

if TYPE_CHECKING:
    from collections.abc import Iterable

#: Mislabel types that alter molecular data and are therefore detectable by the
#: cross-omics distance path.
MOLECULAR_SWAP_TYPES = ("proteomics", "rnaseq")


def detect_molecular_mismatches(
    cohort: dict,
    distance_method: str = "expression_rank",
) -> tuple[set[str], list[str]]:
    """Run the cross-omics distance detector over a cohort.

    Returns
    -------
    (flagged_sample_ids, shared_sample_ids)
        ``flagged_sample_ids`` is the set the detector flagged as mismatched.
    """
    matcher = CrossOmicsMatcher()
    proteomics = cohort["proteomics"].set_index("sample_id")
    rnaseq = cohort["rnaseq"].set_index("sample_id")

    shared_samples = sorted(set(proteomics.index) & set(rnaseq.index))
    shared_genes = sorted(set(proteomics.columns) & set(rnaseq.columns))

    distance_matrix = matcher.build_distance_matrix(proteomics, rnaseq, shared_genes, method=distance_method)
    results = matcher.identify_mismatches(distance_matrix, shared_samples)
    flagged = {r["sample_id"] for r in results if r["is_flagged"]}
    return flagged, shared_samples


class MislabelDetectionEval:
    """Score cross-omics mislabel detection against synthetic ground truth."""

    def evaluate(
        self,
        cohort: dict,
        threshold: float = 0.50,
        distance_method: str = "expression_rank",
    ) -> EvalResult:
        """Score the detector on one cohort.

        PASS if F1 of molecular-swap detection >= ``threshold``.
        """
        mislabel_type: dict[str, str] = cohort["ground_truth"].get("mislabel_type", {})

        flagged, shared_samples = detect_molecular_mismatches(cohort, distance_method)
        shared_set = set(shared_samples)

        positives = {sid for sid, t in mislabel_type.items() if t in MOLECULAR_SWAP_TYPES and sid in shared_set}
        clinical_swaps = {sid for sid, t in mislabel_type.items() if t == "clinical" and sid in shared_set}

        # Score only over (clean samples + molecular swaps); clinical swaps are
        # out of scope for the distance path and excluded from the denominator.
        scored = shared_set - clinical_swaps
        flagged_scored = flagged & scored

        tp = flagged_scored & positives
        fp = flagged_scored - positives
        fn = positives - flagged_scored

        n_tp, n_fp, n_fn = len(tp), len(fp), len(fn)
        precision = n_tp / (n_tp + n_fp) if (n_tp + n_fp) else 0.0
        recall = n_tp / (n_tp + n_fn) if (n_tp + n_fn) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

        return EvalResult(
            name="mislabel_detection",
            passed=f1 >= threshold,
            score=f1,
            threshold=threshold,
            details={
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
                "distance_method": distance_method,
            },
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
        mislabel_fractions: Iterable[float],
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
