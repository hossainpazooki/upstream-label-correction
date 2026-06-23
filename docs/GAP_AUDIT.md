# Gap audit — CLUE detection gate

A risk assessment of CLUE's verification gate, read through the
[`correct-shaped-lies`](../../correct-shaped-lies) red-team lens (a producer that
clears every evaluator yet is dishonest), plus the disposition of each finding.

**One-line headline.** The gate's *integrity* and *honesty* are now hardened —
authenticated, server-pinned cohorts, a decorrelated dual detector, a result
consistency check, no-op gates removed, and optimistic claims rewritten. The
deepest *validity* limit — that scoring a synthetic detector against the
generator's own planted ground truth is **not** real-world validation (gap #1) —
is now **closed for the train partition**: the real precisionFDA training matrices
landed, and `transfer_validation('train')` scores the detector at **F1 0.914**
against the challenge organizers' own mislabel key (independent of both us and the
generator). What remains open is the *blind* precisionFDA test oracle, whose labels
the challenge withheld. The synthetic-vs-real and validated-vs-robustness
boundaries are stated plainly everywhere rather than implied.

## Findings and disposition

| # | Risk (CSL lens) | Status | Mechanism / where | Commit |
|---|---|---|---|---|
| **1** | **No held-out oracle** — the gate scores the detector against the *same* synthetic ground truth the generator planted; ACHIEVED = self-consistent, not "works on real data". | ✅ **Train oracle CLOSED** (real precisionFDA matrices vs the organizers' key, F1 0.914) · 🔶 **blind test oracle still gated** | **Train-partition closure (current):** the real precisionFDA sub-challenge-2 training matrices (`train_pro.tsv` 4119×80, `train_rna.tsv` 17448×80) were obtained from the public participant mirror [`ACHG2018/fda-mislabeling-challenge`](https://github.com/ACHG2018/fda-mislabeling-challenge) and placed in gitignored `data/raw/`. `transfer_validation('train')` returns `applicable=True, data_source=real`: **fixed-0.5 F1 = 0.914** (precision 0.842, recall 1.000; TP 16 / FP 3 [`Training_1/18/19`] / FN 0), independently recomputed from the raw flagged set vs the key. The key (`sum_tab_2.csv` → `train_mislabels.json`, 20/80 = `{pro 8, rna 8, clin 4}`) is authored by the **challenge organizers** — independent of both us and the generator — and the threshold was **not** fit to it, so this is genuine independent validation, not the COSMO self-injected run's relocated circularity. **Scope:** train partition (challenge released train labels) — not a *blind*-test number; the blind test set (`test_pro`/`test_rna`, present locally) has **withheld** labels and stays unscoreable. Molecular swaps only (16); the 4 clinical-only swaps are out of a cross-omics detector's scope. **Provenance caveat:** matrices came from a participant mirror, not the official precisionFDA portal — sample-namespace + key alignment corroborate; an official-source cross-check is recommended. **Separately**, the COSMO robustness run remains a *robustness characterization under an external error MODEL* (fixed-0.5 F1 0.805, range [0.559, 0.939] over 27 conditions) — not independent validation; see [`TRANSFER_VALIDATION_RUN.md`](TRANSFER_VALIDATION_RUN.md). | `c5c034e`, *(pending commit)* |
| **2** | **Tune-on-test** — the default gate selected the decision threshold to maximize F1 on the *same* cohort it then graded. | ✅ **Honest framing; substance folded into #1** | Gate reports `in_sample_f1` vs `held_out_f1` + delta; `clue.loop.select_threshold_holdout` added. Skeptic showed a disjoint-seed sibling is still structurally identical, so a true held-out fix needs #1's oracle. | `201f55d` |
| **3** | **Shared scorer** — `fidelity_gate` reused the *exact* rank detector that `mislabel_detection` grades, so the construction-validity check shared the detector's blind spot. | ✅ **Fixed** | `FidelityGateEval.evaluate_dual`: AND-gate over two mechanically distinct detectors (rank-correlation **and** MSE-residual AUROC), `detectors_disagree` flag, null-control test. Decorrelated second scorer — **not** an external oracle. | `c5c034e` |
| **4** | **Evals gate nothing / training deploys ungated** — `mislabel_detection`/`fidelity_gate` were in no `IntentSpec`; `training` reached ACHIEVED on mere completion, then ran `pulumi up`. | ✅ **Fixed** | `validation` gates on fidelity + mislabel; `training` gates its deploy on the SLM-probing evals; `verify()` refactored (`achieve()`) so `TriggersDeploy` fires only after a *gated* ACHIEVED. | `ecb490b` |
| **5** | **Seed-shopping** — caller-supplied `seed`/`mislabel_fraction`/sizes chose the cohort the gate judged. | ✅ **Fixed** | Integrity-critical cohort params pinned server-side; seed derived from the server-assigned `intent_id` (SHA-256). Caller params ignored for the gate. | `37fbd34` |
| **6** | **Go trusts the ML boolean** — the controller aggregated `result["passed"]` without corroboration. | ✅ **Fixed (defense-in-depth)** | `checkEvalConsistency` cross-checks `passed` against the same response's `score`/`threshold` and fails closed on malformed, self-inconsistent (`passed=true` yet `score<threshold`), or gate-weakening (returned threshold below requested) results. | `d216384` |
| **7** | **Knife-edge gate** — `test_clue_loop` sat at `target_f1=0.8`, flipping on float/BLAS noise. | ✅ **Fixed** | Cross-omics iteration made deterministic; the live `mislabel_detection` gate sits at 0.70 with wide margin (#5). | `cbcb61f` |
| **8** | **Unauthenticated control plane** — controller API + `ml_service` had no app-layer auth; an anonymous request could reach `pulumi up`. | ✅ **Fixed** | Shared `X-Service-Token` on the controller `/api/v1/*` and every `ml_service` endpoint (health exempt); `ingress=internal` on intent/ml; `REQUIRE_AUTH`+`API_KEYS` close the public web edge. OIDC/IAM left as a documented follow-up on the same seam. | `283f8a8` |

### Bonus findings (surfaced by the adversarial skeptic)

| Finding | Status | Commit |
|---|---|---|
| `benchmark_comparison` was a no-op gate (`threshold=0.0` → passed on any single-gene overlap). | ✅ Fixed: non-trivial Jaccard floor (`DEFAULT_BENCHMARK_JACCARD=0.10`); reports `independent_reference=False`. | `c2013d3` |
| `benchmark_comparison` / `biological_validity` presented as *external* validation, but their reference fixture is byte-identical to the generator's own `core.constants.KNOWN_MSI_PATHWAY_MARKERS`. | ✅ Documented as marker-recovery / self-consistency, not external validation. | `c2013d3`, `c5c034e` |

## What remains

- **Gap #1 — train oracle CLOSED; blind-test oracle still open.** The blocker was
  always data, not code, and the train-partition data has now landed. The real
  precisionFDA sub-challenge-2 training matrices (`train_pro.tsv` /
  `train_rna.tsv`) were obtained from the public participant mirror
  [`ACHG2018/fda-mislabeling-challenge`](https://github.com/ACHG2018/fda-mislabeling-challenge),
  placed in gitignored `data/raw/`, and `transfer_validation('train')` now scores
  the detector against the **challenge organizers'** mislabel key — independent of
  both us and the generator — at a **fixed-0.5 F1 of 0.914** (precision 0.842,
  recall 1.000; TP 16 / FP 3 / FN 0), independently recomputed from the raw flagged
  set. That is genuine independent validation for the train partition. **What is
  still open:** (a) the **blind precisionFDA test oracle** — the challenge withheld
  those labels, so `test_pro`/`test_rna` (present locally) stay unscoreable;
  (b) **clinical-only** swaps (4/20) are out of a cross-omics distance detector's
  scope; (c) a **provenance cross-check** against the official precisionFDA portal
  is recommended, since the matrices came from a participant mirror.
- **Separately — real-matrix robustness (not validation).** The detector also runs
  unmodified on real COSMO (Zhang-lab) CPTAC/TCGA matrices and, under **COSMO's own
  published error taxonomy** (swap + duplicate + shift) swept over a 27-condition
  grid at fixed 0.5, characterizes at fixed-0.5 F1 = **0.805 mean, range
  [0.559, 0.939]**. This adopts an outside-defined error *MODEL* but the *realized
  key* is still ours, so it remains a **robustness characterization, not
  independent validation** — distinct from the organizer-keyed train closure above.
  See [`TRANSFER_VALIDATION_RUN.md`](TRANSFER_VALIDATION_RUN.md).
- **Lower-priority follow-ups:**
  - Promote `EnsembleMismatchClassifier` to a second fidelity detector *family*
    (stronger independence than two distance primitives) — heavier (training/CV
    seeding review). `[PROPOSED]`.
  - Upgrade the gap-#8 shared token to GCP OIDC / `run.invoker` IAM — the
    middleware seam already isolates this swap.
  - Harden the controller's `DATABASE_URL` (plain Cloud Run env) into Secret
    Manager (noted in [`DEPLOY.md`](../DEPLOY.md)).

## What this audit does and does not claim

It claims the gate can no longer be reached anonymously, seed-shopped, silently
weakened, or trusted on an inconsistent self-report, and that its fidelity check
no longer rests on a single detector's blind spot. It does **not** claim the
*synthetic* gate alone validates real-world detector performance — that needed
gap #1's independent oracle. That oracle is now in hand for the **train partition**
(organizer-keyed real matrices, F1 0.914); the **blind** precisionFDA test oracle
remains gated. The repo states which is which wherever the gate is described.
