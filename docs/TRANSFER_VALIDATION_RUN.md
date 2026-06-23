# Transfer-validation runs — CLUE detector on real multi-omics matrices

This file records **two** distinct real-data runs, which must never be conflated:

- **Run 3 — independent validation (precisionFDA train oracle).** Real precisionFDA
  training matrices scored against the **challenge organizers'** mislabel key. The
  key is authored by neither us nor the generator, so this is **genuine independent
  validation** — it **closes gap #1 for the train partition** at **F1 0.914**.
  Documented immediately below.
- **Run 2 — real-matrix robustness (COSMO, self-injected key).** Real COSMO matrices
  with corruption *we* injected following COSMO's published error taxonomy. The
  features are real but the realized key is ours, so it is a **robustness
  characterization, NOT validation** (fixed-0.5 F1 0.805). Recorded further down,
  unchanged.

---

## Run 3 — independent validation: precisionFDA train oracle (gap #1 train-partition CLOSED)

**Headline:** at the detector's **fixed default 0.5** threshold, `transfer_validation`
scores the real precisionFDA sub-challenge-2 **training** cohort at
**fixed-0.5 F1 = 0.9143** (precision 0.8421, recall 1.0000; TP 16 / FP 3 / FN 0).
This is the first number that is independent of *us*, not just of the generator —
so it genuinely **closes gap #1 for the train partition**.

**Why this is independent (unlike Run 2).** The answer key is the challenge
organizers' own `sum_tab_2.csv` (converted to `data/raw/train_mislabels.json` by
`scripts/build_real_labels.py`: 20 mislabeled of 80 = `{proteomics 8, rnaseq 8,
clinical 4}`). We did not choose which samples are corrupted, in which modality, or
under which seed — the organizers did. The decision threshold was held at the
detector default 0.5 and **not** selected against the key (no tune-on-test, gap #2).
Features are real precisionFDA/CPTAC matrices. Key external + features real +
threshold not fit ⇒ genuine independent validation.

**Data provenance.** `train_pro.tsv` (4119 genes × 80 samples) and `train_rna.tsv`
(17448 × 80), genes-as-rows with `Training_1..Training_80` headers, were downloaded
from the public participant mirror
[`ACHG2018/fda-mislabeling-challenge`](https://github.com/ACHG2018/fda-mislabeling-challenge)
(`challenge_data/`) into gitignored `data/raw/`. That repo's `sum_tab_2.csv` matches
the already-staged `train_mislabels.json` (e.g. Training_2→proteomics,
Training_6→rnaseq), corroborating that the matrices are the matching official
training set. **Caveat:** this is a participant mirror, not the official precisionFDA
portal — a spot-check of a few cells against the official Synapse/precisionFDA
download is recommended as belt-and-suspenders.

**Independent recomputation (not self-report).** Separately from the eval wrapper,
the cross-omics detector was re-run directly (`detect_molecular_mismatches`,
`distance_method='expression_rank'`) and the confusion matrix rebuilt from scratch
against the organizer key: molecular positives = 16 (clinical-only excluded),
flagged = 19, **TP = 16, FP = 3 (`Training_1`, `Training_18`, `Training_19`),
FN = 0** ⇒ precision 0.8421, recall 1.0000, **F1 0.9143** — identical to the
wrapper to 1e-9.

**Scope and honest limits.**
- **Train partition, not blind test.** The challenge *released* train labels, so
  this validates the detector independently of the generator, but it is **not** a
  blind-test result. The actual blind test set (`test_pro.tsv` / `test_rna.tsv`,
  already on disk) has **withheld** labels and remains unscoreable — that blind
  oracle is the remaining open piece of gap #1.
- **Molecular swaps only.** 16 of the 20 mislabels are molecular (proteomics/rnaseq);
  the 4 clinical-only swaps (`Training_13/39/47/68`) are out of scope for a
  cross-omics *distance* detector and are excluded, not missed.
- **Reproduce:** place `train_pro.tsv`/`train_rna.tsv` in `data/raw/`, then
  `python -c "from evals.transfer_validation import TransferValidationEval as T;
  print(T().evaluate('train'))"` → `applicable=True, data_source=real, score=0.9143`.

---

## Run 2 — real-matrix robustness (COSMO, self-injected key)

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

---

# Run 2 - COSMO published error taxonomy (swap/duplicate/shift)

**Run 2 supersedes Run 1's optimism.** Run 1 injected a single, easy error type
(rnaseq-only label swaps) at one fraction (0.20) and one seed (42), hitting
recall 1.0 / F1 ~0.85 — an optimistic point estimate. Run 2 instead mixes the
**three error types from COSMO's own published error taxonomy**
(swap + duplicate + shift), across **both** molecular modalities
(proteomics + rnaseq), and sweeps a documented grid of fractions and seeds to
report a **distribution**, not a cherry-picked point. It is materially harder and
more honest.

**It is still NOT independent validation and still does NOT close gap #1.** The
error *MODEL* (the swap/duplicate/shift taxonomy) is externally defined by COSMO,
but the *realized key* — which specific samples get corrupted, in which modality,
under which seed — is run by **us**. So the oracle is still self-authored (now
following an outside-defined recipe). The only genuine closure remains the gated
precisionFDA clinical key (real mislabel truth). No claim of
independence-from-us or circularity-broken is made.

## Honest label (verbatim)

> published-protocol-simulated F1 on real COSMO matrices -- COSMO's error MODEL
> is externally defined, but the realized key is run by us, so this is a
> robustness characterization, NOT independent validation and NOT a gap-#1
> closure (the only closure is the gated precisionFDA clinical key). No claim of
> independence-from-us or circularity-broken is made.

## COSMO published error taxonomy (externally defined, not ours)

- **SWAP** — two samples exchange one modality's profile (A's rnaseq becomes B's
  and vice versa).
- **DUPLICATE** — one sample's modality profile overwrites another's (a profile
  appears twice; the victim's true profile is lost).
- **SHIFT** — a run of >=3 consecutive samples' modality labels shift by one
  (A<-B, B<-C, C<-A within the run).

Applied to the molecular modalities (proteomics and/or rnaseq); each affected
sample is recorded with molecular type in `{proteomics, rnaseq}` so it counts as
a POSITIVE for `score_molecular_detection`.

## Grid run (no truncation)

**FULL documented grid, no silent truncation:** 3 cohorts {CCRCC, LUAD,
Chick_etal} x 3 fractions {0.10, 0.20, 0.30} x 3 seeds {1, 2, 3} = **27
conditions**. Every condition mixed all three COSMO error types
(swap + duplicate + shift) in roughly equal affected-sample share across the
molecular modalities (proteomics/rnaseq chosen per-event by `RandomState(seed)`).
Detector run unchanged:
`evals.mislabel_detection.mismatch_frequencies(cohort, distance_method="expression_rank")`
-> flag at **FIXED 0.5** -> `score_molecular_detection`. Wall time ~2s (CCRCC, 77
samples), ~5s (LUAD, 107), ~13-33s (Chick, 192); the whole sweep finished in one
run. Script: `data/raw/cosmo/cosmo_robustness_sweep.py` (gitignored,
`git check-ignore` confirmed).

## Grid / cohorts skipped (logged, no silent truncation)

- **No grid points skipped within the run cohorts** — all 27 ran.
- **Cohorts skipped by design** (logged in-script + stdout):
  - `TCGA_BRCA` — microarray expression, not RNA-seq (different namespace/scale).
  - `CCLE` — riboseq pairing, not the clean proteome+rnaseq pairing.
  - `Battle_etal` — heavy missingness / riboseq pairing.
- **Deterministic tractability cap (logged):** `GENE_CAP=1500` top-variance
  proteome genes among the shared-gene set (the O(N^2) Spearman detector is the
  bottleneck). Shared-gene pools before cap: 5035 (CCRCC), 8366 (LUAD), 8138
  (Chick). No sample cap was needed.

## Results — per-condition (fixed 0.5)

| Cohort | fraction | seed | n mislabeled | precision | recall | F1 |
|---|---|---|---|---|---|---|
| CCRCC | 0.10 | 1 | 8 | 0.8000 | 1.0000 | 0.8889 |
| CCRCC | 0.10 | 2 | 8 | 0.7000 | 0.8750 | 0.7778 |
| CCRCC | 0.10 | 3 | 8 | 0.7273 | 1.0000 | 0.8421 |
| CCRCC | 0.20 | 1 | 15 | 0.8824 | 1.0000 | 0.9375 |
| CCRCC | 0.20 | 2 | 15 | 0.8125 | 0.8667 | 0.8387 |
| CCRCC | 0.20 | 3 | 15 | 0.8333 | 1.0000 | 0.9091 |
| CCRCC | 0.30 | 1 | 23 | 0.8846 | 1.0000 | 0.9388 |
| CCRCC | 0.30 | 2 | 23 | 0.9167 | 0.9565 | 0.9362 |
| CCRCC | 0.30 | 3 | 23 | 0.8846 | 1.0000 | 0.9388 |
| LUAD | 0.10 | 1 | 11 | 0.6111 | 1.0000 | 0.7586 |
| LUAD | 0.10 | 2 | 11 | 0.5789 | 1.0000 | 0.7333 |
| LUAD | 0.10 | 3 | 11 | 0.5500 | 1.0000 | 0.7097 |
| LUAD | 0.20 | 1 | 21 | 0.6897 | 0.9524 | 0.8000 |
| LUAD | 0.20 | 2 | 21 | 0.7000 | 1.0000 | 0.8235 |
| LUAD | 0.20 | 3 | 21 | 0.6774 | 1.0000 | 0.8077 |
| LUAD | 0.30 | 1 | 32 | 0.8205 | 1.0000 | 0.9014 |
| LUAD | 0.30 | 2 | 32 | 0.8421 | 1.0000 | 0.9143 |
| LUAD | 0.30 | 3 | 32 | 0.7619 | 1.0000 | 0.8649 |
| Chick_etal | 0.10 | 1 | 19 | 0.4091 | 0.9474 | 0.5714 |
| Chick_etal | 0.10 | 2 | 19 | 0.3878 | 1.0000 | 0.5588 |
| Chick_etal | 0.10 | 3 | 19 | 0.3958 | 1.0000 | 0.5672 |
| Chick_etal | 0.20 | 1 | 38 | 0.5938 | 1.0000 | 0.7451 |
| Chick_etal | 0.20 | 2 | 38 | 0.5672 | 1.0000 | 0.7238 |
| Chick_etal | 0.20 | 3 | 38 | 0.6129 | 1.0000 | 0.7600 |
| Chick_etal | 0.30 | 1 | 58 | 0.7342 | 1.0000 | 0.8467 |
| Chick_etal | 0.30 | 2 | 58 | 0.6988 | 1.0000 | 0.8227 |
| Chick_etal | 0.30 | 3 | 58 | 0.6905 | 1.0000 | 0.8169 |

## Results — distribution (headline)

Fixed-0.5 F1 as a **DISTRIBUTION** over all 27 grid conditions (each condition =
one mix of swap+duplicate+shift):

- **mean F1 = 0.805, range [0.559, 0.939].** Aggregation = unweighted mean of the
  27 per-condition F1 values (each F1 itself computed from that condition's
  TP/FP/FN, not a micro-average of pooled counts).
- **Per-cohort means:** CCRCC 0.890 [0.778, 0.939]; LUAD 0.813 [0.710, 0.914];
  Chick_etal 0.712 [0.559, 0.847].
- **Strong fraction trend within every cohort** (F1 rises with corruption rate):
  the fixed real-data false-positive floor is a larger *share* of flags when
  fewer samples are truly mislabeled.
- Recall stays near 1.0; **precision** is dragged down by genuine COSMO data
  mismatches (the real-data FP floor), which is what makes this materially harder
  and more honest than Run 1's recall-1.0 / F1-~1.0 rnaseq-only label-shuffle.

Independently recomputed (this write-up): the 27 per-condition F1 values
re-aggregate to mean **0.8050**, min **0.5588**, max **0.9388**; per-cohort means
CCRCC **0.8898**, LUAD **0.8126**, Chick **0.7125** — byte-consistent with the
script's HEADLINE_JSON. Spot-checked per-condition F1 from raw P/R (e.g. CCRCC
0.10/s2 -> 0.7778, Chick 0.10/s1 -> 0.5714, LUAD 0.30/s3 -> 0.8649) all reconcile.

## Per-error-type detection (recall only, pooled across all 27 conditions)

Each injected positive is tagged with its source error type, then checked for
detection (flag > 0.5):

| Error type | detected / injected | recall |
|---|---|---|
| SWAP | 198 / 198 | 1.000 |
| SHIFT | 378 / 378 | 1.000 |
| DUPLICATE | 93 / 99 | 0.939 (6 victims missed) |

**Interpretation.** Swaps and shifts break *both* ends of the cross-omics
correspondence cleanly, so the Hungarian assignment surfaces them every time. The
6 duplicate misses are *victims* whose surviving modality still rank-correlates
well enough with the overwriting donor's profile that `mismatch_frequency` stayed
<= 0.5. These are **recall only** — false positives (the precision drag) come from
the real-data FP floor and are not attributable to any injected type, so the
headline F1 is lower than any single type's recall.

## Independent recomputation (verification, not self-report)

Two independent layers:

1. **In-script.** Alongside `score_molecular_detection`'s return, `recompute_prf()`
   rebuilds positives from the realized key, intersects with the raw flagged set
   (freq > 0.5) and shared samples, and computes TP/FP/FN -> P/R/F1 from scratch.
   A hard assert `abs(scorer_f1 - raw_f1) < 1e-9` ran every condition and **never
   tripped** — scorer and raw agree exactly. The per-condition rows above are the
   raw-recomputed numbers, not the scorer's.
2. **Out-of-script.** The 27 per-row F1 values were re-aggregated in a separate
   Python process from the emitted `ROWS_JSON` -> mean 0.8050, min 0.5588, max
   0.9388, byte-identical to the script's `HEADLINE_JSON`.

Clean-baseline (uninjected) flag counts were also printed and explain the FP
floor: **3/77 CCRCC, 8/107 LUAD, 31/192 Chick** — Chick's high baseline-FP rate
is why its precision (and thus F1) is the lowest of the three.

## Obstacles encountered

1. The Bash tool could not write the ~230-line script via a single heredoc
   (repeated "unexpected EOF matching quote" even with a quoted delimiter and
   after stripping single quotes); resolved by appending the source in five
   chunked heredocs to `/tmp` then copying into the repo, confirmed with
   `ast.parse` SYNTAX OK.
2. Chick_etal files are named `Chick_proteome.tsv` / `Chick_rnaseq.tsv` /
   `Chick_cli.tsv` (not `Chick_etal_*`).
3. Initial worry about a trailing-tab phantom sample column was unfounded — the
   pandas Unnamed/empty filter is in place but CCRCC genuinely has 77 samples.
4. Duplicate gene-symbol rows exist in the COSMO matrices; collapsed
   deterministically with `keep="first"`.
5. No project validator gate exists for this characterization task — it reuses
   the detector contract unchanged, so the "gate" here is the in-script
   scorer-vs-raw assert (passed on all 27) plus the external re-aggregation.

## Bottom line to quote (Run 2)

The detector, run unchanged at a **fixed 0.5** threshold against COSMO's
**published** swap/duplicate/shift error taxonomy on **real** COSMO matrices,
characterizes at fixed-0.5 F1 = **0.805 mean, range [0.559, 0.939]** over a full
3x3x3 grid (mean per cohort CCRCC 0.890 / LUAD 0.813 / Chick 0.712). Per-type
recall: SWAP 1.000, SHIFT 1.000, DUPLICATE 0.939. This is harder and more honest
than Run 1, but the realized key is still ours: it is a **robustness
characterization, NOT independent validation and NOT a gap-#1 closure** — the
only closure is the gated precisionFDA clinical key.
