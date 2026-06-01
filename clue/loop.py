"""CLUE closed loop (stage ④): generate → measure → improve → regenerate.

This closes the loop the README describes. Each round:

1. **Generate** a synthetic cohort at the round's corruption rate (known ground
   truth).
2. **Measure** the cross-omics detector against that ground truth.
3. **Improve** the detector by tuning its decision threshold to maximise F1 —
   driven entirely by the measured score, not by hand.
4. **Feed back**: if the tuned detector clears the F1 target, raise the
   corruption rate to probe a harder regime real data can't reach (regenerate
   a harder cohort); if it can no longer clear the target, stop and report the
   detector's operating frontier.

Scope of "improve": today the tunable is the detector's **decision threshold**
on per-sample mismatch frequency. Full model retraining (the classification
path) is a deeper future lever; the loop's structure accommodates it but does
not yet drive it. Everything here is deterministic for a given seed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.synthetic import SyntheticCohortGenerator
from evals.mislabel_detection import mismatch_frequencies, score_molecular_detection

#: Decision thresholds searched during the improve step.
DEFAULT_THRESHOLDS = (0.3, 0.4, 0.5, 0.6, 0.7)


@dataclass
class RoundResult:
    """Outcome of one generate→measure→improve round."""

    iteration: int
    mislabel_fraction: float
    best_threshold: float
    precision: float
    recall: float
    f1: float
    passed: bool
    n_molecular_swaps: int


@dataclass
class LoopResult:
    """Full history of a CLUE loop run and the detector's operating frontier."""

    rounds: list[RoundResult] = field(default_factory=list)
    target_f1: float = 0.0
    #: Highest corruption rate at which the tuned detector still cleared the
    #: target F1, or ``None`` if it never did.
    frontier_fraction: float | None = None

    @property
    def best_round(self) -> RoundResult | None:
        return max(self.rounds, key=lambda r: r.f1) if self.rounds else None


def tune_decision_threshold(
    cohort: dict,
    candidates: tuple[float, ...] = DEFAULT_THRESHOLDS,
    distance_method: str = "expression_rank",
) -> tuple[float, dict]:
    """IMPROVE step: pick the decision threshold that maximises F1.

    Runs the detector once to get continuous per-sample scores, then scores
    each candidate threshold against the planted ground truth and returns the
    best ``(threshold, metrics)``. Ties break toward the higher threshold
    (fewer false positives).
    """
    frequencies, shared_samples = mismatch_frequencies(cohort, distance_method)
    mislabel_type = cohort["ground_truth"].get("mislabel_type", {})

    best_threshold = candidates[0]
    best_metrics: dict | None = None
    for tau in candidates:
        flagged = {sid for sid, freq in frequencies.items() if freq > tau}
        metrics = score_molecular_detection(flagged, mislabel_type, shared_samples)
        if best_metrics is None or metrics["f1"] >= best_metrics["f1"]:
            best_threshold, best_metrics = tau, metrics

    assert best_metrics is not None  # noqa: S101  invariant check (candidates is non-empty), not security-sensitive
    return best_threshold, best_metrics


class CLUELoop:
    """Drive the closed loop until the detector reaches its operating frontier."""

    def __init__(
        self,
        *,
        target_f1: float = 0.80,
        start_fraction: float = 0.05,
        fraction_step: float = 0.05,
        max_fraction: float = 0.40,
        max_rounds: int = 8,
        n_samples: int = 80,
        n_genes_proteomics: int = 2000,
        n_genes_rnaseq: int = 4000,
        seed: int = 42,
        thresholds: tuple[float, ...] = DEFAULT_THRESHOLDS,
        distance_method: str = "expression_rank",
    ) -> None:
        self.target_f1 = target_f1
        self.start_fraction = start_fraction
        self.fraction_step = fraction_step
        self.max_fraction = max_fraction
        self.max_rounds = max_rounds
        self.n_samples = n_samples
        self.n_genes_proteomics = n_genes_proteomics
        self.n_genes_rnaseq = n_genes_rnaseq
        self.seed = seed
        self.thresholds = thresholds
        self.distance_method = distance_method

    def _generate(self, fraction: float, iteration: int) -> dict:
        generator = SyntheticCohortGenerator(
            n_samples=self.n_samples,
            n_genes_proteomics=self.n_genes_proteomics,
            n_genes_rnaseq=self.n_genes_rnaseq,
            mislabel_fraction=fraction,
            seed=self.seed + iteration,  # a fresh cohort each round, still deterministic
        )
        return generator.generate_cohort()

    def run(self) -> LoopResult:
        """Run the loop and return its history + frontier."""
        result = LoopResult(target_f1=self.target_f1)
        fraction = round(self.start_fraction, 4)

        for iteration in range(self.max_rounds):
            cohort = self._generate(fraction, iteration)
            threshold, metrics = tune_decision_threshold(cohort, self.thresholds, self.distance_method)
            passed = metrics["f1"] >= self.target_f1

            result.rounds.append(
                RoundResult(
                    iteration=iteration,
                    mislabel_fraction=fraction,
                    best_threshold=threshold,
                    precision=metrics["precision"],
                    recall=metrics["recall"],
                    f1=metrics["f1"],
                    passed=passed,
                    n_molecular_swaps=metrics["n_molecular_swaps"],
                )
            )

            if not passed:
                # Detector ceiling: tuning could not clear the target at this rate.
                break

            result.frontier_fraction = fraction
            next_fraction = round(fraction + self.fraction_step, 4)
            if next_fraction > self.max_fraction:
                break  # probed as hard as configured; detector still holding
            fraction = next_fraction

        return result
