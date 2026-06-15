# Anthropic Alignment

> **[HISTORICAL — design-era doc]** Written against the original platform
> framing; component names and the Python-monolith structure predate the polyglot
> split (Go `intent-controller`, TypeScript `web`/`infra-ts`, Python ML core) and
> the CLUE closed loop. The responsible-AI / eval principles still apply, but for
> current structure see [`README.md`](../README.md) and
> [`TECHNICAL_WRITEUP.md`](TECHNICAL_WRITEUP.md).

> How each component of this platform maps to the Applied AI Engineer, Life Sciences
> (Beneficial Deployments) role at Anthropic, and lessons learned about deploying
> AI in life sciences research.

---

## 1. Component-to-Role Mapping

The Beneficial Deployments team builds infrastructure for partners like HHMI and the Allen Institute to use Claude in scientific research. Every component in this platform was designed to demonstrate one or more of those capabilities on a real genomics challenge with measurable ground truth.

| Role Requirement | Platform Component | Evidence |
|---|---|---|
| MCP servers for genomics platforms | `mcp_server/` — 8 tools with Pydantic I/O | Complete MCP-compliant server exposing multi-omics data as Claude-callable tools over stdio transport |
| Agentic scientific workflows | `agent_skills/` — 4 composable skills | End-to-end orchestration: QC -> feature selection -> classification -> interpretation, all driven by tool calls |
| Reusable agent skills | Skill -> Workflow -> Eval pattern | Identical interface contracts (`__init__(tool_caller)`, `async run() -> dict`) across all skills; domain-portable by design |
| Evaluation frameworks for scientific tasks | `evals/` — 4 evals with domain thresholds | Biological validity, hallucination detection, reproducibility, benchmark comparison — all CI-gatable |
| Hands-on with partner engineering teams | Production codebase | Temporal workflows, Pydantic schemas, CI/CD, Docker, 260+ tests |
| Identify what's hard about deploying AI in life sciences | Section 3 of this document | Missing data, auditability, trust gaps, hallucination risk, class imbalance |
| Technical content for self-service adoption | Documentation suite + modular architecture | Other institutions can adopt the MCP tools, skills, or evals independently |

---

## 2. What Makes This Real

This is not a toy demo. The platform implements the actual championship methodology from the precisionFDA NCI-CPTAC Multi-Omics MSI Classification Challenge:

- **52 international teams** competed on the same dataset
- **Ground truth exists** — MSI status and mislabeled samples are known
- **Published methodology** — the COSMO pipeline from the top 3 teams' post-challenge collaboration
- **Measurable performance** — F1 scores, pathway coverage, and mismatch detection rates can be compared head-to-head with published results

The eval framework validates outputs against these published baselines, not synthetic benchmarks. When the `BiologicalValidityEval` checks that agent-selected genes cover known MSI pathways, those pathways are the actual immune infiltration, interferon response, and antigen presentation signatures established in the literature.

---

## 3. What's Hard About Deploying AI in Life Sciences

Five recurring problems surfaced during development. Each maps to infrastructure the Beneficial Deployments team is building.

### 3.1 Missing Data Is Semantically Rich

Over 30% of genes have missing values in typical multi-omics datasets. But not all missing values mean the same thing:

- **MNAR**: Y-chromosome genes are biologically absent in female samples. Imputing them would be wrong.
- **MAR**: Measurement artifacts that can be recovered via matrix factorization.

**Lesson**: An AI tool that treats all NaN values identically will produce biologically nonsensical results. The MAR/MNAR classification in `OmicsImputer` shows that Claude (and the agent) must reason about *why* data is missing, not just that it is.

**Infrastructure implication**: MCP tools need domain-specific context about data semantics, not just data access.

### 3.2 Auditability Is Non-Negotiable

Researchers will not act on AI-generated findings without understanding the reasoning. When the platform flags a sample as mislabeled, the researcher needs to see:

- Which method(s) flagged it (classification, distance matrix, or both)
- The concordance level (HIGH / REVIEW / PASS)
- The underlying evidence (distance matrix scores, classifier confidence)

**Lesson**: Every tool output in the MCP layer returns structured evidence, not just conclusions. The `EvalResult.details` dict carries pathway-level breakdowns, per-gene coverage, and per-citation verification status.

**Infrastructure implication**: MCP tool schemas should encode provenance and evidence chains, not just final answers.

### 3.3 Hallucination Risk Is Domain-Specific

When Claude explains why a gene is an MSI biomarker, fabricated gene-pathway associations are difficult for non-experts to detect and dangerous if acted upon. Standard LLM hallucination benchmarks do not cover this.

**Mitigation** (two layers):
1. The `LiteratureGroundingSkill` pre-grounds every gene explanation in real PubMed results before presentation. Confidence is scored by publication count (>= 10 PMIDs = high, >= 3 = medium, < 3 = low).
2. The `HallucinationDetectionEval` verifies that cited PubMed IDs actually exist via NCBI E-utilities. Threshold: >= 90% verifiable citations.

**Lesson**: Hallucination detection must be domain-specific. A generic factuality check cannot assess whether "GBP1 is involved in interferon-gamma signalling in MSI-H tumours" is true.

**Infrastructure implication**: Eval frameworks need fixtures derived from domain ground truth (published pathway markers, verified PMIDs), not generic benchmarks.

### 3.4 The Trust Gap: "The Model Says" vs. "I Believe It"

The hardest deployment problem is not technical accuracy but researcher trust. A classifier that flags 5 samples as mislabeled needs to overcome skepticism that the model is wrong, not the labels.

**Solution** — Dual-method concordance:
- Classification-based detection captures complex phenotype-expression relationships
- Distance-matrix matching is model-free and independently derived
- A HIGH-concordance flag (both methods agree) is qualitatively more convincing than a single-method flag

This mirrors how scientific findings gain credibility: independent replication using different methods.

**Lesson**: Production AI in life sciences must provide multiple independent lines of evidence, not a single confidence score.

**Infrastructure implication**: Agent skills should be designed around concordance and cross-validation patterns, not single-model outputs.

### 3.5 Class Imbalance Is the Norm

MSI-High tumours represent roughly 15% of clinical cohorts. Standard classifiers optimized for accuracy will ignore the minority class. The platform addresses this through:

- Label-weighted k-NN (inverse label-frequency weighting)
- F1-optimized hyperparameter search (not accuracy)
- Ensemble meta-learning that combines diverse base classifiers

**Lesson**: Every ML component in a life sciences platform must be imbalance-aware by default. This cannot be an afterthought.

---

## 4. Trust Gap Analysis

Researchers evaluating AI tools for adoption have specific concerns that generic software demonstrations do not address.

| Concern | What Researchers Ask | How This Platform Answers |
|---------|---------------------|--------------------------|
| **Biological plausibility** | "Do the selected genes make biological sense?" | `BiologicalValidityEval` validates pathway coverage against published MSI signatures |
| **Reproducibility** | "Will I get the same result tomorrow?" | `ReproducibilityEval` measures Jaccard similarity across repeated runs (threshold >= 0.85) |
| **Transparency** | "Why was this sample flagged?" | Dual-method concordance with per-method evidence in structured output |
| **Hallucination** | "Are these citations real?" | PubMed verification via E-utilities; >= 90% verifiable threshold |
| **Benchmarking** | "How does this compare to published results?" | `BenchmarkComparisonEval` compares against precisionFDA and TCGA reference panels |
| **Data handling** | "Does it understand my data's quirks?" | MAR/MNAR-aware imputation; availability filtering; sex-chromosome handling |

---

## 5. Comparison to HHMI / Allen Institute Partnership Goals

Anthropic's partnerships with HHMI and the Allen Institute focus on making Claude useful for research workflows. This platform demonstrates the three infrastructure layers those partnerships require.

### Layer 1: Domain-Specific MCP Tools

HHMI researchers need Claude to access their experimental data without manual export. This platform's 8 MCP tools show the pattern:

- `load_dataset` — unified data access across clinical, proteomics, and RNA-Seq modalities
- `impute_missing` — domain-aware preprocessing (not generic pandas operations)
- `select_biomarkers` — multi-strategy feature selection with ensemble integration
- `explain_features` — biologically grounded interpretation with provenance

Each tool has Pydantic input/output schemas and returns structured results that Claude can reason about. The same pattern applies to any research domain: define schemas, implement core logic, register in the MCP server.

### Layer 2: Composable Agent Skills

The Allen Institute's research workflows span multiple tools in sequence. Skills encode this orchestration:

- `BiomarkerDiscoverySkill` chains 7 tool calls in a scientifically validated order
- `SampleQCSkill` runs two independent analysis paths and cross-validates
- `LiteratureGroundingSkill` grounds every finding in PubMed before presentation

The injectable `tool_caller` design means these skills work identically in:
- Unit tests (mock tool_caller)
- Development (local MCP server)
- Production (remote MCP server over SSE)

### Layer 3: Scientific Evaluation

Both partnerships need assurance that Claude's outputs are trustworthy. The eval framework provides CI-gatable validation:

- Every eval returns `EvalResult(name, passed, score, threshold, details)`
- Thresholds are set from domain knowledge (60% pathway coverage, 90% citation verification, 85% reproducibility)
- Fixtures contain published ground truth, not synthetic benchmarks
- Evals run in CI, blocking deployment if thresholds are not met

---

## 6. Lessons for Beneficial Deployments

### What Worked

1. **Pydantic at boundaries, plain Python inside.** MCP tools validate I/O schemas rigorously. Core ML classes use dicts and DataFrames. This keeps the hot path fast and the system boundary safe.

2. **Duck-typed evals.** No abstract base class, no framework. Any class with `evaluate() -> EvalResult` is an eval. This made it trivial to add new evals without touching existing code.

3. **Injectable tool_caller.** The single design decision that makes skills testable, portable, and transport-agnostic. Every skill can be tested with a 3-line mock.

4. **Dual-method validation as a design pattern.** Not specific to genomics — any domain where trust is critical benefits from independent analytical paths with concordance scoring.

5. **Fixture-based eval ground truth.** Loading known MSI pathway markers from a JSON fixture makes evals deterministic, version-controllable, and auditable.

### What's Still Hard

1. **Real data stochasticity.** NMF imputation and Random Forest feature selection produce slightly different results per run. The `ReproducibilityEval` quantifies this, but achieving 100% determinism requires seed control across all ML libraries — a fragile proposition.

2. **LLM interpretation quality.** The `LiteratureGroundingSkill` can verify citations but cannot fully assess whether a biological explanation is correct. This requires domain expert review and better evaluation methodology.

3. **Scaling to new modalities.** Adding a third omics modality (e.g. metabolomics) requires new MCP tools, schema extensions, and cross-modality matching logic. The architecture supports it, but the implementation effort is non-trivial.

4. **Researcher onboarding.** The platform is technically sound but requires researchers to trust an AI-mediated workflow. Adoption depends on demonstrating value on their specific datasets, not on the precisionFDA challenge data.
