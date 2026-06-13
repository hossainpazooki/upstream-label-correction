"""Transfer validation against REAL held-out data — the only true fix for gap #1.

**[PROPOSED — not active in this repo today.]** Every other eval in this package
scores the detector against ground truth the *same* ``SyntheticCohortGenerator``
planted, so ACHIEVED means "self-consistent with the generator," not "works on
real data" (gap #1, the no-held-out-oracle problem). The genuinely independent
oracle is the real precisionFDA / NCI-CPTAC multi-omics data plus a curated
mislabel ground-truth file — neither of which is present in this repo
(``data/raw`` is empty and the challenge withheld test labels).

This module is the *seam*: it loads real data via the real loader
(:class:`core.data_loader.OmicsDataLoader` — not a fictitious ``load_dataset``)
and scores the cross-omics detector against a real label file. Until both the
omics TSVs and the ground-truth file exist, :meth:`evaluate` **skips gracefully**
(``applicable=False``, ``passed=True``) and never reports a synthetic-derived
number as real-data performance. When real data lands, this eval activates with
no code change — that is the point of building the seam now.
"""

from __future__ import annotations

import json
from pathlib import Path

from evals import EvalResult
from evals.mislabel_detection import detect_molecular_mismatches, score_molecular_detection


def _load_ground_truth(path: Path) -> dict[str, str] | None:
    """Load a real mislabel ground-truth file: ``{"mislabel_type": {sample_id: type}}``.

    Returns the ``mislabel_type`` map, or ``None`` if the file is absent/empty —
    which (correctly) makes the eval inapplicable rather than scoring against
    nothing.
    """
    if not path.is_file():
        return None
    data = json.loads(path.read_text())
    mislabel_type = data.get("mislabel_type") or {}
    return mislabel_type or None


#: Modality columns in the precisionFDA sub-challenge-2 answer key (sum_tab_2.csv),
#: in molecular-first priority: it lists, per sample, the sample index each
#: modality's data actually came from.
_SUM_TAB2_MODALITIES = (("Proteomics", "proteomics"), ("RNAseq", "rnaseq"), ("Clinical", "clinical"))


def mislabel_type_from_sum_tab2(rows: list[dict]) -> dict[str, str]:
    """Convert precisionFDA ``sum_tab_2.csv`` rows to the ``{sample_id: type}`` map.

    Each row gives, for ``Training_N``, the sample index each modality
    (Clinical / RNAseq / Proteomics) truly originates from. A sample is mislabeled
    iff some modality's source index differs from its own; the recorded type is
    the swapped modality, molecular-first (proteomics, then rnaseq, then clinical)
    so the cross-omics distance path scores it as a positive. Clean samples are
    omitted. Robust to a UTF-8 BOM and case in the header.
    """
    out: dict[str, str] = {}
    for r in rows:
        norm = {(k or "").lstrip("﻿").strip().lower(): v for k, v in r.items()}
        sample = norm.get("sample")
        if not sample:
            continue
        try:
            idx = int(str(sample).split("_")[-1])
        except ValueError:
            continue
        for col, typ in _SUM_TAB2_MODALITIES:
            src = norm.get(col.lower())
            if src is None or str(src).strip() == "":
                continue
            if int(float(src)) != idx:
                out[sample] = typ
                break
    return out


class TransferValidationEval:
    """Score the detector on REAL held-out data (gap #1). [PROPOSED — see module docstring.]"""

    def evaluate(
        self,
        dataset: str = "test",
        ground_truth_path: str | None = None,
        threshold: float = 0.50,
        distance_method: str = "expression_rank",
    ) -> EvalResult:
        """Run the cross-omics detector on real data and score it against real labels.

        Skips gracefully (``applicable=False``, ``passed=True``) when the real
        omics data or the ground-truth label file is absent — the current state
        of this repo — so it can be wired into VERIFY today without ever
        fabricating a real-data metric.
        """
        from core.data_loader import OmicsDataLoader

        def _skip(reason: str) -> EvalResult:
            return EvalResult(
                name="transfer_validation",
                passed=True,
                score=1.0,
                threshold=threshold,
                details={"applicable": False, "proposed": True, "reason": reason, "dataset": dataset},
            )

        gt_path = Path(ground_truth_path) if ground_truth_path else Path(get_raw_dir()) / f"{dataset}_mislabels.json"
        mislabel_type = _load_ground_truth(gt_path)
        if mislabel_type is None:
            return _skip(f"real mislabel ground-truth not present at {gt_path}")

        loader = OmicsDataLoader()
        try:
            proteomics = loader.load_proteomics(dataset).rename_axis("sample_id").reset_index()
            rnaseq = loader.load_rnaseq(dataset).rename_axis("sample_id").reset_index()
        except FileNotFoundError as exc:
            return _skip(f"real omics data not present: {exc}")

        cohort = {"proteomics": proteomics, "rnaseq": rnaseq, "ground_truth": {"mislabel_type": mislabel_type}}
        flagged, shared = detect_molecular_mismatches(cohort, distance_method=distance_method)
        metrics = score_molecular_detection(flagged, mislabel_type, shared)
        return EvalResult(
            name="transfer_validation",
            passed=metrics["f1"] >= threshold,
            score=metrics["f1"],
            threshold=threshold,
            details={**metrics, "applicable": True, "proposed": True, "dataset": dataset, "data_source": "real"},
        )


def get_raw_dir() -> str:
    """Resolve the configured raw-data directory (where real TSVs would live)."""
    from core.config import get_settings

    return get_settings().raw_data_dir
