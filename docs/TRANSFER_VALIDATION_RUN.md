# Real-matrix robustness run — CLUE detector on COSMO matrices (self-injected swaps)

A durable record of running the CLUE cross-omics detector on **real** COSMO
multi-omics matrices. Two honest takeaways:

1. **Real-matrix ingestion works** (a genuine milestone): the detector built on
   synthetic cohorts runs **unmodified** on real CPTAC/TCGA matrices — real NaN,
   real gene namespaces, real scales.
2. Against **self-injected** rnaseq label-swaps it recovers them at a fixed-0.5
   micro-F1 of **0.85** (recall 1.0).

> **This is NOT independent validation and does NOT close gap #1.** The public
> COSMO tarball ships base matrices with **no mislabel keys** (the premise that it
> held keyed simulated cohorts was wrong). So the "answer key" here was authored
> by *this experiment* — a numpy label-shuffle. That makes the **features**
> independent of CLUE's generator but leaves the **oracle self-made**: gap #1's
> circularity is *relocated onto real features, not broken*. rnaseq-only injection
> makes 0.85 an **optimistic bound**, not a performance estimate.

Read alongside [`docs/GAP_AUDIT.md`](GAP_AUDIT.md) (gap #1 row) and
[`LEARNINGS.md`](../LEARNINGS.md).

## Headline (honest label)

> **Real-matrix robustness number** — the detector recovering swaps **we
> injected ourselves** into real COSMO matrices. It is independent of CLUE's
> *generator module* but **not** of *us* (we authored the corruption), so it is
> **not** independent validation and does **not** close gap #1. It is also **not**
> real-world clinical performance — that needs actual clinical mislabel truth (the
> gated precisionFDA held-out partition), not used here. Read 0.85 as an
> **optimistic upper bound** (rnaseq-only swaps ⇒ recall 1.0).

- **Fixed-0.5 micro-F1 = 0.8462** (pooled TP=55 / FP=20 / FN=0 across 3
  cohorts; precision 0.7333, recall 1.0000). This is the headline number.
- Macro-F1 (unweighted mean of per-cohort F1) = 0.8575 — reported as a
  secondary because cohorts have unequal swap counts.
- The decision threshold was held **fixed at the detector default 0.5** and was
  **not** selected against the COSMO key — deliberately, to avoid reintroducing
  tune-on-test (gap #2). Tuned-threshold figures appear below as **reference
  only** and must never be quoted as the headline.

## Data provenance

- **Source:** COSMO datasets release from the **Bing Zhang lab** (Baylor College
  of Medicine), a co-organizer of the precisionFDA NCI-CPTAC Multi-omics Sample
  Mislabeling Correction Challenge.
- **Tarball:** `http://pdv.zhang-lab.org/data/download/cosmo/cosmo_datasets.tar.gz`
  (~237 MB; 237,605,376 bytes as downloaded). Extracted to the gitignored
  scratch dir `data/raw/cosmo/cosmo_datasets/`.
- **Contents (uncompressed ~600 MB), all matrices genes-as-rows x
  samples-as-columns with sample IDs in the header row:**
  - `Battle_etal/` — clinic, proteome, riboseq, rnaseq
  - `CCLE/` — clinic, cnv, proteome, rnaseq
  - `CCRCC/` — clinic, CNV, proteome, rnaseq
  - `Chick_etal/` — cli, proteome, rnaseq
  - `LUAD/` — clinic, cnv, proteome, rnaseq
  - `TCGA_BRCA/` — clinic, cnv, microarray, rnaseq

### Premise correction (important)

The task premise expected the tarball to contain *simulated colorectal cohorts
with fixed, keyed mislabel ground truth*. **It does not.** An exhaustive scan of
the extracted tree found **no ground-truth keys, no README, no simulated-cohort
subdirectories, and no json/key/truth/shuffle files** — only the 6 real,
**unlabeled** CPTAC/TCGA cohorts above. The "keyed simulated cohorts" are not
part of this public release.

**Resolution chosen — and its honest limit:** rather than fall back to CLUE's
`core/synthetic.py`, the answer key was built by shuffling a known fraction of
real sample labels (a numpy derangement). This keeps the *features* real and
avoids calling CLUE's simulator — but it does **not** make the key independent of
the experimenter: *we* still decide which samples are corrupted and how. So it
does **not** close gap #1; it only moves a self-authored corruption onto real
expression matrices. A genuinely independent key must be authored by an outside
party — **COSMO's own** published error-simulation protocol (simulated, but not
ours), or the **real clinical** mislabel truth in the gated precisionFDA
partition. (The premise that those keyed cohorts shipped in the tarball was
wrong — see above.)

## Exact steps run

Scratch script: `data/raw/cosmo/score_independent.py` (gitignored), run as
`python score_independent.py` from `data/raw/cosmo`. Steps:

1. For each scored cohort, read `proteome` and `rnaseq` TSVs (genes-as-rows x
   samples-as-cols), **transpose** to samples x genes, and reset the sample
   index into a `"sample_id"` column — matching the shared detector contract.
2. Build an **independent answer key**: select `round(0.20 * n)` sample
   positions and apply a `numpy.random.RandomState(42)` **derangement** (a
   permutation with no fixed points) to their `sample_id` labels in the
   **rnaseq modality only**. Each affected sample now carries a wrong rnaseq
   profile — a molecular swap, key-type `"rnaseq"`.
3. Assemble the cohort dict per the shared contract (`proteomics` / `rnaseq`
   DataFrames, each with a `"sample_id"` column + gene columns).
4. Run `evals.mislabel_detection.mismatch_frequencies` (default
   `distance_method="expression_rank"`, which reuses `core.CrossOmicsMatcher`
   with its internal `RandomState(42)`).
5. Flag at the **fixed** threshold: `flagged = {s for s, f in freqs.items() if
   f > 0.5}`.
6. Score via `evals.mislabel_detection.score_molecular_detection`
   (POSITIVES = samples whose key-type is in `{proteomics, rnaseq}`;
   `clinical`-only swaps are out of scope and excluded — none were injected).

### Independent recomputation (verification, not self-report)

- **In-harness:** `recompute_f1_from_raw()` recomputes P/R/F1 directly from the
  raw flagged set vs the raw mislabel key, separate from the scorer's returned
  numbers — `helper_matches_independent == True` on every cohort (to 1e-9).
- **Separate code path:** a verification script re-derived the entire key from
  scratch under `RandomState(42)`, rebuilt the cross-omics distance matrix by
  calling `CrossOmicsMatcher.build_distance_matrix` + `identify_mismatches`
  **directly** (bypassing the eval wrappers), flagged at >0.5, and pooled
  tp/fp/fn from scratch -> micro-F1 = 0.8462, identical to the harness
  (`match=True`).
- **In writing this record:** micro/macro/per-cohort F1 were recomputed once
  more from the raw confusion counts in `data/raw/cosmo/result.json`
  (tp=55/fp=20/fn=0) and reproduce every figure below exactly.

## Key assumptions

- **COSMO-key -> CLUE mislabel_type mapping.** Every sample whose rnaseq label
  was moved by the derangement is assigned mislabel-type `"rnaseq"` (a molecular
  swap), which the scorer counts as a POSITIVE
  (`MOLECULAR_SWAP_TYPES = {proteomics, rnaseq}`). No `"clinical"` swaps were
  injected — those are out of scope for the distance detector and would be
  excluded anyway.
- **Modality alignment.** COSMO `proteome.tsv` and `rnaseq.tsv` are assumed to
  share the same sample-ID namespace and to be originally correctly aligned —
  verified: 100% sample-ID overlap per cohort, identical header ordering. So a
  sample is "correctly labeled" iff its rnaseq label equals its proteomics
  label, and corruption = forcing inequality.
- **Gene namespace.** Both modalities use HGNC gene symbols — verified
  intersections of 5035 / 8366 / 8138 genes for CCRCC / LUAD / Chick.
- **Corruption rate and seed.** `mislabel_fraction = 0.20` mirrors the
  precisionFDA real cohort rate (20/80 mislabeled); `seed = 42` matches the
  detector's internal `RandomState` for determinism.

## Obstacles encountered

- **No keyed simulated cohorts in the public tarball** (see Premise correction).
- **NaNs in real matrices.** Chick proteome is ~21% NaN; CCRCC ~0%; LUAD ~0.6%.
  The matcher `fillna(0.0)`s internally before Spearman, so no crash — but
  Chick's missingness likely drives its lower precision (0.61).
- **Compute scaling.** The detector is O(n^2 * genes) Spearman. Genes were
  deterministically capped to 3000 (`RandomState(42)` subsample) on all three
  scored cohorts (logged: `genes_capped_to=3000`); Chick samples were capped to
  96 (logged: `samples_capped_to=96`).
- **Skipped cohorts (logged, no silent truncation):**
  - `TCGA_BRCA` — uses microarray, not rnaseq (modality mismatch with the
    proteome-vs-rnaseq detector); also large (329 MB + 157 MB).
  - `CCLE` — proteome covers cell lines with heavy missingness; 170 MB rnaseq.
  - `Battle_etal` — ships riboseq, not a clean same-scale rnaseq pairing.

  These three were left out of the scored subset to keep the pairing clean and
  the Spearman tractable.

## Results

### Per-cohort (fixed-0.5)

| Cohort | n samples | molecular swaps | precision | recall | F1 (fixed 0.5) | TP/FP/FN | tuned F1 (ref only) |
|---|---|---|---|---|---|---|---|
| CCRCC | 77 | 15 | 0.8824 | 1.0000 | **0.9375** | 15 / 2 / 0 | 0.9677 @ 0.68 |
| LUAD | 107 | 21 | 0.7778 | 1.0000 | **0.8750** | 21 / 6 / 0 | 0.8750 @ 0.26 |
| Chick_etal | 96 | 19 | 0.6129 | 1.0000 | **0.7600** | 19 / 12 / 0 | 0.7917 @ 0.62 |

### Aggregate

- **Fixed-0.5 micro-F1 = 0.8462** (pooled TP=55 / FP=20 / FN=0; P=0.7333,
  R=1.0000). **Headline.**
- Fixed-0.5 macro-F1 = 0.8575 (unweighted mean of the three per-cohort F1s).
- The **tuned-threshold** column is **reference only** — selecting the threshold
  on the key is exactly gap #2 (tune-on-test) and must never be the headline.

## Caveats (read before quoting any number)

- **Simulated corruption, real matrices.** Independent of CLUE's generator, but
  the corruption is a simulated label-shuffle — not real clinical mislabels.
- **Optimistic regime.** Only rnaseq-modality label swaps were injected — the
  easiest case for a proteomics-vs-rnaseq concordance detector. Recall is a
  perfect 1.0 on all three cohorts (every swapped sample is caught); the only
  errors are false positives from Hungarian-subsampling noise on correctly
  labeled samples (FP = 2 / 6 / 12). So this F1 is an **optimistic bound**.
- **Cap sensitivity.** Results depend on the 3000-gene cap and, for Chick, the
  96-sample cap and its 21% proteome missingness.
- **Single point, not a distribution.** One `mislabel_fraction` (0.20) and one
  seed (42); not a fraction sweep or a multi-seed CI.

**Bottom line to quote:** the detector ingests and runs on real COSMO matrices
(the genuine milestone), and recovers **self-injected** rnaseq swaps at fixed-0.5
micro-F1 = 0.85 (recall 1.0, precision 0.73). Because the corruption was authored
by this experiment, this is a **real-data robustness check, not independent
validation** — it does not close gap #1 and is not a real-world clinical number.
