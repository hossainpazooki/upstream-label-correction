"""Convert a precisionFDA sub-challenge-2 answer key into the mislabel
ground-truth JSON that ``evals.transfer_validation`` consumes (gap #1).

The answer key (``sum_tab_2.csv``: ``sample,Clinical,RNAseq,Proteomics``) is the
genuinely independent oracle — real CPTAC sample-prep swaps, not generator-planted.
This script turns it into ``data/raw/<dataset>_mislabels.json``.

Usage:
    python scripts/build_real_labels.py path/to/sum_tab_2.csv [--dataset train] [--out PATH]

NOTE: the real omics matrices (``<dataset>_pro.tsv`` / ``<dataset>_rna.tsv`` from
precisionFDA / Synapse) must ALSO be placed in ``data/raw`` for
``transfer_validation`` to actually run — this script only stages the labels.
See ``data/raw/README.md``.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

# Allow `python scripts/build_real_labels.py` from the repo root without install.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals.transfer_validation import mislabel_type_from_sum_tab2  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("sum_tab2", help="path to the precisionFDA sum_tab_2.csv answer key")
    ap.add_argument("--dataset", default="train", help="dataset name (train/test); default train")
    ap.add_argument("--out", default=None, help="output path; default data/raw/<dataset>_mislabels.json")
    args = ap.parse_args()

    with open(args.sum_tab2, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    mislabel_type = mislabel_type_from_sum_tab2(rows)
    out = Path(args.out or f"data/raw/{args.dataset}_mislabels.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"mislabel_type": mislabel_type}, indent=2))

    breakdown: dict[str, int] = {}
    for t in mislabel_type.values():
        breakdown[t] = breakdown.get(t, 0) + 1
    print(f"wrote {out}: {len(mislabel_type)} mislabeled / {len(rows)} samples  breakdown={breakdown}")


if __name__ == "__main__":
    main()
