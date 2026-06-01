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

Scope of "improve" — selected by the ``improve_mode`` lever:

* ``"threshold"`` (default) — tune the **distance** detector's decision
  threshold on per-sample mismatch frequency (``tune_decision_threshold``).
* ``"retrain"`` — fully **retrain the classification path**
  (``EnsembleMismatchClassifier``) from measured feedback.
* ``"both"`` — do both and report each.

The retrain lever observes the **no-leakage** rule the whole project rests on:
the classifier is fitted on a *separate* train cohort (same corruption rate and
geometry, but a disjoint seed) and scored on the held-out measure cohort it has
never seen — so ``retrain_f1`` is an honest, unseen-data metric, never the
detector's own training set. Loop *control* (``passed`` / ``frontier_fraction``)
stays keyed on the distance-threshold F1 in every mode; retrain metrics are
reported alongside. Hard-example reweighting is a further lever the structure
admits but does not yet drive. Everything here is deterministic for a given seed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

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
    #: Which improve lever produced this round (default keeps existing callers).
    improve_mode: str = "threshold"
    #: Held-out classification-path metrics from the retrain lever, populated
    #: only when ``improve_mode`` is ``"retrain"``/``"both"`` (else ``None``).
    #: ``retrain_f1`` is scored on the measure cohort the classifier never saw.
    retrain_f1: float | None = None
    retrain_precision: float | None = None
    retrain_recall: float | None = None
    #: Seed of the disjoint train cohort the classifier was fitted on — makes
    #: the train/measure separation auditable. ``None`` when not retraining.
    train_seed: int | None = None


@dataclass
class LoopResult:
    """Full history of a CLUE loop run and the detector's operating frontier."""

    rounds: list[RoundResult] = field(default_factory=list)
    target_f1: float = 0.0
    #: Highest corruption rate at which the tuned detector still cleared the
    #: target F1, or ``None`` if it never did.
    frontier_fraction: float | None = None
    #: The improve lever the loop was configured with (echoed for consumers).
    improve_mode: str = "threshold"

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


def build_classifier_xy(
    cohort: dict,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Build ``(X, y_gender, y_msi, mismatch_labels)`` for the ensemble classifier.

    ``X`` is each sample's proteomics and RNA-Seq profiles over the genes the two
    modalities **share** (inner join, columns sorted for a stable, deterministic
    order), concatenated and aligned to the clinical sample order. Labels come
    from this cohort's own planted ground truth. Everything is derived from
    *this* cohort only — keeping train and measure cohorts disjoint is the
    caller's job (see :meth:`CLUELoop._generate_train`).
    """
    clinical = cohort["clinical"]
    proteomics = cohort["proteomics"].set_index("sample_id")
    rnaseq = cohort["rnaseq"].set_index("sample_id")

    shared_samples = set(proteomics.index) & set(rnaseq.index)
    shared_genes = sorted(set(proteomics.columns) & set(rnaseq.columns))

    # Preserve clinical sample order, restricted to samples in both modalities.
    order = [sid for sid in clinical["sample_id"].tolist() if sid in shared_samples]

    pro = proteomics.loc[order, shared_genes].to_numpy(dtype=float)
    rna = rnaseq.loc[order, shared_genes].to_numpy(dtype=float)
    X = np.hstack([pro, rna])

    clin = clinical.set_index("sample_id").loc[order]
    y_gender = (clin["gender"] == "Male").to_numpy().astype(int)
    y_msi = (clin["MSI_status"] == "MSI-H").to_numpy().astype(int)

    mislabeled = set(cohort["ground_truth"].get("mislabeled_samples", []))
    mismatch_labels = np.array([1 if sid in mislabeled else 0 for sid in order], dtype=int)

    return X, y_gender, y_msi, mismatch_labels


def retrain_and_score(
    train_cohort: dict,
    measure_cohort: dict,
    random_state: int = 42,
) -> dict:
    """RETRAIN step: fit the classifier on the train cohort, score on the measure cohort.

    The ensemble is fitted **only** on ``train_cohort`` and scored **only** on the
    held-out ``measure_cohort`` — the two must come from disjoint seeds so the
    detector is never trained on the ground truth it is then scored against.
    Returns weighted ``{f1, precision, recall}`` on the (unseen) measure cohort.
    """
    from core.classifier import EnsembleMismatchClassifier

    X_tr, yg_tr, ym_tr, mm_tr = build_classifier_xy(train_cohort)
    X_me, _yg_me, _ym_me, mm_me = build_classifier_xy(measure_cohort)

    clf = EnsembleMismatchClassifier(random_state=random_state)
    clf.fit(X_tr, yg_tr, ym_tr, mm_tr)
    metrics = clf.evaluate(X_me, mm_me)
    return {
        "f1": float(metrics["f1"]),
        "precision": float(metrics["precision"]),
        "recall": float(metrics["recall"]),
    }


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
        improve_mode: str = "threshold",
        classifier_random_state: int = 42,
        train_seed_offset: int = 1000,
    ) -> None:
        if improve_mode not in ("threshold", "retrain", "both"):
            raise ValueError(
                f"improve_mode must be 'threshold', 'retrain', or 'both'; got {improve_mode!r}"
            )
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
        self.improve_mode = improve_mode
        self.classifier_random_state = classifier_random_state
        #: Offset added to the measure seed to build a disjoint train cohort.
        #: Large enough that train seeds never collide with measure seeds
        #: (``self.seed + iteration`` for ``iteration`` in ``[0, max_rounds)``).
        self.train_seed_offset = train_seed_offset

    def _generate(self, fraction: float, iteration: int) -> dict:
        generator = SyntheticCohortGenerator(
            n_samples=self.n_samples,
            n_genes_proteomics=self.n_genes_proteomics,
            n_genes_rnaseq=self.n_genes_rnaseq,
            mislabel_fraction=fraction,
            seed=self.seed + iteration,  # a fresh cohort each round, still deterministic
        )
        return generator.generate_cohort()

    def _generate_train(self, fraction: float, iteration: int) -> dict:
        """Generate a DISJOINT train cohort for the retrain lever.

        Same corruption rate and geometry as the measure cohort but a seed
        offset by ``train_seed_offset``, so neither its samples nor its RNG
        stream overlap the measure cohort (seed ``self.seed + iteration``).
        This is the train/measure separation that keeps retrain F1 honest.
        """
        generator = SyntheticCohortGenerator(
            n_samples=self.n_samples,
            n_genes_proteomics=self.n_genes_proteomics,
            n_genes_rnaseq=self.n_genes_rnaseq,
            mislabel_fraction=fraction,
            seed=self.seed + self.train_seed_offset + iteration,
        )
        return generator.generate_cohort()

    def run(self) -> LoopResult:
        """Run the loop and return its history + frontier."""
        result = LoopResult(target_f1=self.target_f1, improve_mode=self.improve_mode)
        fraction = round(self.start_fraction, 4)

        for iteration in range(self.max_rounds):
            cohort = self._generate(fraction, iteration)
            threshold, metrics = tune_decision_threshold(cohort, self.thresholds, self.distance_method)
            # Loop control stays keyed on the distance-threshold F1 in EVERY
            # mode; retrain metrics (below) are reported, not used to escalate.
            passed = metrics["f1"] >= self.target_f1

            round_result = RoundResult(
                iteration=iteration,
                mislabel_fraction=fraction,
                best_threshold=threshold,
                precision=metrics["precision"],
                recall=metrics["recall"],
                f1=metrics["f1"],
                passed=passed,
                n_molecular_swaps=metrics["n_molecular_swaps"],
                improve_mode=self.improve_mode,
            )

            if self.improve_mode in ("retrain", "both"):
                # Fit on a disjoint train cohort, score on the unseen measure
                # cohort — held-out, no leakage.
                train_cohort = self._generate_train(fraction, iteration)
                retrain = retrain_and_score(train_cohort, cohort, self.classifier_random_state)
                round_result.retrain_f1 = retrain["f1"]
                round_result.retrain_precision = retrain["precision"]
                round_result.retrain_recall = retrain["recall"]
                round_result.train_seed = self.seed + self.train_seed_offset + iteration

            result.rounds.append(round_result)

            if not passed:
                # Detector ceiling: tuning could not clear the target at this rate.
                break

            result.frontier_fraction = fraction
            next_fraction = round(fraction + self.fraction_step, 4)
            if next_fraction > self.max_fraction:
                break  # probed as hard as configured; detector still holding
            fraction = next_fraction

        return result
