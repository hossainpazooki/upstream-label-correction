# Technical Writeup: CLUE — Closed-Loop Upstream Error-correction

> **Current as of the polyglot split.** This writeup describes the system as it
> stands: a Python ML core, a Go `intent-controller`, a FastAPI `ml_service`
> seam, and the CLUE closed loop. It supersedes the earlier
> Temporal/GCP-Workflows/MCP-centric draft. For the canonical overview see
> [`README.md`](../README.md); for the integrity/honesty record see
> [`GAP_AUDIT.md`](GAP_AUDIT.md).

## Problem statement

In multi-omics precision medicine, the most damaging errors are **upstream**: a
patient's proteomics, RNA-Seq, or clinical record is swapped with another's
before any model runs. The NCI-CPTAC precisionFDA Multi-omics Sample Mislabeling
Correction Challenge formalized this as a computational task over ~80 tumor
samples with paired proteomics (~7K genes) and RNA-Seq (~15K genes).

The problem this repo attacks is not just *detecting* mislabels — it is
**measuring a detector where it matters**. The challenge test set has hidden
labels, a single fixed (unknown) corruption rate, and stochastic CV evaluation.
You cannot compute precision/recall against ground truth you do not have, and you
cannot ask "does the detector hold at 2%? 15%? 30%?" CLUE's answer is to
**manufacture fidelity-verified ground truth** and treat synthetic cohorts as a
*measurement instrument* — never as the deliverable.

## The closed loop

CLUE runs **generate → verify fidelity → measure → improve → regenerate**:

1. **Generate** (`core/synthetic.py` → `SyntheticCohortGenerator`) — a complete
   multi-omics cohort (clinical, proteomics, RNA-Seq) whose every defect is
   recorded as ground truth: which samples were swapped, the swap pairs, the
   mislabel type per sample, the MSI-H set, and the gender map. The corruption
   rate (`mislabel_fraction`), cohort size, feature dimension, class balance, and
   seed are all dials real data does not offer.
2. **Verify fidelity** (`evals/fidelity_gate.py` → `evaluate_dual`) — confirm the
   cohort is *detectable-by-construction* under **two mechanically independent**
   scorers (rank-correlation distance `1−|spearman|` **and** an MSE-residual
   linear model), AND-gated. This is construction-validity on synthetic data; it
   does **not** establish real-data transfer (see "Honesty boundary" below).
3. **Measure** (`evals/mislabel_detection.py` → `MislabelDetectionEval`) — run
   the cross-omics detector, score its flags against the planted swap pairs as
   precision/recall/F1, and sweep the corruption rate.
4. **Improve / regenerate** (`clue/loop.py` → `CLUELoop`) — tune the detector
   against measured feedback, then raise the corruption rate and regenerate a
   harder cohort, until the tuned detector can no longer clear the target F1.
   That last cleared rate is the detector's **operating frontier**.

`scripts/demo.py` drives this loop end to end and prints the rate→F1 table plus
the frontier — every number labeled as synthetic measurement, not real-world
performance.

## The COSMO-inspired detector

The detector is a four-stage pipeline inspired by **COSMO** (Cross-Omics Sample
Matching), the post-challenge methodology from the top-3 teams. This methodology
is unchanged from the original design and remains accurate:

**Stage 1 — Imputation.** Missing values split into MNAR (below-detection-limit)
and MAR (batch effects). The imputer classifies each missing value, applying
minimum-value imputation for MNAR and NMF-based completion (automatic rank
selection) for MAR, with gender-stratified handling of Y-chromosome genes.

**Stage 2 — Cross-omics matching** (`core/cross_omics_matcher.py`). Proteomics
and RNA-Seq samples are aligned via Spearman correlation across shared genes,
producing a distance matrix solved by the Hungarian algorithm over 100 subsampled
iterations. Samples with `mismatch_frequency > 0.5` are flagged. Model-free;
catches proteomics↔RNA-Seq discordance.

**Stage 3 — Classification** (`core/classifier.py`). An ensemble of four
classifiers across two phenotype strategies (gender, MSI) is stacked into a
meta-learner; samples whose molecular phenotype contradicts their annotation are
flagged. The joint phenotype strategy (4-class gender × MSI) captures interaction
effects a separate-target classifier misses.

**Stage 4 — Dual validation.** The two independent flag sources are cross-checked:
**HIGH** (both agree) / **REVIEW** (one) / **PASS** (neither). Two-path
concordance is what makes a mismatch call trustworthy enough to act on, and it
catches mislabels that affect only one modality.

## The agentic lifecycle (Go `intent-controller`)

The same observe → decide → act → verify discipline runs at the platform level as
an **intent lifecycle** (inspired by intent-based networking, IETF RFC 9315). The
lifecycle now lives **solely in the Go service** (`intent-controller/`); the
legacy Python `intents/`/`workflows/` packages are **decommissioned** after the
Go service reached parity. States: DECLARED → RESOLVING → ACTIVE → VERIFYING →
ACHIEVED, with BLOCKED/FAILED edges.

- The Go controller is the **single authority for `ACHIEVED`**: `verify()` runs
  each `IntentSpec` eval criterion via the ML service and gates on the aggregate.
- It runs **multiple replicas safely** via a cross-replica claim/lease (Postgres
  `FOR UPDATE SKIP LOCKED`).
- VERIFY is wired through the ML service: the controller's `RunEval` posts to
  `ml_service`'s `/ml/evaluate`, which routes `eval_name` to the matching runner.
  For the mislabel gate, integrity-critical cohort parameters (corruption rate,
  size, and a seed derived from the **server-assigned** `intent_id`) are **pinned
  server-side**, so the gate cohort cannot be seed-shopped by the caller.

## Integrity model and the honesty boundary

The verification gate has been hardened across an 8-finding audit read through a
"correct-shaped-lies" red-team lens (see [`GAP_AUDIT.md`](GAP_AUDIT.md)). It is
now **server-authoritative**: an authenticated control plane (`X-Service-Token`),
server-pinned cohort params, a **dual decorrelated** fidelity detector, and a
Go-side consistency check that won't trust a self-inconsistent `passed`.

**The load-bearing caveat (gap #1).** The fidelity gate validates synthetic
*self-consistency*, **not** real-world performance. Both fidelity scorers read the
*same* generator's matrices, so this is a decorrelated second scorer on synthetic
data — **not** an independent held-out oracle. Corruption the generator never
planted is invisible to both. Clearing the gate does **not** establish real-data
performance. The only true fix is validation against the real precisionFDA
held-out partition with curated clinical labels, which are **not** in this repo
(`data/raw` is gitignored; the challenge withheld test labels).
`evals/transfer_validation.py` is the `[PROPOSED]` seam for that — it skips
gracefully until real data lands and never reports a synthetic number as
real-data performance.

## Real-COSMO robustness run (what it is, and what it is not)

The detector has been run **unmodified on real CPTAC/TCGA matrices** from the
public COSMO datasets release (Bing Zhang lab) — real NaN, real gene namespaces,
real scales. Against corruption following **COSMO's own published error taxonomy**
(swap / duplicate / shift) across a documented 3×3×3 grid (3 cohorts × 3
fractions × 3 seeds = 27 conditions), the detector characterizes at a **fixed-0.5
F1 of 0.805, range [0.559, 0.939]** (per-cohort means CCRCC 0.890 / LUAD 0.813 /
Chick 0.712; per-type recall: swap 1.000, shift 1.000, duplicate 0.939). Full
record: [`TRANSFER_VALIDATION_RUN.md`](TRANSFER_VALIDATION_RUN.md).

**This is a robustness characterization, NOT independent validation, and it does
NOT close gap #1.** The error *model* (the swap/duplicate/shift taxonomy) is
externally defined by COSMO, but the *realized key* — which specific samples are
corrupted, in which modality, under which seed — is authored by **us**. So the
oracle is self-made (now following an outside-defined recipe), and the features
are real but the corruption is simulated. The genuine milestone is **real-matrix
ingestion and robustness**; the genuine closure remains the gated precisionFDA
clinical key. No claim of independence-from-us or circularity-broken is made.

## Determinism

Determinism is a hard invariant: all randomness flows through a seeded `PCG64`
stream (generator) or `RandomState(42)` (detector). Same seed → byte-identical
cohort → exact regression tests. Global `np.random` use is prohibited because it
breaks byte-identical reproduction.

## Lessons learned

1. **Missing-data classification matters more than imputation method.** Choosing
   MNAR vs MAR had a larger downstream impact than the specific algorithm.
   Treating below-detection-limit zeros as random missingness introduced
   systematic feature-selection bias.
2. **Cross-omics concordance is a powerful validation signal.** When proteomics
   and RNA-Seq independently agree, confidence is substantially higher than
   either alone — especially valuable when a mislabel affects only one modality.
3. **Joint phenotype improves over separate prediction.** The 4-class joint label
   (gender × MSI) captures interaction effects separate binary classifiers miss;
   the meta-learner weights joint predictions more heavily near decision
   boundaries.
4. **Synthetic generators need realistic structure, not random noise.** Uniform
   random noise produced unrealistically high accuracy; structured signal layers
   (pathway fold-changes, gender effects, batch-dropout missingness) produced
   datasets that exercised the edge cases the pipeline must handle.
5. **A measurement instrument must be kept honest by construction.** The whole
   point of CLUE is measuring a detector against ground truth, so every empirical
   number is recomputed from the raw source and the synthetic-vs-real boundary is
   never blurred. The gap audit and the explicit "this is not validation" labels
   on the real-COSMO run are the discipline that keeps the instrument trustworthy.

## Future directions

- **Close gap #1** when the real precisionFDA held-out partition + curated labels
  are available: activate `evals/transfer_validation.py` as the independent
  oracle.
- **Hard-example reweighting** in the improve step — a lever the loop structure
  admits but does not yet drive.
- **Multi-center validation**: extend the generator with site-specific batch
  effects to test generalization.
