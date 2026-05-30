# Precision Genomics Agent Platform — Implementation Plan

**Target Role:** Applied AI Engineer, Life Sciences (Beneficial Deployments) — Anthropic  
**Repository:** `upstream-label-correction`  
**Foundation:** precisionFDA Multi-Omics MSI Classification Challenge  
**Author:** Hossain  
**Date:** February 2026  
**Estimated Duration:** 3–4 weeks (parallel tracks)

---

## Project Status

| Item | Status |
|---|---|
| Implementation plan | ✅ Complete (this document) |
| ML pipeline design | ✅ Upgraded to Sentieon 1st-place championship methodology |
| Architecture diagram | ✅ Full system topology with 4-stage pipeline |
| Hyperparameter tuning workflow | ✅ Documented across all 4 stages |
| MCP tool specifications | ✅ 8 tools with I/O schemas |
| Agent skill designs | ✅ 4 skills with prompt templates |
| Temporal workflow patterns | ✅ 3 workflows with activity decomposition |
| Evaluation framework | ✅ 4 evals with thresholds |
| Code implementation | ✅ Complete — core ML engine, MCP servers, agent skills, evals, infrastructure |
| GCP deployment | ✅ Complete — Pulumi, Cloud Run, Vertex AI, CI/CD, SSE transport |
| Documentation suite | ✅ 4 of 4 docs complete (ARCHITECTURE, SCIENTIFIC_METHODOLOGY, ANTHROPIC_ALIGNMENT, GCP_DEPLOYMENT) |
| Advanced ML integration | ✅ Complete — SLM fine-tuning (`training/`), DSPy prompt optimization (`dspy_modules/`), GPU-accelerated training, synthetic data generator |

**Project knowledge available:** precisionFDA notebooks (Import, Proteomics, RNA-Seq, Availability, Final Results, Visualizations), raw challenge data (train/test TSVs for clinical, proteomics, RNA-Seq), institutional-defi-platform-api monorepo with existing Temporal/FastAPI/Kubernetes infrastructure.

---

## Executive Summary

This plan transforms an existing precisionFDA multi-omics classification project (proteomics + RNA-Seq → MSI status / mislabeled sample detection) into a production-grade **Claude-orchestrated agentic genomics platform**. The architecture directly mirrors Anthropic's Life Sciences infrastructure: MCP servers connecting Claude to domain-specific data, reusable agent skills, scientific evaluation frameworks, and Temporal-orchestrated research workflows.

The deliverable is a portfolio-ready system that demonstrates the exact capabilities Anthropic's Beneficial Deployments team is building with HHMI and the Allen Institute — taking a real scientific pipeline from "works in a notebook" to a trustworthy, integrated research tool.

---

## Strategic Alignment Matrix

| Anthropic Role Requirement | Platform Component | Evidence |
|---|---|---|
| MCP servers for genomics platforms | `genomics-omics-mcp-server` | Exposes multi-omics data as Claude-callable tools |
| Agentic scientific workflows | `BiomarkerDiscoveryAgent` | End-to-end: QC → feature selection → classification → interpretation |
| Reusable agent skills | 4 composable skills | Biomarker discovery, sample QC, cross-omics integration, literature grounding |
| Evaluation frameworks for scientific tasks | `evals/` suite | Biological validity, reproducibility, hallucination detection, benchmark comparison |
| Hands-on with partner engineering teams | Production codebase | FastAPI service, Temporal workflows, CI/CD, Docker |
| Identifies what's hard about deploying AI in life sciences | Technical writeup | Heterogeneous data, auditability, trust gap analysis |
| Technical content for self-service adoption | Documentation + prompt library | Other institutions can adopt without hand-holding |

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        Claude (Sonnet 4.5 / Opus 4.6)                    │
│                    Extended Thinking + Native Tool Use                    │
└─────────┬──────────────────┬──────────────────┬──────────────────────────┘
          │                  │                  │
   ┌──────▼───────┐  ┌──────▼───────┐  ┌───────▼────────┐
   │  MCP Server  │  │   PubMed     │  │  ToolUniverse  │
   │  (8 tools)   │  │  Connector   │  │   Connector    │
   │              │  │  (citations) │  │  (600+ tools)  │
   └──────┬───────┘  └──────┬───────┘  └───────┬────────┘
          │                  │                  │
┌─────────▼──────────────────▼──────────────────▼──────────────────────────┐
│                        Agent Skills Layer                                │
│                                                                          │
│  ┌──────────────────┐  ┌───────────────────┐  ┌──────────────────────┐  │
│  │    Biomarker      │  │   Sample QC       │  │   Cross-Omics        │  │
│  │    Discovery      │  │   (Dual-Method)   │  │   Integration        │  │
│  │                   │  │                   │  │   (COSMO-Inspired)   │  │
│  │  Multi-strategy   │  │  Classification   │  │                      │  │
│  │  feature select   │  │       +           │  │  4-stage pipeline:   │  │
│  │  + ensemble       │  │  Distance Matrix  │  │  Impute → Match →   │  │
│  │  classification   │  │  concordance      │  │  Predict → Correct   │  │
│  └────────┬─────────┘  └────────┬──────────┘  └──────────┬───────────┘  │
│           └──────────────────────┼───────────────────────┘               │
│                                  │                                       │
│  ┌───────────────────────────────┴────────────────────────────────────┐  │
│  │                   Literature Grounding Skill                       │  │
│  │        PubMed verification · Pathway mapping · Novelty scoring     │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼───────────────────────────────────────┐
│                    Temporal Workflow Orchestration                        │
│                                                                          │
│  BiomarkerDiscoveryWorkflow ─── fan-out/fan-in (parallel modalities)     │
│  SampleQCWorkflow ────────────── saga + dual-validation concordance      │
│  COSMOPipelineWorkflow ───────── 4-stage sequential with checkpoints     │
│                                                                          │
│  Task Queue: genomics-workflows  │  Retry: 3x exponential backoff       │
│  Timeout: 30min per workflow     │  Compensation: quarantine on failure  │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼───────────────────────────────────────┐
│                  Championship ML Pipeline (Sentieon-Informed)             │
│                                                                          │
│  ┌─────────────┐  ┌─────────────────┐  ┌──────────────────────────────┐ │
│  │  Stage 1:   │  │    Stage 2:     │  │        Stage 3:              │ │
│  │  Imputation │  │  Feature Select │  │  Cross-Omics Matching        │ │
│  │             │  │                 │  │                              │ │
│  │  MAR/MNAR   │──▶  ANOVA (BH/BF) │  │  Gene-level R² correlation  │ │
│  │  classify   │  │  LASSO (L1)     │  │  NxN distance matrix        │ │
│  │  NMF fill   │  │  NSC (shrunken) │  │  Hungarian algorithm        │ │
│  │  Zero-fill  │  │  RF (importance)│  │  Iterative subsampling      │ │
│  │  (Y-chr)    │  │       ▼         │  │  (100 iter × 80% genes)     │ │
│  └──────┬──────┘  │  Union-weighted │  └────────────┬─────────────────┘ │
│         │         │  integration    │               │                   │
│         │         └────────┬────────┘               │                   │
│         │                  │                        │                   │
│         │         ┌────────▼────────────────────────▼─────────────────┐ │
│         │         │             Stage 4: Ensemble Classification      │ │
│         └────────▶│                                                   │ │
│                   │  Label-Weighted k-NN ──┐                         │ │
│                   │  LASSO Classifier ─────┤  Meta-learner           │ │
│                   │  Nearest Shrunken ─────┤  (LogReg stacking)      │ │
│                   │  Random Forest ────────┘         │               │ │
│                   │                                  │               │ │
│                   │  Strategy A: Separate (♂/♀ + MSI independently)  │ │
│                   │  Strategy B: Joint (4-class combined phenotype)  │ │
│                   └──────────────────────────────────┬───────────────┘ │
│                                                      │                 │
│         ┌────────────────────────────────────────────▼──────────────┐  │
│         │              Dual-Validation Concordance                   │  │
│         │   Classification flags ∩ Distance matrix flags = HIGH     │  │
│         │   Single-method only = REVIEW                             │  │
│         └───────────────────────────────────────────────────────────┘  │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼───────────────────────────────────────┐
│                        Data & Infrastructure                             │
│                                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────┐  ┌──────────────────┐  │
│  │ precisionFDA │  │  PostgreSQL  │  │  Redis  │  │    Temporal      │  │
│  │ TSV data     │  │  16 +        │  │ cache + │  │    Server        │  │
│  │ (80 train    │  │  TimescaleDB │  │ session │  │    (workflow     │  │
│  │  80 test)    │  │  (features)  │  │ state   │  │     history)     │  │
│  └──────────────┘  └──────────────┘  └─────────┘  └──────────────────┘  │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │                    Evaluation Framework                            │   │
│  │  Biological Validity · Reproducibility · Hallucination Detection  │   │
│  │  Benchmark Comparison · Head-to-Head (original RF vs. ensemble)   │   │
│  └───────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────┘
```

**Data Flow Summary:**
```
TSV files → Imputation (MAR/MNAR + NMF) → Multi-strategy feature selection
  → Ensemble classification (4 classifiers × 2 strategies → meta-learner)
  → Cross-omics distance matrix matching (independent validation)
  → Dual-validation concordance → Corrected labels + audit trail
  → Claude interpretation (PubMed-grounded) → Structured report
```

---

## Phase 1: Foundation & MCP Server (Week 1)

### 1.1 Repository Scaffolding

**Objective:** Establish monorepo structure, CI, and development environment.

```
upstream-label-correction/
├── README.md
├── pyproject.toml                   # Unified Python project config
├── Dockerfile
├── docker-compose.yml               # PostgreSQL, Redis, Temporal
├── .github/
│   └── workflows/
│       ├── ci.yml                   # Lint + test + build
│       └── security-scan.yml        # Weekly SAST + dependency audit
├── mcp_server/
│   ├── __init__.py
│   ├── server.py                    # MCP server entrypoint
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── data_loader.py           # load_dataset tool
│   │   ├── availability_check.py    # check_availability tool
│   │   ├── biomarker_selector.py    # select_biomarkers tool
│   │   ├── classifier.py            # run_classification tool
│   │   ├── evaluator.py             # evaluate_model tool
│   │   └── explainer.py             # explain_features tool
│   └── schemas/
│       ├── __init__.py
│       └── omics.py                 # Pydantic schemas for tool I/O
├── agent_skills/
│   ├── __init__.py
│   ├── biomarker_discovery.py
│   ├── sample_qc.py
│   ├── cross_omics_integration.py
│   └── literature_grounding.py
├── workflows/
│   ├── __init__.py
│   ├── biomarker_discovery.py       # Temporal workflow
│   ├── sample_qc.py                 # Temporal workflow
│   ├── activities/
│   │   ├── __init__.py
│   │   ├── data_activities.py
│   │   ├── ml_activities.py
│   │   └── claude_activities.py
│   └── worker.py                    # Temporal worker entrypoint
├── api/
│   ├── __init__.py
│   ├── main.py                      # FastAPI app
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── analysis.py              # /analyze endpoints
│   │   ├── biomarkers.py            # /biomarkers endpoints
│   │   └── workflows.py             # /workflows endpoints
│   └── middleware/
│       ├── audit.py
│       └── auth.py
├── core/
│   ├── __init__.py
│   ├── config.py                    # Settings via Pydantic BaseSettings
│   ├── models.py                    # SQLModel ORM models
│   ├── database.py                  # PostgreSQL + TimescaleDB session
│   ├── data_loader.py               # OmicsDataLoader (from notebooks)
│   ├── imputation.py                # MAR/MNAR-aware NMF imputer (Sentieon method)
│   ├── availability.py              # Availability filter (imputation-aware)
│   ├── feature_selection.py         # Multi-strategy selector (ANOVA+LASSO+NSC+RF)
│   ├── classifier.py                # Ensemble classifier (LW-kNN+LASSO+NSC+RF)
│   ├── cross_omics_matcher.py       # Distance matrix matching (Sentieon SC2)
│   ├── pipeline.py                  # COSMO-inspired 4-stage orchestrator
│   ├── constants.py                 # Original + championship feature panels
│   └── feature_store.py             # TimescaleDB feature snapshots
├── data/
│   ├── raw/                         # precisionFDA challenge files
│   │   ├── train_cli.tsv
│   │   ├── train_pro.tsv
│   │   ├── train_rna.tsv
│   │   ├── test_cli.tsv
│   │   ├── test_pro.tsv
│   │   ├── test_rna.tsv
│   │   └── sum_tab_2.csv
│   └── processed/                   # Preprocessed outputs
├── notebooks/                       # Original precisionFDA notebooks (provenance)
│   ├── Import.ipynb
│   ├── Proteomics.ipynb
│   ├── RNA-Seq.ipynb
│   ├── Availability.ipynb
│   ├── Final_Results.ipynb
│   ├── MSI_Visual.ipynb
│   └── Gender_Visual.ipynb
├── evals/
│   ├── __init__.py
│   ├── biological_validity.py
│   ├── reproducibility.py
│   ├── hallucination_detection.py
│   ├── benchmark_comparison.py
│   └── fixtures/
│       └── known_msi_signatures.json
├── prompts/
│   ├── biomarker_discovery.md
│   ├── sample_qc_analysis.md
│   ├── feature_interpretation.md
│   └── regulatory_report.md
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DEPLOYMENT.md
│   ├── SCIENTIFIC_METHODOLOGY.md
│   └── ANTHROPIC_ALIGNMENT.md
└── tests/
    ├── conftest.py
    ├── test_mcp_tools/
    ├── test_agent_skills/
    ├── test_workflows/
    ├── test_api/
    └── test_evals/
```

**Acceptance Criteria:**
- `docker-compose up` starts all services
- `pytest tests/ -x` passes with ≥50 initial tests
- `ruff check .` passes clean
- CI pipeline green on push

### 1.2 Core ML Engine — Championship-Grade Pipeline

**Objective:** Extract the notebook pipeline into a testable Python module, then upgrade it with the winning methodology from Sentieon's 1st-place solution (RECOMB 2019) and the post-challenge COSMO consortium (published in Molecular & Cellular Proteomics, PMC8134945). This elevates the platform from a competent submission to a championship-caliber system.

> **Reference:** The precisionFDA NCI-CPTAC Multi-omics Challenge received 149 submissions for Sub-challenge 1 and 87 for Sub-challenge 2, from 52 teams across 15 countries. Sentieon won 1st place in Sub-challenge 1 and tied for 1st in Sub-challenge 2. The top 3 teams then collaborated with FDA/NCI organizers to build the open-source COSMO (COrrection of Sample Mislabeling by Omics) pipeline.

**Source notebooks → Target modules:**

| Notebook | Module | Key Logic |
|---|---|---|
| `Import.ipynb` + `preprocess.py` | `core/data_loader.py::OmicsDataLoader` | TSV ingestion, transpose, clinical/molecular merge |
| *(new — Sentieon method)* | `core/imputation.py::OmicsImputer` | MAR/MNAR-aware missing data imputation via NMF |
| `Availability.ipynb` | `core/availability.py::AvailabilityFilter` | 90% threshold + imputation-aware filtering |
| `Proteomics.ipynb` + RNA-Seq.ipynb | `core/feature_selection.py::MultiStrategySelector` | ANOVA + LASSO + NSC + RF ensemble feature selection |
| `Final Results.ipynb` | `core/classifier.py::EnsembleMismatchClassifier` | Label-Weighted k-NN + LASSO + NSC + RF ensemble |
| *(new — Sentieon method)* | `core/cross_omics_matcher.py::CrossOmicsMatcher` | Distance matrix matching between proteome and transcriptome |
| *(new — COSMO-inspired)* | `core/pipeline.py::COSMOInspiredPipeline` | Full 4-stage pipeline orchestrating all components |

#### Stage 1: Missing Data Imputation (`core/imputation.py`)

**Problem Sentieon identified:** Over 30% of genes had >20% missing data in the proteomic samples. Your original approach (Availability.ipynb) simply discarded genes below a 90% availability threshold. The winning solution instead *imputed* missing values using biologically-informed strategies, preserving far more features.

**MAR vs. MNAR Classification:**
```python
class OmicsImputer:
    """Sentieon-method missing data imputation with MAR/MNAR awareness."""

    def classify_missingness(self, expression_matrix, clinical_df):
        """
        Missing Not At Random (MNAR): Biologically expected zeros.
          - Y chromosome genes (DDX3Y, EIF1AY, etc.) in female samples → assign 0
          - Tissue-specific genes absent in colorectal context → assign 0

        Missing At Random (MAR): Stochastic measurement gaps.
          - All other missing values → impute via NMF
        """

    def impute_nmf(self, matrix, n_components="auto", max_iter=500):
        """
        Non-negative Matrix Factorization for MAR imputation.
        Decomposes X ≈ W·H where W (samples × k) and H (k × genes),
        then fills missing entries from the reconstructed product.

        Advantage over simple mean/median: preserves latent structure
        and cross-gene correlations in the expression data.
        """

    def impute(self, expression_matrix, clinical_df):
        """Full pipeline: classify → MNAR zeros → NMF for MAR → return filled matrix."""
```

**Why this matters for the Anthropic role:** Imputation is a recurring pain point in life sciences AI deployment. Researchers are skeptical of imputed values. The MAR/MNAR distinction is scientifically principled — it shows Claude (and the agent) can reason about *why* data is missing, not just that it is missing.

#### Stage 2: Multi-Strategy Feature Selection (`core/feature_selection.py`)

**Problem with original approach:** Using only Random Forest importance is a single-method strategy that misses features where other methods excel. Sentieon's winning approach combined multiple complementary strategies and integrated their results.

```python
class MultiStrategySelector:
    """Championship-grade feature selection combining 4 complementary methods."""

    def anova_selection(self, X, y, correction="bonferroni"):
        """
        Univariate Screening: One-way ANOVA per gene across clinical
        phenotype groups (MSI-High vs MSI-Low/MSS, Male vs Female).

        P-value correction methods (run both, union the results):
          - Bonferroni correction: conservative, controls family-wise error
          - Benjamini-Hochberg: less conservative, controls FDR

        Returns genes passing significance threshold after correction.
        """

    def lasso_selection(self, X, y, cv_folds=10):
        """
        L1-Regularized Logistic Regression (LASSO).
        Automatically drives irrelevant gene coefficients to zero.
        Cross-validate regularization strength (C parameter).
        Returns genes with non-zero coefficients at optimal C.
        """

    def nsc_selection(self, X, y, cv_folds=10):
        """
        Nearest Shrunken Centroids (Tibshirani et al., 2002).
        Shrinks class centroids toward overall centroid; genes with
        zero shrunken difference are eliminated.
        Particularly effective for high-dimensional, low-sample-size data.
        Cross-validate shrinkage threshold.
        """

    def random_forest_selection(self, X, y, n_estimators=500, cv_folds=10):
        """
        Original method from notebooks: RF importance with GridSearchCV.
        Preserved as one voice in the ensemble.
        """

    def ensemble_select(self, X, y, target, modality, strategy="union_weighted"):
        """
        Integrate features selected by each method:
          - "union": any gene selected by ≥1 method
          - "intersection": genes selected by all methods
          - "union_weighted": rank genes by # methods selecting them + average rank

        Returns: FeaturePanel with per-gene selection metadata showing
        which methods selected each gene and their respective rankings.
        """
```

**Feature panel structure (Pydantic model):**
```python
class SelectedFeature(BaseModel):
    gene: str
    selected_by: list[str]          # e.g., ["anova_bonferroni", "lasso", "rf"]
    selection_count: int             # How many methods selected this gene
    anova_pvalue: float | None
    lasso_coefficient: float | None
    nsc_centroid_diff: float | None
    rf_importance: float | None
    ensemble_rank: int               # Final integrated ranking

class FeaturePanel(BaseModel):
    target: str                      # "msi" | "gender"
    modality: str                    # "proteomics" | "rnaseq" | "combined"
    features: list[SelectedFeature]
    method_agreement_matrix: dict    # Overlap statistics between methods
```

> **Current Implementation Note:** The actual code (`core/feature_selection.py`) uses a `@dataclass` with fields `name`, `score`, `method`, `p_value`, and `rank` rather than the Pydantic `BaseModel` shown above. The `selected_by: list[str]` multi-method tracking is handled at the `FeaturePanel` level instead.

#### Stage 3: Ensemble Classification (`core/classifier.py`)

**Sentieon's key insight:** For binary clinical labels (gender + MSI), there are two valid strategies — predict each phenotype independently then merge, or treat all 4 combinations (Male-MSI-High, Male-MSI-Low, Female-MSI-High, Female-MSI-Low) as a 4-class problem. The winning solution ran both and integrated the results.

```python
class EnsembleMismatchClassifier:
    """
    Multi-classifier ensemble matching Sentieon's championship approach.

    Classifiers:
      1. Label-Weighted k-NN: Accounts for class imbalance by weighting
         predictions by prior label frequencies. Calibrated to match the
         expected mislabeling rate (~5%) from training data.
      2. LASSO (L1-regularized logistic regression)
      3. Nearest Shrunken Centroids
      4. Random Forest (original method, preserved for continuity)

    Integration strategies:
      - Separate: Predict gender and MSI independently, merge predictions
      - Joint: Predict 4-class combined phenotype directly
        > **Implementation Note:** The joint strategy computation (`y_gender * 10 + y_msi`) exists in code but is not yet connected to classifier training — only the "separate" strategy is functional.
      - Meta: Stack predictions from all classifiers as features for a
        final meta-learner (logistic regression)
    """

    def fit(self, X, y_gender, y_msi, mismatch_labels):
        """Train all classifiers with cross-validation."""

    def predict_ensemble(self, X):
        """Generate integrated predictions with confidence scores."""

    def label_weighted_knn(self, X_train, y_train, X_test, k=5, weights="label_frequency"):
        """
        Sentieon's innovation: k-NN where neighbor votes are weighted by
        the prior probability of each label. This prevents majority-class
        bias when MSI-High samples are ~15% of the cohort.
        """
```

#### Stage 4: Cross-Omics Distance Matrix Matching (`core/cross_omics_matcher.py`)

**This is the most novel component from Sentieon's Sub-challenge 2 solution.** Instead of classifying mismatch/no-mismatch directly, they reframed the problem as finding the optimal sample pairing between proteomics and RNA-Seq data.

```python
class CrossOmicsMatcher:
    """
    Sentieon Sub-challenge 2 method: Proteome ↔ Transcriptome matching
    via gene-level correlation and distance matrix optimization.

    For N samples, constructs an NxN distance matrix where entry (i,j)
    represents the distance between protein sample i and RNA sample j.
    Correctly paired samples should have the shortest distance on the
    diagonal. Off-diagonal minima indicate mislabeled samples.
    """

    def compute_gene_correlations(self, proteomics_df, rnaseq_df):
        """
        For each gene present in both modalities, fit a linear regression
        model (protein abundance ~ RNA expression). Use R² goodness-of-fit
        to identify genes with high cross-omics correlation.
        Returns a high-correlation gene set for downstream matching.
        """

    def build_distance_matrix(self, proteomics_df, rnaseq_df, gene_set,
                               method="expression_rank"):
        """
        Two distance definitions (Sentieon validated both work):
          1. "linear_model": Distance between expression values converted
             by the linear regression model
          2. "expression_rank": Distance based on expression level rankings
             of the same gene across different samples (rank correlation)

        Returns: NxN numpy array where rows = protein samples,
                 cols = RNA samples
        """

    def identify_mismatches(self, distance_matrix, method="hungarian"):
        """
        Find optimal assignment minimizing total distance.
        Hungarian algorithm for exact solution (O(n³)).
        Compare optimal assignment to diagonal (identity) assignment.
        Samples where optimal ≠ diagonal are mislabeled.

        Also supports iterative random subsampling from the correlated
        gene set (Sentieon's noise reduction technique) with majority
        voting across iterations.
        """

    def visualize_distance_matrix(self, distance_matrix, labels):
        """
        Generate the diagnostic heatmap showing:
        - Diagonal: correctly matched samples (short distance)
        - Off-diagonal minima: mislabeled samples (gray bullseye pattern)
        Matches the figure from Sentieon's published methodology.
        """
```

#### Preserved Original Features (Backward Compatibility)

All original notebook feature lists are preserved as baseline constants for comparison:

- **MSI proteomics (original):** TAP1, LCP1, PTPN6, CASK, ICAM1, ITGB2, CKB, LAP3, PTPRC, HSDL2, WARS, IFI35, TYMP, TAPBP, ERMP1, ANP32E, ROCK2, CNDP2, RFTN1, GBP1, NCF2, YARS2, RPL3, ENO1, SNX12, ARL3
- **MSI RNA-Seq (original):** EPDR1, APOL3, POU5F1B, CFTR, CIITA, MAX, PRSS23, FABP6, GABRP, SLC19A3, RAMP1, AREG, EREG, TNNC2, ANKRD27, PLCL2, TFCP2L1, LAG3, GRM8, BEX2, DEFB1, IRF1, CCL4, SLC51B, GBP4, HPSE
- **Gender proteomics + RNA-Seq:** Preserved as separate panels
- **Top RF importance (original):** S100A14 (0.318), ROCK2 (0.076), FHDC1 (0.071), PGM2 (0.053), GAR1 (0.042)

The agent's evaluation framework will compare original RF-only panel vs. multi-strategy ensemble panel in head-to-head classification performance.

#### COSMO-Inspired Orchestration (`core/pipeline.py`)

The full pipeline mirrors the 4-stage COSMO architecture developed by the top 3 teams post-challenge:

```
Stage 1: Data Preprocessing    → Imputation (MAR/MNAR) + normalization
Stage 2: Omics Data Pairing    → Cross-omics distance matrix matching
Stage 3: Phenotype Prediction  → Ensemble classification (gender + MSI)
Stage 4: Label Correction      → Integrate pairing + prediction → final labels
```

Each stage is implemented as both a standalone Python module (for direct use) and a Temporal activity (for workflow orchestration), ensuring the pipeline works with or without infrastructure dependencies.

**Acceptance Criteria:**
- `EnsembleMismatchClassifier` F1 ≥ original RF baseline (and ideally surpasses it)
- `CrossOmicsMatcher` correctly identifies all known mismatches in training set (`sum_tab_2.csv`)
- NMF imputation preserves ≥95% of features that were previously discarded by availability filter
- Multi-strategy feature selection produces a superset that includes ≥80% of the original RF-selected features plus additional candidates
- All 80 training + 80 test samples load and process correctly
- Head-to-head comparison report: original pipeline vs. championship pipeline

### 1.3 MCP Server Implementation

**Objective:** Build a Model Context Protocol server exposing 8 genomics tools (6 original + 2 new from Sentieon methodology).

**Tool Specifications:**

#### `load_dataset`
```
Input:  { dataset: "train" | "test", modalities: ["clinical", "proteomics", "rnaseq"] }
Output: { samples: int, features: { clinical: int, proteomics: int, rnaseq: int },
          msi_distribution: { high: int, low_mss: int }, gender_distribution: { male: int, female: int },
          missing_data_summary: { pct_missing_proteomics: float, pct_missing_rnaseq: float,
                                  genes_gt20pct_missing: int } }
```

#### `impute_missing` *(NEW — Sentieon method)*
```
Input:  { dataset: "train" | "test", modality: "proteomics" | "rnaseq",
          strategy: "nmf" | "median" | "knn", classify_missingness: true | false }
Output: { genes_before_imputation: int, genes_imputed_mar: int, genes_assigned_mnar_zero: int,
          nmf_reconstruction_error: float, features_recovered: int,
          comparison: { before_available_90pct: int, after_available_90pct: int } }
```

#### `check_availability`
```
Input:  { genes: [str], threshold: float (default 0.9), dataset: "train" | "test",
          use_imputed: bool (default true) }
Output: { available: [str], filtered: [str], availability_scores: { gene: float },
          imputation_impact: { genes_rescued: [str] } }
```

#### `select_biomarkers`
```
Input:  { target: "msi" | "gender" | "mismatch", modality: "proteomics" | "rnaseq" | "combined",
          methods: ["anova", "lasso", "nsc", "random_forest"] | "all",
          integration: "union" | "intersection" | "union_weighted",
          n_top: int (default 30), p_value_correction: "bonferroni" | "bh" | "both" }
Output: { biomarkers: [{ gene: str, ensemble_rank: int, selected_by: [str], selection_count: int,
                          anova_pvalue: float?, lasso_coef: float?, nsc_diff: float?, rf_importance: float? }],
          method_agreement: { anova_lasso_overlap: float, anova_rf_overlap: float, ... },
          comparison_to_original: { original_rf_panel_size: int, new_panel_size: int,
                                     overlap_genes: [str], novel_genes: [str] } }
```

#### `run_classification`
```
Input:  { features: [str] | "auto", target: "mismatch",
          classifiers: ["label_weighted_knn", "lasso", "nsc", "random_forest"] | "ensemble",
          phenotype_strategy: "separate" | "joint" | "both",
          meta_learner: "logistic_regression" | "none",
          test_size: float (default 0.3), cv_folds: int (default 10) }
Output: { ensemble_f1: float, per_classifier_f1: { classifier: float },
          best_strategy: str, phenotype_strategy_comparison: { separate_f1: float, joint_f1: float },
          classification_report: str,
          feature_importances: [{ gene: str, importance: float }],
          comparison_to_baseline: { original_rf_f1: float, championship_ensemble_f1: float, delta: float } }
```

#### `match_cross_omics` *(NEW — Sentieon Sub-challenge 2 method)*
```
Input:  { dataset: "train" | "test",
          distance_method: "linear_model" | "expression_rank" | "both",
          n_iterations: int (default 100),
          gene_sampling_fraction: float (default 0.8) }
Output: { distance_matrix: { shape: [int, int], diagonal_mean: float, off_diagonal_mean: float },
          identified_mismatches: [{ sample_id: str, matched_to: str, distance: float, confidence: float }],
          iteration_agreement: float,
          visualization_data: { heatmap_values: [[float]], mismatch_indicators: [{ row: int, col: int }] } }
```

#### `evaluate_model`
```
Input:  { model_id: str, test_data: "holdout" | "cross_val",
          compare_to_baseline: bool (default true) }
Output: { f1_score: float, precision: float, recall: float, confusion_matrix: [[int]],
          roc_auc: float, confidence_interval: { lower: float, upper: float },
          baseline_comparison: { original_f1: float, improvement_pct: float } }
```

#### `explain_features`
```
Input:  { genes: [str], context: "msi_classification" | "gender_prediction" | "mismatch_detection",
          include_selection_provenance: bool (default true) }
Output: { explanations: [{ gene: str, biological_function: str, relevance_to_target: str,
          known_associations: [str], pubmed_ids: [str],
          selection_provenance: { methods: [str], anova_pvalue: float?, pathway: str? } }] }
```

**Technical implementation:**
- Built with `mcp` Python SDK
- Stdio transport for local Claude Desktop integration
- SSE transport for remote/API access
- Each tool wraps the corresponding `core/omics_engine.py` class
- `explain_features` uses Anthropic API to generate grounded biological explanations with PubMed citation retrieval

**Acceptance Criteria:**
- MCP Inspector connects and lists all 8 tools
- Claude Desktop can invoke tools and receive structured results
- Tool execution times: data loading <2s, classification <30s, explanation <10s
- All tools return valid JSON matching their output schemas

---

## Phase 2: Agent Skills & Claude Integration (Week 2)

### 2.1 Biomarker Discovery Skill

**Objective:** A composable skill that takes a classification target and multi-omics data, then systematically identifies, validates, and interprets a biomarker panel.

**Workflow:**
1. Load dataset via `load_dataset` — note missing data summary
2. Impute missing data via `impute_missing` (MAR/MNAR-aware NMF)
3. Check feature availability via `check_availability` (on imputed data)
4. Select biomarkers via `select_biomarkers` with `methods="all"` — run ANOVA, LASSO, NSC, and RF independently for each modality, compare method agreement
5. Run ensemble classification via `run_classification` with `classifiers="ensemble"` — Label-Weighted k-NN + LASSO + NSC + RF with meta-learner
6. Run cross-omics matching via `match_cross_omics` — validate sample pairing independently of classification
7. Generate biological interpretations via `explain_features` with selection provenance
8. Cross-reference with known MSI signatures (ground truth: MLH1, MSH2, MSH6, PMS2 deficiency markers)
9. Produce structured report comparing original RF-only results vs. championship ensemble

**Claude prompt template (`prompts/biomarker_discovery.md`):**
```markdown
You are a computational genomics researcher analyzing multi-omics data from a
colorectal cancer cohort (NCI-CPTAC precisionFDA challenge). Your task is to
identify biomarkers predictive of {target} using {modalities} data, following
the championship methodology validated at RECOMB 2019.

Available tools:
- load_dataset: Load and summarize the dataset, including missing data profile
- impute_missing: Fill missing values using MAR/MNAR-aware NMF imputation
- check_availability: Verify genes have sufficient data (post-imputation)
- select_biomarkers: Multi-strategy feature selection (ANOVA + LASSO + NSC + RF)
- run_classification: Ensemble classification with Label-Weighted k-NN integration
- match_cross_omics: Cross-omics distance matrix matching (proteome ↔ transcriptome)
- evaluate_model: Model performance with baseline comparison
- explain_features: Biological context with selection method provenance

Approach this systematically:
1. Load the data and examine the missing data profile — what % of genes have
   >20% missing values? This informs imputation strategy.
2. Impute missing data: classify missingness as MAR vs MNAR (e.g., Y chromosome
   genes in female samples are MNAR → assign zero, not impute). Use NMF for MAR.
3. Filter for availability on the IMPUTED data — compare how many features are
   now available vs. the original 90% threshold approach.
4. Run ALL FOUR feature selection methods on each modality independently.
   Report which genes are selected by multiple methods (high confidence) vs.
   single methods (exploratory candidates). Use union_weighted integration.
5. Train the ensemble classifier: Label-Weighted k-NN (handles class imbalance),
   LASSO, NSC, and RF. Test both "separate" (predict gender + MSI independently)
   and "joint" (predict 4-class combined phenotype) strategies.
6. Independently validate with cross-omics distance matrix matching — do the
   same mislabeled samples appear in both classification and distance matrix results?
7. Interpret the top features biologically. For each gene, note:
   - Which selection methods chose it (provenance)
   - Known MSI pathway associations (immune infiltration, interferon response, etc.)
   - Whether it appears in published MSI signatures
8. Compare your championship pipeline results to the baseline RF-only approach.
   Quantify: feature panel overlap, F1 improvement, novel discoveries.

Report your findings with:
- Ranked biomarker panel with multi-method selection provenance
- Method agreement matrix (which methods agree on which genes?)
- Classification performance: ensemble vs. each individual classifier
- Cross-omics matching validation results
- Head-to-head: championship pipeline vs. original RF-only baseline
- Biological plausibility assessment with pathway context
- Recommendations for experimental validation
```

### 2.2 Sample QC Skill (Mismatch Detection) — Dual-Method Validation

**Objective:** Detect mislabeled samples using two independent approaches (Sentieon's winning strategy) — classification-based AND distance-matrix-based — then cross-validate results.

**Scientific context:** The precisionFDA challenge provided 80 training samples where some had intentionally swapped proteomics data (documented in `sum_tab_2.csv`). 52 teams from 15 countries submitted 149+87 solutions. The winning approach combined phenotype prediction with cross-omics distance matrix matching for maximum accuracy.

**Skill logic (dual validation):**

1. **Path A — Classification-based detection:**
   - Load all three data types (clinical, proteomics, RNA-Seq)
   - Impute missing data (MAR/MNAR-aware NMF)
   - Train ensemble classifier (Label-Weighted k-NN + LASSO + NSC + RF) to predict clinical phenotypes from molecular data
   - Samples where predicted phenotype ≠ annotated phenotype → flagged as potentially mislabeled
   - Both "separate" and "joint" phenotype strategies are run

2. **Path B — Cross-omics distance matrix matching:**
   - Compute gene-level R² correlations between proteomics and RNA-Seq
   - Select high-correlation gene set
   - Build NxN distance matrix (protein sample i vs. RNA sample j)
   - Apply iterative random gene subsampling (100 iterations, 80% genes each) for stability
   - Use Hungarian algorithm to find optimal sample assignment
   - Off-diagonal optimal assignments → mislabeled samples

3. **Cross-validation:**
   - Compare flagged samples from Path A and Path B
   - Samples flagged by BOTH methods = high confidence mislabel
   - Samples flagged by only one method = requires review
   - Generate concordance report with per-sample confidence scores

**Key insight for Anthropic alignment:** This dual-validation approach addresses the "auditability" and "trust" requirements head-on. A researcher can see that two independent methods agree on which samples are mislabeled — this is fundamentally more trustworthy than a single classifier's prediction. The distance matrix visualization (heatmap with off-diagonal minima) provides an intuitive visual proof.

### 2.3 Cross-Omics Integration Skill — COSMO-Inspired Pipeline

**Objective:** Automate the full multi-omics fusion pipeline following the COSMO architecture developed collaboratively by the top 3 challenge teams post-competition.

**COSMO 4-stage pipeline:**
1. **Data Preprocessing:** NMF imputation, normalization, MAR/MNAR classification
2. **Omics Data Pairing:** Cross-omics distance matrix matching (proteome ↔ transcriptome)
3. **Clinical Phenotype Prediction:** Ensemble classification of gender + MSI
4. **Label Correction:** Integrate pairing + prediction → corrected sample labels with confidence

**Additional evaluations:**
- Assess imputation impact: how many features recovered vs. simple availability filtering
- Compare combined multi-omics panel vs. individual modality panels
- Report which modality contributes most to each classification target
- Benchmark against published COSMO results on TCGA BRCA validation set (3.1% mislabeling rate, 16/521 samples correctly identified)

### 2.4 Literature Grounding Skill

**Objective:** Given a set of biomarker genes, use Claude + PubMed connector to validate biological plausibility and find supporting literature.

**Why this matters:** This is the hallucination-resistant layer. When Claude explains why GBP1 or PTPRC are MSI markers, those explanations must be grounded in real papers — not confabulated biology.

**Implementation:**
- Query PubMed API for each gene + disease context
- Claude synthesizes findings with citation IDs
- Cross-reference with known MSI pathway databases (KEGG, Reactome)
- Output includes confidence levels: "well-established" / "emerging evidence" / "novel finding"

---

## Phase 3: Temporal Workflows & Evaluation (Week 3)

### 3.1 BiomarkerDiscoveryWorkflow (Temporal)

**Objective:** Orchestrate the full biomarker discovery pipeline as a durable, retryable workflow.

**Pattern:** Fan-out/fan-in (mirrors existing ComplianceCheck workflow pattern).

```python
@workflow.defn
class BiomarkerDiscoveryWorkflow:

    @workflow.run
    async def run(self, params: BiomarkerDiscoveryParams) -> BiomarkerReport:
        # Activity 1: Data ingestion and QC
        dataset = await workflow.execute_activity(
            load_and_validate_data,
            params.dataset_config,
            start_to_close_timeout=timedelta(minutes=2)
        )

        # Activity 2: Sample QC (mismatch detection)
        qc_results = await workflow.execute_activity(
            run_sample_qc,
            dataset,
            start_to_close_timeout=timedelta(minutes=5)
        )

        # Activity 3: Fan-out — parallel feature selection per modality
        proteomics_task = workflow.execute_activity(
            select_features, FeatureSelectionParams("proteomics", params.target), ...)
        rnaseq_task = workflow.execute_activity(
            select_features, FeatureSelectionParams("rnaseq", params.target), ...)

        pro_features, rna_features = await asyncio.gather(proteomics_task, rnaseq_task)

        # Activity 4: Fan-in — combine and filter
        combined_panel = await workflow.execute_activity(
            integrate_and_filter,
            IntegrationParams(pro_features, rna_features, threshold=0.9),
            start_to_close_timeout=timedelta(minutes=2)
        )

        # Activity 5: Classification
        classification = await workflow.execute_activity(
            train_and_evaluate,
            ClassificationParams(combined_panel, params.target, params.hyperparams),
            start_to_close_timeout=timedelta(minutes=10)
        )

        # Activity 6: Claude-powered interpretation
        interpretation = await workflow.execute_activity(
            generate_interpretation,
            InterpretationParams(combined_panel.top_features, params.target),
            start_to_close_timeout=timedelta(minutes=5)
        )

        # Activity 7: Report generation
        return await workflow.execute_activity(
            compile_report,
            ReportParams(qc_results, combined_panel, classification, interpretation),
            start_to_close_timeout=timedelta(minutes=2)
        )
```

**Task queue:** `genomics-workflows`  
**Retry policy:** 3 retries with exponential backoff for Claude API activities  
**Timeout:** 30 minutes total workflow execution

### 3.2 SampleQCWorkflow (Temporal)

**Pattern:** Saga with compensation (if QC fails, flag but don't block downstream).

**Activities:**
1. `load_clinical_data` — Parse clinical TSVs
2. `load_molecular_data` — Parse proteomics + RNA-Seq TSVs
3. `compute_consistency_scores` — Per-sample concordance metrics
4. `classify_mismatches` — RF mismatch prediction
5. `generate_qc_report` — Audit trail with explanations
6. Compensation: `quarantine_flagged_samples` — Isolate but preserve flagged data

### 3.3 Evaluation Framework

**Objective:** Rigorous evaluation suite that proves the agent produces scientifically valid results.

#### Eval 1: Biological Validity
```python
class BiologicalValidityEval:
    """Does the agent's biomarker selection include known MSI biology?"""

    KNOWN_MSI_MARKERS = {
        "immune_infiltration": ["PTPRC", "ITGB2", "LCP1", "NCF2"],
        "interferon_response": ["GBP1", "GBP4", "IRF1", "IFI35", "WARS"],
        "antigen_presentation": ["TAP1", "TAPBP", "LAG3"],
        "mismatch_repair_adjacent": ["CIITA", "TYMP"]
    }

    def evaluate(self, agent_selected_genes: list[str]) -> EvalResult:
        # Compute overlap with known marker categories
        # Score: % of known pathways represented in agent selection
        # Threshold: ≥60% pathway coverage = PASS
```

#### Eval 2: Reproducibility
```python
class ReproducibilityEval:
    """Same inputs → same biomarker panel across 10 runs?"""

    def evaluate(self, n_runs: int = 10) -> EvalResult:
        # Run agent pipeline n times with identical inputs
        # Measure Jaccard similarity of top-20 features across runs
        # Threshold: ≥0.85 average Jaccard = PASS
```

#### Eval 3: Hallucination Detection
```python
class HallucinationDetectionEval:
    """When Claude explains feature biology, are citations real?"""

    def evaluate(self, interpretations: list[FeatureInterpretation]) -> EvalResult:
        # For each cited PubMed ID, verify it exists via PubMed API
        # For each biological claim, check against UniProt/KEGG
        # Score: % of verifiable claims
        # Threshold: ≥90% verifiable = PASS
```

#### Eval 4: Benchmark Comparison
```python
class BenchmarkComparisonEval:
    """Agent-selected features vs. published MSI signatures?"""

    PUBLISHED_SIGNATURES = {
        "precisionFDA_top5": ["S100A14", "ROCK2", "FHDC1", "PGM2", "GAR1"],
        "TCGA_MSI_signature": [...],  # Published colorectal MSI gene sets
        "Guinney_CMS_markers": [...]   # Consensus Molecular Subtypes
    }

    def evaluate(self, agent_panel: list[str]) -> EvalResult:
        # Compare overlap, unique discoveries, and classification F1
        # Report: agent vs. each benchmark signature
```

---

## ML Hyperparameter Tuning Workflow

This section details how hyperparameter tuning flows across the 4-stage championship pipeline. Every hyperparameter is selected by cross-validation on the training data — never by manual inspection or test set leakage.

### Stage 1: Imputation — NMF Component Selection

NMF imputation has one critical hyperparameter: the number of latent components `k` (the rank of the factorization W·H ≈ X). Too few components underfit and blur biological signal; too many overfit to noise in a small cohort.

**Tuning approach:** Standard CV doesn't apply to imputation. Instead, use a held-out masking strategy — randomly mask 10% of *known* values, impute them, measure reconstruction error (Frobenius norm between true and imputed values), and sweep `k` from 2 to 20. Sentieon's NMF approach also benefits from multiple random initializations (`n_init`) since NMF is non-convex. The MAR/MNAR classification step upstream is deterministic (Y-chromosome gene list + biological rules), so it doesn't require tuning.

### Stage 2: Feature Selection — 4 Independent Tuning Paths

Each feature selection method has its own hyperparameters, tuned independently before ensemble integration.

**ANOVA:** The tuning target is the significance threshold after multiple testing correction. Bonferroni is parameter-free (α/n_tests), but Benjamini-Hochberg has an FDR control rate (typically 0.05 or 0.10). The plan runs both corrections and unions the selected gene sets — BH is less conservative and recovers more features. The implementation runs both and lets the downstream ensemble weigh the results.

**LASSO (L1-Regularized Logistic Regression):** The regularization strength `C` (inverse of λ) is the key hyperparameter. Tuned via 10-fold cross-validation using F1 score. `LogisticRegressionCV` with `penalty='l1'` and `solver='liblinear'` sweeps a logarithmic grid of C values (typically 1e-4 to 1e2). Genes with non-zero coefficients at the optimal C form the selected panel. The coefficient magnitude directly indicates feature importance direction and strength.

**Nearest Shrunken Centroids (NSC):** The shrinkage threshold Δ controls how aggressively class centroids are pulled toward the overall centroid. Tuned via 10-fold CV, sweeping Δ from 0 (no shrinkage, all genes kept) to max(Δ) where all genes are eliminated. The optimal Δ minimizes CV classification error while minimizing gene count. Implemented via the Tibshirani PAM algorithm: for each Δ, compute shrunken centroids, classify, measure F1.

**Random Forest:** The original pipeline's method, now one voice in the ensemble. GridSearchCV over:

| Parameter | Grid | Notes |
|---|---|---|
| `n_estimators` | 500 (fixed) | Sentieon also used 500 |
| `min_samples_leaf` | [1, 3, 5, 10, 25, 100] | Controls overfitting on small N |
| `criterion` | ['gini', 'entropy'] | Split quality metric |
| `max_depth` | [1, 5, 10, 15, 20, 25, 30] | Tree complexity bound |
| `max_features` | [None, 0.5, 'sqrt', 'log2'] | Feature subsampling per split |
| `cv` | 10-fold | `scoring`: F1 |

Total: 6 × 2 × 7 × 4 = 336 parameter combinations × 10 folds × 500 trees. With 80 samples, each fold trains fast.

> **Implementation Note:** The current code uses a reduced 6-combination grid (3 `max_depth` × 2 `min_samples_leaf`) suitable for the small training set (n=80). The full 336-combination grid is documented for scaling to larger cohorts.

**Ensemble integration** (`union_weighted`) is parameter-free — it ranks genes by how many methods selected them, breaking ties by average rank across methods.

### Stage 3: Cross-Omics Distance Matrix Matching

This stage has surprisingly few traditional hyperparameters because it's fundamentally a matching/assignment problem, not a prediction problem.

**Gene correlation threshold:** The R² cutoff for including a gene in the high-correlation gene set. Sentieon used the top-k correlated genes or a reasonable R² threshold (e.g., 0.3). Sweep this and measure matching accuracy on the training set where ground truth mismatches are known from `sum_tab_2.csv`.

**Iterative subsampling parameters:**

| Parameter | Default | Purpose |
|---|---|---|
| `n_iterations` | 100 | Number of bootstrap-like sampling rounds |
| `gene_sampling_fraction` | 0.8 | % of correlated genes sampled per iteration |
| `voting_threshold` | 0.6 | Flagged if identified in ≥60% of iterations |

These are relatively robust — 100 iterations at 80% is standard bootstrap-like behavior. The voting threshold can be tuned against training set ground truth.

**Distance definition:** `linear_model` vs. `expression_rank` — Sentieon validated that both work and produce consistent results. The implementation runs both and checks concordance rather than choosing one.

### Stage 4: Ensemble Classification — Most Complex Tuning

This is where the most hyperparameter interactions live: 4 classifiers × 2 phenotype strategies × 1 meta-learner.

**Label-Weighted k-NN:**

| Parameter | Grid | Notes |
|---|---|---|
| `k` | [3, 5, 7, 9, 11] | Number of neighbors |
| `weights` | ["label_frequency", "uniform", "distance"] | Sentieon's innovation: weight votes by prior class probability |
| Distance metric | ["euclidean", "manhattan", "cosine"] | Similarity measure |

Tuned via 10-fold CV with F1 scoring. The "label_frequency" weighting is the key innovation — it prevents majority-class bias when MSI-High is ~15% of the cohort.

**LASSO Classifier:** Same LogisticRegressionCV tuning as Stage 2, but trained on the *integrated* feature panel (post-ensemble selection). The optimal C may differ because the feature space has changed.

**NSC Classifier:** Same Δ sweep as Stage 2, applied to the integrated panel.

**Random Forest Classifier:** Same GridSearchCV grid as Stage 2, applied to the integrated panel.

**Phenotype strategy selection:** A structural choice evaluated empirically, not a traditional hyperparameter:

| Strategy | Approach | When It Wins |
|---|---|---|
| A: "separate" | Train gender + MSI classifiers independently, merge | When phenotypes are independent signals |
| B: "joint" | Train single 4-class classifier (Male×MSI-High, Male×MSI-Low, Female×MSI-High, Female×MSI-Low) | When phenotype interactions matter |

Both strategies are run for all 4 classifiers (8 total classifier instances), and the meta-learner picks the best combination.

**Meta-learner (stacking):**
- **Input:** Predictions from all 8 classifier instances (4 classifiers × 2 strategies)
- **Model:** Logistic regression with L2 regularization
- **Tuning:** C tuned via nested 5-fold CV (inner loop)
- **Evaluation:** Outer 10-fold CV evaluates the full stacked ensemble's generalization
- **Guard against leakage:** Inner CV for meta-learner tuning, outer CV for honest performance estimation

### Tuning Orchestration in Temporal

The `BiomarkerDiscoveryWorkflow` handles tuning as a fan-out/fan-in pattern:

```
Activity 1: Imputation (NMF k-selection)          ~30 seconds
    │
    ▼
Activity 2: Feature Selection (fan-out parallel)   ~2 minutes total
    ├── ANOVA tuning (BF + BH)                     ~5 seconds
    ├── LASSO CV (C sweep)                          ~15 seconds
    ├── NSC CV (Δ sweep)                            ~15 seconds
    └── RF GridSearchCV (336 combos)                ~90 seconds
    │
    ▼ (fan-in: union_weighted integration)
    │
Activity 3: Cross-Omics Matching                   ~45 seconds
    ├── Gene correlation (R² computation)
    └── 100× iterative distance matrix + Hungarian
    │
    ▼
Activity 4: Ensemble Classification (fan-out)      ~3 minutes total
    ├── LW-kNN CV (k × weights × distance)         ~20 seconds
    ├── LASSO CV on integrated panel                ~15 seconds
    ├── NSC CV on integrated panel                  ~15 seconds
    ├── RF GridSearchCV on integrated panel          ~90 seconds
    └── Meta-learner nested CV                      ~30 seconds
    │
    ▼
Activity 5: Dual-validation concordance            ~5 seconds
```

**Total tuning time:** ~6–7 minutes on the 80-sample dataset. Each activity has a Temporal retry policy (3× exponential backoff) and the RF GridSearchCV activities use `n_jobs=-1` for parallel tree fitting.

**Reproducibility guarantees:** The `random_state` seed is propagated through all stages. The Reproducibility Eval validates that 10 identical runs produce ≥0.85 Jaccard similarity on the final feature panel.

---

## Phase 4: API, Documentation & Polish (Week 4)

### 4.1 FastAPI Service

**Endpoints:**

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `POST` | `/analyze/biomarkers` | Trigger biomarker discovery (returns workflow ID) |
| `POST` | `/analyze/sample-qc` | Trigger sample QC workflow |
| `GET` | `/analyze/{workflow_id}/status` | Poll workflow status |
| `GET` | `/analyze/{workflow_id}/report` | Get completed report |
| `GET` | `/biomarkers/panels` | List discovered biomarker panels |
| `GET` | `/biomarkers/{panel_id}/features` | Get features for a panel |
| `POST` | `/evals/run` | Execute evaluation suite |
| `GET` | `/evals/{eval_id}/results` | Get eval results |

### 4.2 Documentation Suite

#### `docs/ARCHITECTURE.md`
- System architecture diagram (Mermaid)
- Data flow from TSV → MCP tool → Claude → report
- Technology choices and rationale

#### `docs/SCIENTIFIC_METHODOLOGY.md`
- precisionFDA challenge description and approach
- Multi-omics integration strategy
- Feature selection methodology (Random Forest importance with availability filtering)
- Classification approach (GridSearchCV, F1-optimized)
- Key findings: S100A14 as dominant mismatch predictor, immune pathway enrichment in MSI features

#### `docs/ANTHROPIC_ALIGNMENT.md`
- How each component maps to the Beneficial Deployments role
- Lessons learned about deploying AI in life sciences
- Trust gap analysis: what researchers need before adopting AI tools
- Comparison to Anthropic's HHMI/Allen Institute partnership goals

#### `docs/DEPLOYMENT.md`
- Docker Compose local development
- Kubernetes deployment (leveraging existing EKS infrastructure)
- MCP server registration in Claude Desktop

### 4.3 Prompt Library

Production-tested prompts for life sciences tasks, ready for the Anthropic prompt library:

| Prompt | Task | Key Techniques |
|---|---|---|
| `biomarker_discovery.md` | End-to-end multi-omics biomarker identification | Step-by-step scientific reasoning, tool orchestration |
| `sample_qc_analysis.md` | Detect mislabeled or contaminated samples | Anomaly detection framing, audit trail generation |
| `feature_interpretation.md` | Biological interpretation of ML-selected features | Citation grounding, pathway context, novelty assessment |
| `regulatory_report.md` | Draft FDA-style biomarker qualification report | Structured output, evidence hierarchy, limitation disclosure |

---

## Phase 5: Integration & Demo (Days 25–28)

### 5.1 End-to-End Demo Script

A Claude Desktop session demonstrating the championship-grade pipeline:

1. **"Load the precisionFDA training data and give me an overview"**  
   → Claude calls `load_dataset`, reports 80 samples, 4118 proteins, 17447 genes, MSI distribution, **and that >30% of genes have >20% missing proteomic data**

2. **"That's a lot of missing data. Impute it using the championship method"**  
   → Claude calls `impute_missing` with MAR/MNAR classification. Reports: Y-chromosome genes in female samples assigned zero (MNAR), remaining gaps filled via NMF. **Features recovered: X genes that would have been lost to the 90% availability filter**

3. **"Now run all four feature selection methods on the proteomics data for MSI prediction"**  
   → Claude calls `select_biomarkers(methods="all", integration="union_weighted")`. Reports method agreement matrix: ANOVA, LASSO, NSC, and RF each select overlapping but distinct gene sets. **Highlights genes selected by 3+ methods as high-confidence MSI markers** (e.g., TAP1, GBP1, PTPRC appear across methods)

4. **"Train the ensemble classifier and compare to the original Random Forest approach"**  
   → Claude calls `run_classification(classifiers="ensemble", phenotype_strategy="both")`. Reports ensemble F1 vs. original RF F1, with breakdown per classifier. **"Separate" vs. "joint" phenotype strategy comparison shows which works better for this data**

5. **"Now independently validate using cross-omics distance matrix matching"**  
   → Claude calls `match_cross_omics(distance_method="both", n_iterations=100)`. Reports NxN distance matrix results. **"Both classification and distance matrix matching identify the same N mislabeled samples — dual-method concordance provides high confidence"**

6. **"Explain why these specific genes are MSI markers and cite the literature"**  
   → Claude calls `explain_features(include_selection_provenance=true)`. Reports biological context **with selection method provenance** — "GBP1 was selected by ANOVA (p<0.001), LASSO, and RF. It's an interferon-gamma-induced GTPase in the MSI-associated immune infiltration pathway (PMID: ...)"

7. **"Run the full evaluation suite"**  
   → Claude triggers evals. Reports biological validity (MSI pathway coverage), reproducibility (Jaccard), hallucination detection (PubMed verification), **and head-to-head benchmark: championship pipeline vs. original RF-only baseline**

### 5.2 Technical Blog Post / Writeup

A 1500-word technical narrative for the Anthropic application "Why Anthropic?" field and portfolio site:

- **The problem:** Genomics researchers spend weeks on repetitive multi-omics analysis pipelines. Sample mislabeling affects ~5% of clinical trial data (Nature Medicine, PMID: 30194412), reducing credibility of precision medicine results.
- **The challenge:** The precisionFDA NCI-CPTAC challenge attracted 52 teams from 15 countries. I participated, then systematically upgraded my pipeline by studying the 1st-place Sentieon solution and the post-challenge COSMO consortium methodology.
- **What the winners did differently:** MAR/MNAR-aware NMF imputation instead of simple filtering, multi-strategy feature selection (ANOVA + LASSO + NSC + RF) instead of RF-only, cross-omics distance matrix matching as independent validation, Label-Weighted k-NN for class imbalance handling.
- **What I built on top of that:** An MCP-enabled agentic system where Claude orchestrates the championship pipeline end-to-end — with 8 domain-specific tools, dual-validation sample QC, and a rigorous evaluation framework grounded in real biological knowledge.
- **The hard parts:** Heterogeneous data formats, scientific auditability requirements, the trust gap between "the model says it's mislabeled" and "I believe it" (solved via dual-method concordance and visual distance matrix proof), hallucination risk in biological interpretations.
- **What I learned:** The gap between a competent single-method approach and a championship-caliber system mirrors the gap between a notebook prototype and production AI in life sciences. Both require methodological rigor, not just engineering polish.
- **Why Anthropic:** Anthropic wants to make Claude the go-to tool for life sciences R&D. I've built exactly the infrastructure — MCP servers, agent skills, Temporal workflows, scientific evaluations — that the Beneficial Deployments team is creating with HHMI and Allen Institute. And I've done it on a real genomics challenge where ground truth exists and performance is measurable.

---

## Implementation Status

> **As of March 2026:** Phases 1–4 are implemented with the following deviations from this plan:
>
> **Implemented:**
> - Core ML engine (imputation, feature selection, classifier, cross-omics matcher, pipeline)
> - MCP server with 8 tools (stdio transport)
> - 4 agent skills (biomarker discovery, sample QC, cross-omics integration, literature grounding)
> - Evaluation framework (biological validity, reproducibility, hallucination detection, benchmark)
> - Test suite (260+ tests)
> - CI pipeline (GitHub Actions)
> - 3 documentation files: ARCHITECTURE.md, SCIENTIFIC_METHODOLOGY.md, ANTHROPIC_ALIGNMENT.md
>
> **Not yet implemented:**
> - `security-scan.yml` CI workflow
> - `data/` and `notebooks/` directories (raw precisionFDA data not committed)
> - `COSMOPipelineWorkflow` as standalone Temporal workflow (exists as `core/pipeline.py` class)
> - 1 documentation file: DEPLOYMENT.md
> - Literature grounding skill (4th agent skill — since implemented)
> - FastAPI service layer
> - SSE transport for MCP server

---

## Testing Strategy

| Layer | Framework | Target Coverage | Priority Tests |
|---|---|---|---|
| MCP Tools | pytest + mcp test client | 90%+ | Tool schema validation, data loading correctness, feature selection reproducibility |
| Agent Skills | pytest + mock Claude API | 80%+ | Skill composition, error handling, output schema compliance |
| Workflows | pytest + Temporal test environment | 85%+ | Activity execution, saga compensation, timeout handling |
| API | pytest + httpx async client | 80%+ | Route validation, auth middleware, workflow triggering |
| Evals | pytest (evals as tests) | 100% of eval logic | Biological validity thresholds, reproducibility bounds |
| Integration | pytest + Docker Compose | Key paths | End-to-end: API → workflow → MCP tool → result |

**Total target: ≥250 tests**

---

## Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| MCP Server | `mcp` Python SDK | Native Claude tool integration |
| API | FastAPI + Pydantic v2 | Consistent with existing platform patterns |
| Workflows | Temporal (Python SDK) | Durable execution, matches existing infrastructure |
| ML — Classification | scikit-learn (RF, LASSO, k-NN, NSC) | Multi-strategy ensemble matching Sentieon's winning approach |
| ML — Imputation | scikit-learn NMF + custom MAR/MNAR | Championship-grade missing data handling |
| ML — Optimization | scipy.optimize (Hungarian algorithm) | Optimal assignment for cross-omics distance matrix matching |
| ML — Statistics | statsmodels (ANOVA), scipy.stats | Univariate screening with Bonferroni/BH correction |
| Database | PostgreSQL 16 + TimescaleDB | Feature store, analysis results persistence |
| Cache | Redis | Session state, intermediate results |
| LLM | Anthropic Claude API (Sonnet 4.5) | Biological interpretation, report generation |
| Literature | PubMed E-utilities API | Citation grounding for hallucination prevention |
| CI/CD | GitHub Actions | Lint (ruff), test, build, security scan |
| Containerization | Docker + Docker Compose | Local development, future Kubernetes deployment |
| Observability | structlog + OpenTelemetry | Audit trails, latency tracking |
| Reference | COSMO (bzhanglab/COSMO on GitHub) | Post-challenge open-source benchmark for validation |

---

## Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| Claude hallucinating gene functions | High — undermines scientific trust | Hallucination eval + PubMed citation verification + known marker cross-reference |
| Feature selection non-determinism | Medium — RF randomness affects reproducibility | Set `random_state` seeds, reproducibility eval with Jaccard threshold, multi-method consensus reduces single-method variance |
| precisionFDA data is small (n=80) | Medium — may limit generalizability claims | Acknowledge in documentation, position as methodology demo not clinical tool, reference COSMO validation on TCGA BRCA (n=521) |
| NMF imputation introducing artifacts | Medium — imputed values could create false signal | Validate by comparing classification with/without imputation, check imputed gene distributions against non-missing samples |
| Cross-omics correlation assumptions | Low-Medium — linear model between protein and RNA may not hold for all genes | Use both distance definitions (linear model + expression rank), iterative random subsampling for stability |
| Ensemble classifier overfitting on small N | Medium — 80 samples with 4 classifiers + meta-learner | Strict cross-validation, monitor train/test gap, compare to single-classifier baselines |
| MCP SDK breaking changes | Low — SDK is actively evolving | Pin version, abstract tool registration behind interface |
| Temporal complexity for reviewers | Low — some may not know Temporal | Include non-Temporal execution path (direct Python) as fallback |
| COSMO comparison expectations | Low — reviewers may expect exact COSMO reproduction | Clearly frame as "COSMO-inspired" with methodology attribution, not a fork |

---

## Success Metrics

| Metric | Target | Measurement |
|---|---|---|
| MCP tools functional | 8/8 tools working in Claude Desktop | Manual testing + MCP Inspector |
| Ensemble F1 ≥ baseline | Championship ensemble F1 ≥ original RF F1 | Automated test comparison |
| Cross-omics matcher accuracy | 100% of known training mismatches identified | Validated against `sum_tab_2.csv` |
| NMF imputation recovery | ≥95% features preserved vs. ≥10% lost to availability filter | Before/after feature count comparison |
| Multi-method feature agreement | ≥3/4 methods agree on top-10 features | Method agreement matrix |
| Biological validity eval | ≥60% known MSI pathway coverage | Eval suite |
| Reproducibility eval | ≥0.85 Jaccard across 10 runs | Eval suite |
| Hallucination eval | ≥90% verifiable citations | PubMed API verification |
| Dual-validation concordance | ≥80% overlap between classification and distance matrix flagged samples | Cross-validation report |
| Test coverage | ≥250 tests, ≥80% line coverage | pytest + coverage |
| Documentation completeness | 4 docs + 4 prompts + README + methodology comparison | Manual review |
| Demo script execution | End-to-end in <5 minutes | Timed run |
| Head-to-head report | Quantified improvement over original pipeline | Automated benchmark |

---

## Application Positioning

This project demonstrates every core competency the Applied AI Engineer, Life Sciences role requires:

1. **"Work as a deep technical partner to life sciences research institutions"** — Built from a real NCI-CPTAC genomics challenge that attracted 52 international teams, upgraded with the published championship methodology (COSMO, PMC8134945)
2. **"Build hands-on with partner engineering teams"** — Production codebase with CI/CD, 250+ tests, Docker, Temporal workflows — not notebooks
3. **"Develop ecosystem infrastructure — MCP servers, benchmarks, reusable agent skills"** — 8 MCP tools, 4 composable skills, and a rigorous eval framework, all purpose-built for genomics
4. **"Help design and evaluate agentic scientific workflows"** — Temporal-orchestrated COSMO-inspired pipeline with dual-validation (classification + distance matrix) for maximum scientific trustworthiness
5. **"Identify what's actually hard about deploying AI in life sciences"** — Missing data handling (30%+ genes affected), auditability (dual-method concordance), hallucination risk (PubMed-grounded citations), class imbalance (MSI-High ~15% of cohort), trust gap (visual proof via distance matrix heatmaps) — all documented and solved
6. **"Create technical content that lets partners self-serve"** — Prompt library, documentation, modular skills, head-to-head methodology comparisons

**Championship credibility:** This isn't just a demo — it implements the actual winning methodology from a challenge that published in Nature Medicine and Molecular & Cellular Proteomics, producing the open-source COSMO tool now used in clinical trial quality control. The agent doesn't just run a pipeline; it runs the *validated* pipeline.

The salary range ($280K–$320K) and "scrappy founder mentality" emphasis signals they want someone who ships, not someone who presents. This project ships.
