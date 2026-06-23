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
| `<dataset>_pro.tsv` | proteomics matrix (genes as rows, samples as columns) | public mirror [`ACHG2018/fda-mislabeling-challenge`](https://github.com/ACHG2018/fda-mislabeling-challenge) `challenge_data/` (train present locally) |
| `<dataset>_rna.tsv` | RNA-Seq matrix (genes as rows, samples as columns) | public mirror [`ACHG2018/fda-mislabeling-challenge`](https://github.com/ACHG2018/fda-mislabeling-challenge) `challenge_data/` (train present locally) |
| `<dataset>_cli.tsv` | clinical matrix (optional) | same mirror / the user's repo |
| `<dataset>_mislabels.json` | mislabel ground-truth labels | generated locally (see below) |

`<dataset>` is `train` or `test`. The two molecular matrices (`_pro` + `_rna`)
are the load-bearing ones the cross-omics distance path consumes.

## Generating the labels

The answer key is the per-modality oracle `sum_tab_2.csv`, available both in the
user's older repo
[`hossainpazooki/precisionFDA-mislabel-challenge`](https://github.com/hossainpazooki/precisionFDA-mislabel-challenge)
(`src/raw_data/sum_tab_2.csv`) and in the public mirror
[`ACHG2018/fda-mislabeling-challenge`](https://github.com/ACHG2018/fda-mislabeling-challenge)
(`challenge_data/sum_tab_2.csv`). Convert it with:

```sh
python scripts/build_real_labels.py <path to sum_tab_2.csv> --dataset train
```

This writes `data/raw/train_mislabels.json`. Expected result for sub-challenge 2:
**20 mislabeled of 80 samples** — breakdown `{proteomics: 8, rnaseq: 8,
clinical: 4}` (each mislabeled sample has exactly one swapped modality).

> Do **not** use `sum_tab_1.csv` from that repo — it is a different binary answer
> key (12 mislabeled) for a different sub-challenge.

## Current status: TRAIN oracle ACTIVE; TEST oracle still gated

The **training** molecular matrices (`train_pro.tsv` 4119×80, `train_rna.tsv`
17448×80) were obtained from the public mirror above and now sit here (gitignored).
`transfer_validation.evaluate('train')` therefore runs for real:
`applicable=True, data_source=real`, **fixed-0.5 F1 = 0.914** (precision 0.842,
recall 1.000; TP 16 / FP 3 / FN 0) against the organizers' key — **gap #1 is closed
for the train partition** (see [`../../docs/TRANSFER_VALIDATION_RUN.md`](../../docs/TRANSFER_VALIDATION_RUN.md),
Run 3).

The **test** matrices (`test_pro.tsv` / `test_rna.tsv`) are also present, but the
challenge **withheld** the test mislabel labels, so there is no `test_mislabels.json`
oracle — `transfer_validation.evaluate('test')` **skips gracefully**
(`applicable=False`, `passed=True`) and never fabricates a number. That blind-test
oracle is the remaining open piece of gap #1.

> **Provenance caveat:** the matrices came from a participant mirror, not the
> official precisionFDA portal. Sample-namespace + key alignment corroborate the
> match; a spot-check against the official Synapse/precisionFDA download is
> recommended before quoting the 0.914 externally.
