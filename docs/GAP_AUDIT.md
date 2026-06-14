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
| **1** | **No held-out oracle** — the gate scores the detector against the *same* synthetic ground truth the generator planted; ACHIEVED = self-consistent, not "works on real data". | 🔶 **Blocked on data — characterized on real matrices under an external error MODEL, but no independent validation yet** | **Real-matrix ingestion verified** (genuine milestone): the detector runs **unmodified on real COSMO/CPTAC/TCGA matrices** — real NaN, real gene namespaces, real scales. **Run 2 (current):** characterized under **COSMO's own published error taxonomy** (swap + duplicate + shift) across both molecular modalities, swept over a full grid (3 cohorts x fractions {0.10,0.20,0.30} x seeds {1,2,3} = 27 conditions), fixed-0.5 threshold. **Distribution** fixed-0.5 F1 = **0.805 mean, range [0.559, 0.939]** (per-cohort means CCRCC 0.890 / LUAD 0.813 / Chick 0.712); per-type recall SWAP 1.000, SHIFT 1.000, DUPLICATE 0.939. This supersedes Run 1's optimistic rnaseq-only point (F1 ~0.85, recall 1.0). **Still NOT independent validation and NOT a gap-#1 closure:** the error *MODEL* is externally defined by COSMO, but the *realized key* (which samples, which modality, which seed) is run by **us** — the oracle is self-authored, just following an outside recipe; no claim of independence-from-us or circularity-broken. See [`TRANSFER_VALIDATION_RUN.md`](TRANSFER_VALIDATION_RUN.md). Full closure needs the gated precisionFDA clinical truth. Per-modality clinical key staged (`sum_tab_2.csv`, 20/80) via `scripts/build_real_labels.py`; `[PROPOSED]` `evals/transfer_validation.py` still needs the molecular matrices (`train_pro.tsv`/`train_rna.tsv`), **absent** from the public source. | `c5c034e` |
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

- **Gap #1 (characterized under an external error model on real matrices;
  independent validation still open).** The detector's **ingestion on real
  matrices is verified** — it runs unmodified on real COSMO (Zhang-lab) CPTAC/TCGA
  multi-omics matrices (real NaN, real gene namespaces). **Run 2** then
  characterized it under **COSMO's own published error taxonomy** (swap +
  duplicate + shift, mixed across proteomics and rnaseq), swept over a full
  documented grid (3 cohorts x fractions {0.10, 0.20, 0.30} x seeds {1, 2, 3} = 27
  conditions) at a **fixed 0.5** threshold. The result is reported as a
  **distribution**: fixed-0.5 F1 = **0.805 mean, range [0.559, 0.939]**
  (per-cohort means CCRCC 0.890 / LUAD 0.813 / Chick 0.712); per-error-type recall
  SWAP 1.000, SHIFT 1.000, DUPLICATE 0.939 — see
  [`TRANSFER_VALIDATION_RUN.md`](TRANSFER_VALIDATION_RUN.md). Run 2 supersedes
  Run 1's optimistic single-type point (rnaseq-only label shuffle, F1 ~0.85,
  recall 1.0) with a realistic multi-error-type sweep. **This does not close
  gap #1 and is not independent validation:** COSMO's error *MODEL* is externally
  defined, but the *realized key* (which samples are corrupted, in which modality,
  under which seed) is run by **us** — so the oracle is still self-authored, just
  following an outside-defined recipe. No claim of independence-from-us or
  circularity-broken is made. The public COSMO tarball ships **base matrices, no
  keys** — the premise that it held keyed simulated cohorts was wrong. The only
  genuine closure is the **gated precisionFDA clinical held-out partition** (real
  mislabel truth). The per-modality clinical key is **staged**
  (`sum_tab_2.csv`, 20/80) via `scripts/build_real_labels.py`; the remaining
  blocker is the **molecular feature matrices** (`train_pro.tsv` /
  `train_rna.tsv`) — drop them into `data/raw/` and
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
