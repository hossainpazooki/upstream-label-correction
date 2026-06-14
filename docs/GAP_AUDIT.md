# Gap audit — CLUE detection gate

A risk assessment of CLUE's verification gate, read through the
[`correct-shaped-lies`](../../correct-shaped-lies) red-team lens (a producer that
clears every evaluator yet is dishonest), plus the disposition of each finding.

**One-line headline.** The gate's *integrity* and *honesty* are now hardened —
authenticated, server-pinned cohorts, a decorrelated dual detector, a result
consistency check, no-op gates removed, and optimistic claims rewritten. The
deepest *validity* limit — that scoring a synthetic detector against the
generator's own planted ground truth is **not** real-world validation (gap #1) —
is a property of not having real held-out data, not a code defect, and is now
stated plainly everywhere rather than implied.

## Findings and disposition

| # | Risk (CSL lens) | Status | Mechanism / where | Commit |
|---|---|---|---|---|
| **1** | **No held-out oracle** — the gate scores the detector against the *same* synthetic ground truth the generator planted; ACHIEVED = self-consistent, not "works on real data". | 🔶 **Blocked on data — one real milestone, no independent validation yet** | **Real-matrix ingestion verified** (genuine milestone): the detector built on synthetic cohorts runs **unmodified on real COSMO/CPTAC/TCGA matrices** — real NaN, real gene namespaces, real scales — and produces sensible flags. A **self-injected** robustness check (we shuffled rnaseq labels ourselves, `RandomState(42)`, fixed-0.5 threshold) gave micro-F1 **0.85** (recall 1.0 — rnaseq-only ⇒ optimistic). **This is NOT independent validation:** *we* authored the corruption oracle, so gap #1's circularity is **relocated onto real features, not broken**. See [`TRANSFER_VALIDATION_RUN.md`](TRANSFER_VALIDATION_RUN.md). Full closure needs an **outside-authored** key — COSMO's own simulation protocol, or the gated precisionFDA clinical truth. Per-modality clinical key staged (`sum_tab_2.csv`, 20/80) via `scripts/build_real_labels.py`; `[PROPOSED]` `evals/transfer_validation.py` still needs the molecular matrices (`train_pro.tsv`/`train_rna.tsv`), **absent** from the public source. | `c5c034e` |
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

- **Gap #1 (one real milestone; independent validation still open).** The
  detector's **ingestion on real matrices is verified** — it runs unmodified on
  real COSMO (Zhang-lab) CPTAC/TCGA multi-omics matrices (real NaN, real gene
  namespaces). A **self-injected** robustness check (we shuffled rnaseq labels
  ourselves at a fixed 0.5 threshold) gave micro-F1 **0.85** (recall 1.0,
  precision 0.73) — see [`TRANSFER_VALIDATION_RUN.md`](TRANSFER_VALIDATION_RUN.md).
  **This does not close gap #1 and is not independent validation:** *we* authored
  the corruption, so the oracle is still self-made (just on real features instead
  of synthetic ones), and rnaseq-only injection makes 0.85 an optimistic bound,
  not a performance estimate. The public COSMO tarball ships **base matrices, no
  keys** — the premise that it held keyed simulated cohorts was wrong. Genuinely
  independent options, in order of strength: (a) the gated precisionFDA clinical
  held-out partition (real mislabel truth); (b) **COSMO's own** error-simulation
  protocol (an outside-authored key, but still simulated). The per-modality
  clinical key is **staged** (`sum_tab_2.csv`, 20/80) via
  `scripts/build_real_labels.py`; the remaining blocker is the **molecular feature
  matrices** (`train_pro.tsv` / `train_rna.tsv`) — drop them into `data/raw/` and
  `evals/transfer_validation.py` activates with no code change.
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
synthetic gate validates real-world detector performance — that is gap #1, and
the repo now says so wherever the gate is described.
