# `data/raw/` — real held-out data for transfer validation (gap #1)

This directory is where **real** precisionFDA / NCI-CPTAC sub-challenge-2 data
goes — the genuinely independent oracle that `evals/transfer_validation.py`
scores the cross-omics detector against. It is **gitignored**: CPTAC-derived
data must never be committed. (`*.tsv` and `*.csv` are already ignored; keep any
`*.json` labels you generate here out of git too.)

Nothing in this directory is required for the synthetic loop. It only matters
when you want to close gap #1 — measuring the detector against ground truth the
generator did **not** plant.

## Files needed to ACTIVATE `transfer_validation`

| File | Role | Source |
|------|------|--------|
| `<dataset>_pro.tsv` | proteomics matrix (genes as rows, samples as columns) | precisionFDA / Synapse — **NOT** in the user's GitHub repo |
| `<dataset>_rna.tsv` | RNA-Seq matrix (genes as rows, samples as columns) | precisionFDA / Synapse — **NOT** in the user's GitHub repo |
| `<dataset>_cli.tsv` | clinical matrix (optional) | present in the user's repo |
| `<dataset>_mislabels.json` | mislabel ground-truth labels | generated locally (see below) |

`<dataset>` is `train` or `test`. The two molecular matrices (`_pro` + `_rna`)
are the load-bearing ones the cross-omics distance path consumes.

## Generating the labels

The answer key is the per-modality oracle `sum_tab_2.csv`, which lives in the
user's older repo
[`hossainpazooki/precisionFDA-mislabel-challenge`](https://github.com/hossainpazooki/precisionFDA-mislabel-challenge)
at `src/raw_data/sum_tab_2.csv`. Convert it with:

```sh
python scripts/build_real_labels.py <path to sum_tab_2.csv> --dataset train
```

This writes `data/raw/train_mislabels.json`. Expected result for sub-challenge 2:
**20 mislabeled of 80 samples** — breakdown `{proteomics: 8, rnaseq: 8,
clinical: 4}` (each mislabeled sample has exactly one swapped modality).

> Do **not** use `sum_tab_1.csv` from that repo — it is a different binary answer
> key (12 mislabeled) for a different sub-challenge.

## Current status: BLOCKED by design

The molecular matrices (`_pro.tsv` / `_rna.tsv`) are **not** in the user's GitHub
repo — only the clinical TSVs, notebooks, and answer keys are. Until those
matrices are placed here, `transfer_validation.evaluate()` **skips gracefully**
(`applicable=False`, `passed=True`) and never reports a synthetic-derived number
as real-data performance. Gap #1 therefore remains **open** — this is intended
honest behavior, not a failure. When the matrices land, the eval activates with
no code change.
