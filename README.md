# CLUE — Closed-Loop Upstream Error-correction

> **An agentic loop that generates fidelity-verified synthetic multi-omics cohorts to measure — and ultimately improve — label-error detection at corruption rates real data cannot probe.**

Built on the [precisionFDA NCI-CPTAC Multi-omics Sample Mislabeling Correction Challenge](https://www.nature.com/articles/s41591-018-0180-x).

---

## The problem: you can't measure a detector where it matters

In multi-omics precision medicine, the most dangerous errors happen **upstream**, before any model runs: a patient's proteomics, RNA-Seq, or clinical record gets swapped with another's. Mislabeled samples silently corrupt every downstream conclusion — and in the clinic, attribute the wrong data to the wrong patient. The precisionFDA / NCI-CPTAC challenge ([Boja et al., *Nature Medicine* 2018](https://www.nature.com/articles/s41591-018-0180-x)) framed this as a computational task: **detect and correct mislabeled samples** across clinical, proteomics, and RNA-Seq data.

The catch for anyone building a *detector*: **real data can't tell you how good your detector is at the rates you care about.**

- The challenge test set is **~80 samples with unknown, hidden mislabels** — you can't compute precision/recall against ground truth you don't have.
- You can't dial the corruption rate. Does your detector hold at 2%? 15%? 30%? Real cohorts give you one fixed, unknown operating point.
- Cross-validation makes evaluation stochastic, so regressions hide in the noise.

CLUE's answer: **manufacture the ground truth.** Generate synthetic cohorts that carry the same biological signal a real detector relies on, inject known label corruption at a controllable rate and scale, run the detector, and score it against exactly what you planted.

---

## The idea: close the loop

```mermaid
flowchart LR
    G["①  GENERATE\nSynthetic multi-omics cohort\nwith injected label swaps\n(known ground truth)"]
    V["②  VERIFY FIDELITY\nCohort carries the signal\na real detector relies on"]
    M["③  MEASURE\nRun detector → score flags\nvs. planted ground truth\nacross corruption rates"]
    I["④  IMPROVE\nFeed scores back:\nretune / regenerate"]
    G --> V --> M --> I
    I -. "next iteration" .-> G
```

| Stage | What it does | Backed by | Status |
|---|---|---|---|
| ① **Generate** | Synthetic cohorts with planted MSI/gender signal and injected proteomics/RNA-Seq/clinical swaps; emits a ground-truth record of every swap | `core/synthetic.py` → `SyntheticCohortGenerator` | ✅ implemented |
| ② **Verify fidelity** | Confirm the cohort is *detectable-by-construction* — biological signal is recoverable and reproducible, so results transfer to real data | `evals/biological_validity.py`, `evals/reproducibility.py` | 🔶 partial |
| ③ **Measure** | Run the COSMO detector, compare flagged samples to the planted swaps, report precision/recall/F1 swept over corruption rate | `evals/mislabel_detection.py` → `MislabelDetectionEval` (detector: `core/cross_omics_matcher.py`) | ✅ implemented |
| ④ **Improve** | Feed the measured score back: tune the detector and regenerate harder cohorts up to the operating frontier | `clue/loop.py` → `CLUELoop` (eval-level); intent-lifecycle integration ⭕ | ✅ implemented |

> **Honest status.** All four loop stages are **implemented and tested**: generate (`core/synthetic.py`), measure (`evals/mislabel_detection.py`), and improve/regenerate (`clue/loop.py`) — the last tunes the detector against planted ground truth and escalates corruption to the detector's operating frontier. The loop is also wired into the platform **intent lifecycle** — `mislabel_detection` is a registered assurance eval whose VERIFY step tunes the detector and gates on the tuned F1. One honest caveat remains: "improve" tunes the detector's *decision threshold*, not full model retraining yet. See [Implementation status](#implementation-status). This README is explicit about what is wired vs. designed.

---

## ① Generate — synthetic cohorts with known corruption

`SyntheticCohortGenerator` (`core/synthetic.py`) produces a complete multi-omics dataset whose every defect is recorded as ground truth.

```python
from core.synthetic import SyntheticCohortGenerator

gen = SyntheticCohortGenerator(
    n_samples=80,
    n_genes_proteomics=5000,
    n_genes_rnaseq=15000,
    msi_fraction=0.4,
    mislabel_fraction=0.05,   # ← dial the corruption rate
    seed=42,
)
cohort = gen.generate_cohort()
# cohort["clinical"], ["proteomics"], ["rnaseq"], ["ground_truth"]
```

The planted ground truth — the answer key a real test set never gives you:

```python
cohort["ground_truth"] = {
    "mislabeled_samples": [...],          # which samples were swapped
    "mislabel_type":      {sid: "proteomics" | "rnaseq" | "clinical"},
    "swap_pairs":         [(sid_a, sid_b), ...],
    "msi_h_samples":      [...],
    "gender_map":         {sid: "Male" | "Female"},
}
```

**Signal layers** (so the cohort behaves like real data, not noise):

```mermaid
flowchart TD
    BASE["Log-normal base expression"] --> L1["MSI phenotype signal\npathway fold-changes"]
    BASE --> L2["Gender signal\nY-chromosome high / zero"]
    L1 & L2 --> L3["Cross-omics concordance\nshared latent factors"]
    L3 --> L4["Mislabel injection\nproteomics / RNA-Seq / clinical swaps"]
    L4 --> L5["Structured missingness\nMNAR + MAR batch dropout"]
```

**Corruption-rate & scale controls** — the levers real data doesn't have:

| Lever | Parameter | Effect |
|---|---|---|
| Corruption rate | `mislabel_fraction` | Fraction of samples swapped (`max(2, ⌊n·fraction⌋)`, paired) |
| Cohort size | `n_samples` | 20 → 2,000+ |
| Feature dimension | `n_genes_proteomics`, `n_genes_rnaseq` | Stress the high-dimensional / low-N regime |
| Class balance | `msi_fraction` | Match or stress the ~15% MSI-H clinical rate |
| Determinism | `seed` | Same seed → byte-identical cohort → exact regression tests |

**Presets** (as defined in code):

| Preset | Samples | Proteomics genes | RNA-Seq genes | Use |
|---|---|---|---|---|
| `SyntheticCohortGenerator.unit()` | 20 | 100 | 150 | Unit tests (<1s) |
| `SyntheticCohortGenerator.integration()` | 80 | 5,000 | 15,000 | Integration — matches challenge train size |
| `SyntheticCohortGenerator.benchmark()` | 500 | 7,000 | 15,000 | Scale / performance |

---

## ②–③ Verify & Measure — the COSMO detector

The detector is a four-stage pipeline inspired by **COSMO** (Cross-Omics Sample Matching), the post-challenge methodology from the top-3 teams. It produces the flags that stage ③ scores against ground truth.

```mermaid
flowchart LR
    S1["Stage 1 · Impute\nNMF rank selection\nMNAR Y-chr handling"]
    S2["Stage 2 · Match\nSpearman + Hungarian\ndistance matrix"]
    S3["Stage 3 · Predict\n4-method selection\nensemble + meta-learner"]
    S4["Stage 4 · Validate\ndual-path concordance\nHIGH / REVIEW / PASS"]
    S1 --> S2 --> S3 --> S4
```

- **Match** (`core/cross_omics_matcher.py`) — `identify_mismatches()` builds a Spearman distance matrix, solves optimal assignment with the Hungarian algorithm over 100 subsampled iterations, and flags samples whose `mismatch_frequency > 0.5`. Model-free; catches proteomics↔RNA-Seq discordance.
- **Predict** (`core/classifier.py`) — an ensemble of 4 classifiers × 2 phenotype strategies (gender, MSI) stacked into a meta-learner; flags samples whose molecular phenotype contradicts their annotation.
- **Dual-validate** (`core/cross_omics_matcher.py`) — `dual_validate()` cross-checks the two independent flag sources: **HIGH** (both agree) / **REVIEW** (one) / **PASS** (neither). Two-path concordance is what makes a mismatch call trustworthy enough to act on.

**Fidelity verification (②)** keeps the synthetic cohort honest — a detector tuned on signal-free noise wouldn't transfer to real data. Today this is enforced by the biological-validity and reproducibility evals (the planted MSI pathway genes must be recoverable; the same seed must reproduce results). A dedicated "is this corruption detectable-by-construction" gate is part of the closing work.

**Detection measurement (③)** is wired. `MislabelDetectionEval` (`evals/mislabel_detection.py`) runs the cross-omics detector on a generated cohort, scores its flags against the planted `swap_pairs` as precision / recall / F1, and sweeps the corruption rate real data can't provide:

```python
from evals.mislabel_detection import MislabelDetectionEval

# Score detection across corruption rates 10% → 40%
for r in MislabelDetectionEval().sweep([0.10, 0.20, 0.30, 0.40], n_samples=80):
    d = r.details
    print(f"rate={d['mislabel_fraction']:.0%}  P={d['precision']:.2f} R={d['recall']:.2f} F1={d['f1']:.2f}")
```

A clinical-only swap leaves both molecular matrices intact, so it is invisible to the *distance* path — the eval scores it out of scope (and reports it separately) rather than penalising the detector for something that is the classification path's job.

---

## ④ Improve — closing the loop

The loop closes here. `CLUELoop` (`clue/loop.py`) runs **generate → measure → improve → regenerate**, adapting on the measured score:

- **Improve** — `tune_decision_threshold()` selects the detector's decision threshold (on per-sample mismatch frequency) that maximises F1 *against the planted ground truth*. The detector's effective configuration is chosen by measurement, not by hand.
- **Regenerate harder** — when the tuned detector clears the F1 target, the loop raises the corruption rate and generates a fresh, harder cohort — probing regimes real data can't reach — until it finds the detector's **operating frontier**: the hardest rate it still clears.

```python
from clue.loop import CLUELoop

result = CLUELoop(target_f1=0.80, start_fraction=0.05, max_fraction=0.40).run()
for r in result.rounds:
    print(f"rate={r.mislabel_fraction:.0%}  τ*={r.best_threshold}  F1={r.f1:.2f}  pass={r.passed}")
print("operating frontier:", result.frontier_fraction)   # hardest rate the tuned detector cleared
```

Scope of "improve": the lever today is the detector's **decision threshold**, tuned against ground truth. Full model retraining (the classification path) is a deeper lever the loop's structure accommodates but does not yet drive — stated honestly rather than implied.

### The agentic lifecycle

The same observe→decide→act→verify discipline runs at the platform level as an **intent lifecycle** (inspired by intent-based networking, IETF RFC 9315): an agent declares a goal, the platform provisions what it needs, executes, and verifies against evals before declaring success.

```mermaid
flowchart LR
    D["DECLARED\nintent expressed"] --> R["RESOLVING\nprovision infra"]
    R --> A["ACTIVE\nworkflows running"]
    A --> V["VERIFYING\neval assurance"]
    V --> AC["ACHIEVED"]
    R -.->|blocked| B["BLOCKED"] -.->|retry| R
    A -.-> F["FAILED"]
    V -.-> F
```

| Intent | Purpose | Success criteria |
|---|---|---|
| **AnalysisIntent** | Biomarker discovery / sample QC | Biological validity ≥ 60%, reproducibility ≥ 85% |
| **TrainingIntent** | Fine-tune BioMistral / expression encoder | Job completion → auto-deploy |
| **ValidationIntent** | Cross-omics concordance gate | Hallucination detection ≥ 90%, adversarial robustness = 100% |

The lifecycle is implemented twice during an in-flight migration: the Python reference (`intents/`) and the Go service that supersedes it (`intent-controller/`). The loop is wired into VERIFY: `mislabel_detection` is a registered assurance eval (`intents/assurance.py`) that — when an intent lists it in `eval_criteria` — generates a cohort from the intent params, runs the improve step (threshold tuning), and gates the intent on the tuned F1. Porting this runner to the Go `AssuranceLoop` rides along with the migration.

### Skills, tools, evals

| Layer | What |
|---|---|
| **Agent skills** (`agent_skills/`) | biomarker discovery, sample QC, cross-omics integration, literature grounding |
| **MCP tools** (`mcp_server/`) | 11 tools: load/impute/select/classify/match + `express_intent` / `get_intent_status` |
| **Evals** (`evals/`) | mislabel detection (P/R/F1 vs. planted ground truth), biological validity (≥0.60), reproducibility (≥0.85), hallucination detection (≥0.90), adversarial robustness (=1.0), benchmark comparison |

---

## Why synthetic data (and why not *only* synthetic)

| | Real challenge data | CLUE synthetic cohorts |
|---|---|---|
| Mislabel ground truth | Hidden (test set) | Known per-sample |
| Corruption rate | Fixed, unknown | Any rate via `mislabel_fraction` |
| Scale | 80 + 80 samples | 20 → 2,000+ |
| Eval determinism | Stochastic (CV splits) | Byte-identical per seed |

Synthetic data is the **measurement instrument**, not the deliverable. The intended workflow: develop and stress the detector on synthetic cohorts where you can measure it precisely, then validate on the real precisionFDA data as the gold standard, and report both. Real 80-sample data remains the final word on real-world performance.

---

## Implementation status

| Capability | State |
|---|---|
| Synthetic cohort generation + ground truth | ✅ `core/synthetic.py` (tested) |
| Controllable corruption rate / scale / seed | ✅ generator parameters |
| COSMO detector (impute → match → predict → dual-validate) | ✅ `core/` |
| Biological-validity / reproducibility / hallucination / robustness evals | ✅ `evals/` |
| Intent lifecycle (observe-decide-act-verify) | ✅ Python `intents/`; Go `intent-controller/` (migration in progress) |
| Detection scored vs. synthetic ground truth (P/R/F1) across rates | ✅ `evals/mislabel_detection.py` (tested) |
| Closed loop: tune detector + regenerate harder to the operating frontier | ✅ `clue/loop.py` → `CLUELoop` (tested) |
| Loop wired into intent lifecycle (VERIFY gates on tuned detection) | ✅ `intents/assurance.py` (tested; Go port pending) |
| Full model-retrain feedback (vs. threshold tuning) | ⭕ designed — the remaining depth |
| Infrastructure as code | ✅ `infra-ts/` (TypeScript Pulumi); automated deploy currently disabled — see [DEPLOY.md](DEPLOY.md) |

---

## Quick start

**Prerequisites:** Python 3.11+, Docker & Docker Compose (Postgres, Redis).

```bash
git clone https://github.com/hossainpazooki/upstream-label-correction.git
cd upstream-label-correction
pip install -e ".[all]"          # or ".[ml,dev]" for a minimal install
```

Generate a cohort and run the detector — no GCP or external data required:

```python
from core.synthetic import SyntheticCohortGenerator
from core.pipeline import COSMOInspiredPipeline   # see core/pipeline.py

cohort = SyntheticCohortGenerator.integration().generate_cohort()
truth  = cohort["ground_truth"]                   # the planted answer key
# Run the COSMO pipeline over the cohort and compare its flags to `truth`.
```

Services (optional, for the full agentic/API path):

```bash
docker-compose up -d                                              # Postgres, Redis
uvicorn api.main:app --port 8000 --reload                         # REST API
python -m mcp_server.server --transport sse --port 8080          # MCP server
```

Tests:

```bash
pytest                       # all
pytest tests/test_core/test_synthetic.py   # the generator
pytest tests/test_evals/                   # evals
```

---

## Repository layout

```
upstream-label-correction/
├── core/                 # ML engine: synthetic.py (generator), cross_omics_matcher.py,
│                         #   classifier.py, imputation.py, feature_selection.py, pipeline.py
├── evals/                # mislabel detection (vs. ground truth), biological validity,
│                         #   reproducibility, hallucination, adversarial robustness, benchmark
├── clue/                 # closed loop: generate → measure → improve → regenerate (CLUELoop)
├── agent_skills/         # biomarker discovery, sample QC, cross-omics, literature grounding
├── mcp_server/           # MCP tools (genomics + intent lifecycle)
├── intents/              # Python intent lifecycle (being superseded by intent-controller/)
├── intent-controller/    # Go intent + workflow engine (active migration target)
├── web/                  # Next.js dashboard + API routes (TypeScript)
├── dspy_modules/         # DSPy prompt optimization
├── training/             # BioMistral QLoRA fine-tuning, expression encoder (GPU/DDP)
├── infra-ts/             # TypeScript Pulumi infrastructure (GCP)
├── api/  workflows/      # Python FastAPI + legacy orchestration (migrating to Go)
├── tests/                # test suite
└── docs/                 # extended documentation (+ docs/archive/ for retired docs)
```

> Note: the platform is mid-migration from a Python monolith to a polyglot split (Go intent-controller, TypeScript web/infra, Python ML core). Some Python modules (`api/`, `workflows/`, `intents/`) are slated for decommission once their Go/TS replacements reach parity — see [PULUMI_MIGRATION_PLAN.md](PULUMI_MIGRATION_PLAN.md).

---

## Documentation

- [Scientific Methodology](docs/SCIENTIFIC_METHODOLOGY.md) — COSMO pipeline, biomarkers, statistical rationale
- [Synthetic Data Strategy](docs/SYNTHETIC_DATA_STRATEGY.md) — signal layers, mislabel injection, fidelity criteria
- [Architecture](docs/ARCHITECTURE.md) — Skill → Workflow → Eval design *(note: predates the Go/TS split)*
- [Intent Workflow](docs/INTENT_WORKFLOW.md) — intent lifecycle and infrastructure resolution
- [Temporal-Equivalent Workflow Functionality](docs/TEMPORAL_FUNCTIONALITY.md) — retries + parallel fan-out recovered in the Go engine
- [Anthropic Alignment](docs/ANTHROPIC_ALIGNMENT.md) — responsible-AI practices and eval design
- [Advanced ML Integration](docs/ADVANCED_ML_INTEGRATION.md) — SLM, DSPy, GPU training
- [Deployment](DEPLOY.md) · [Pulumi Migration Plan](PULUMI_MIGRATION_PLAN.md) · [Archived docs](docs/archive/)

## License

Proprietary. Internal use only.
