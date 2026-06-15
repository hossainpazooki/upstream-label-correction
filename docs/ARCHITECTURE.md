# Architecture

> **[HISTORICAL — design-era doc]** This describes the original Python-monolith
> **Skill → Workflow → Eval** design and **predates the polyglot split** (Go
> `intent-controller`, TypeScript `web`/`infra-ts`, Python ML core) and the CLUE
> closed loop. The Python `intents/`/`workflows/` packages it references are
> **decommissioned**. For the current architecture see [`README.md`](../README.md)
> and [`TECHNICAL_WRITEUP.md`](TECHNICAL_WRITEUP.md).

> **Central principle:** Every capability follows the **Skill -> Workflow -> Eval** lifecycle.
> A Skill encodes domain logic, a Workflow makes it durable, and an Eval gates it for trust.

---

## 1. Design Philosophy

The platform is organised around a single architectural pattern that repeats for every domain capability:

1. **Skill** — an async Python class that orchestrates MCP tool calls to accomplish a domain task (e.g. biomarker discovery, sample QC). Skills are the unit of agent reasoning.
2. **Workflow** — a Temporal workflow definition that wraps the same logical steps with durability, compensation, and observability. Workflows are the unit of production execution.
3. **Eval** — a standalone evaluation class that validates the output of a skill or workflow against domain-specific thresholds. Evals are the unit of trust.

This pattern is **domain-portable**. The interface contracts (skill constructor, workflow phases, eval result shape) remain identical; only the core logic, schemas, and thresholds change when porting to a new domain.

---

## 2. System Diagram

```
  Agent (Claude / LLM)
    |
    |  natural language -> tool calls
    v
+---------------------------+
|      Skill Layer          |   agent_skills/
|  BiomarkerDiscoverySkill  |   Orchestrates multi-step domain logic
|  SampleQCSkill            |   via _call_tool() -> MCP tools
|  CrossOmicsIntegrationSkill|
|  LiteratureGroundingSkill |
+---------------------------+
    |
    |  tool_name + kwargs
    v
+---------------------------+
|      MCP Tool Layer       |   mcp_server/
|  8 tools with Pydantic    |   Registry + dynamic dispatch
|  I/O schemas              |   Protocol-compliant boundaries
+---------------------------+
    |
    |  validated input
    v
+---------------------------+
|      Core ML Layer        |   core/
|  COSMOInspiredPipeline    |   Pure computation
|  OmicsImputer             |   No protocol, no I/O concerns
|  EnsembleMismatchClassifier|
|  MultiStrategySelector    |
|  CrossOmicsMatcher        |
+---------------------------+

  =========== Parallel execution planes ===========

+---------------------------+
|      Workflow Layer       |   workflows/
|  BiomarkerDiscoveryWorkflow|  Temporal @workflow.defn
|  SampleQCWorkflow         |   Fan-out/fan-in, saga compensation
|  Activities by concern    |   Progress queries, retry policies
+---------------------------+

+---------------------------+
|      Eval Layer           |   evals/
|  BiologicalValidityEval   |   Duck-typed: evaluate() -> EvalResult
|  BenchmarkComparisonEval  |   Domain-specific thresholds
|  HallucinationDetectionEval|  Fixture-driven validation
|  ReproducibilityEval      |
+---------------------------+
```

---

## 3. Layer Contracts

### 3.1 Skill Layer (`agent_skills/`)

**Interface contract:**

```python
class SomeSkill:
    def __init__(self, tool_caller: Callable | None = None) -> None: ...
    async def _call_tool(self, tool_name: str, **kwargs) -> dict: ...
    async def run(self, ...) -> dict: ...
```

- `__init__(tool_caller)` — injectable callable for MCP tool dispatch. Enables testing with mocks and production use with real MCP clients.
- `_call_tool()` — internal dispatcher that supports both sync and async callables (checks `hasattr(result, "__await__")`).
- `run()` — async entry point returning a structured dict report.

**Concrete skills:**

| Skill | File | Purpose |
|-------|------|---------|
| `BiomarkerDiscoverySkill` | `agent_skills/biomarker_discovery.py` | End-to-end pipeline: load -> impute -> availability -> select -> classify -> match -> explain |
| `SampleQCSkill` | `agent_skills/sample_qc.py` | Dual-path mismatch detection (classification + distance matrix) with concordance analysis |
| `CrossOmicsIntegrationSkill` | `agent_skills/cross_omics_integration.py` | COSMO pipeline delegation: load -> impute -> availability -> match -> classify -> evaluate |
| `LiteratureGroundingSkill` | `agent_skills/literature_grounding.py` | PubMed search + optional LLM synthesis for gene-level evidence grounding |

**Why this layer exists:** Composability (skills combine tools into domain workflows), testability (injectable tool_caller), and domain encoding (each skill captures expert knowledge about step ordering and parameter defaults).

**Exception:** `LiteratureGroundingSkill` uses a different constructor signature — `__init__(http_client, llm_client)` — because it calls external APIs (PubMed, Claude) directly rather than routing through MCP tools.

---

### 3.2 MCP Tool Layer (`mcp_server/`)

**Registry pattern** (`mcp_server/server.py`):

```python
_TOOL_REGISTRY: dict[str, tuple[type, str, str]] = {
    "tool_name": (PydanticInputSchema, "module.path", "description"),
    ...
}
```

Each tool call follows: validate input with Pydantic -> `importlib.import_module(module_path)` -> `await module.run_tool(input_data)` -> return Pydantic output as JSON.

**8 registered tools:**

| Tool Name | Input Schema | Module |
|-----------|-------------|--------|
| `load_dataset` | `LoadDatasetInput` | `mcp_server.tools.data_loader` |
| `impute_missing` | `ImputeMissingInput` | `mcp_server.tools.impute_missing` |
| `check_availability` | `CheckAvailabilityInput` | `mcp_server.tools.availability_check` |
| `select_biomarkers` | `SelectBiomarkersInput` | `mcp_server.tools.biomarker_selector` |
| `run_classification` | `RunClassificationInput` | `mcp_server.tools.classifier` |
| `match_cross_omics` | `MatchCrossOmicsInput` | `mcp_server.tools.match_cross_omics` |
| `evaluate_model` | `EvaluateModelInput` | `mcp_server.tools.evaluator` |
| `explain_features` | `ExplainFeaturesInput` | `mcp_server.tools.explainer` |

All I/O schemas are defined in `mcp_server/schemas/omics.py` and inherit from `core.models.CustomBaseModel` (Pydantic v2).

**Why this layer exists:** MCP protocol compliance, schema validation at system boundaries, dynamic dispatch for lazy loading, and decoupling of agent-facing interface from computation.

---

### 3.3 Core ML Layer (`core/`)

Pure computation classes with no protocol or I/O dependencies:

| Class | File | Responsibility |
|-------|------|---------------|
| `COSMOInspiredPipeline` | `core/pipeline.py` | 4-stage orchestrator: Impute -> Match -> Predict -> Correct |
| `OmicsImputer` | `core/imputation.py` | MNAR/MAR classification + NMF imputation |
| `EnsembleMismatchClassifier` | `core/classifier.py` | Multi-classifier ensemble with meta-learner |
| `MultiStrategySelector` | `core/feature_selection.py` | ANOVA, LASSO, NSC, RF ensemble feature selection |
| `CrossOmicsMatcher` | `core/cross_omics_matcher.py` | Distance matrix + Hungarian matching + dual validation |
| `AvailabilityFilter` | `core/availability.py` | Gene availability scoring and pre/post-imputation comparison |
| `OmicsDataLoader` | `core/data_loader.py` | Clinical, proteomics, and RNA-Seq data loading |

**Why this layer exists:** Testability (no async, no protocol overhead), reusability (skills, workflows, and tools all delegate here), and separation of ML logic from infrastructure.

---

### 3.4 Workflow Layer (`workflows/`)

GCP Workflows definitions that make skill-equivalent logic durable and observable, with a local runner for development.

**GCP Workflow YAML definitions** (`workflows/definitions/`):
- `biomarker_discovery.yaml` — 7 steps with `parallel for` on impute + feature select phases
- `sample_qc.yaml` — 6 sequential steps with `try/except` saga compensation
- `prompt_optimization.yaml` — 5 steps with `switch` on compile failure

Each step calls `http.post` to the activity service with retry policy (1s initial, 30s max, 3 attempts).

**Activity Service** (`workflows/activity_service.py`):
- FastAPI app exposing all activities as `POST /activities/{name}` endpoints
- Deployed as a dedicated Cloud Run service (activity-worker)
- Handles long-running ML work separately from the user-facing API

**Local Runner** (`workflows/local_runner.py`):
- `LocalWorkflowRunner` with `run_biomarker_discovery()`, `run_sample_qc()`, `run_prompt_optimization()`
- Calls activity functions directly via `asyncio.gather` for fan-out
- Used for local development (no GCP emulator exists for Workflows)

**Activities** are grouped by concern in `workflows/activities/`:

| File | Activities | Concern |
|------|-----------|---------|
| `data_activities.py` | `load_and_validate_data_activity`, `load_clinical_data_activity`, `load_molecular_data_activity` | Data I/O |
| `ml_activities.py` | `impute_data_activity`, `select_features_activity`, `integrate_and_filter_activity`, `train_and_evaluate_activity` | ML computation |
| `claude_activities.py` | `generate_interpretation_activity`, `compile_report_activity` | LLM-powered biological interpretation |
| `dspy_activities.py` | `generate_synthetic_cohort_activity`, `compile_dspy_modules_activity` | DSPy prompt optimization |
| `gpu_training_activities.py` | `train_expression_encoder_activity`, `finetune_slm_activity` | Vertex AI training jobs |

**Progress Tracking** (`workflows/progress.py`):
- `WorkflowExecution` SQLModel table in Cloud SQL
- `update_progress()` / `get_progress()` functions called by the activity service

**Schemas** (`workflows/schemas.py`):
- `WorkflowStatus` — StrEnum: PENDING, RUNNING, COMPLETED, FAILED, CANCELLED
- Per-workflow Params, Result, and Progress dataclasses (e.g. `BiomarkerDiscoveryParams`, `BiomarkerDiscoveryResult`, `BiomarkerDiscoveryProgress`)

**Why this layer exists:** Durability (GCP Workflows guarantees completion or compensation), observability (progress tracking via Cloud SQL), and compensation (saga pattern for safe failure handling). Fully serverless — no VMs to manage.

---

### 3.5 Eval Layer (`evals/`)

Duck-typed evaluation classes returning `EvalResult`:

```python
@dataclass
class EvalResult:
    name: str        # eval identifier
    passed: bool     # threshold gate
    score: float     # numeric score
    threshold: float # pass/fail boundary
    details: dict    # eval-specific metadata
```

**4 concrete evals:**

| Eval | File | Threshold | What it measures |
|------|------|-----------|-----------------|
| `BiologicalValidityEval` | `evals/biological_validity.py` | 0.60 | Fraction of known MSI pathways covered by agent-selected genes |
| `BenchmarkComparisonEval` | `evals/benchmark_comparison.py` | — | Performance comparison against published baselines |
| `HallucinationDetectionEval` | `evals/hallucination_detection.py` | — | Detection of fabricated gene names or pathway associations |
| `ReproducibilityEval` | `evals/reproducibility.py` | — | Consistency of results across repeated runs |

Each eval uses `evaluate()` (not `run()`) as its entry method, loading validation data from `evals/fixtures/` (e.g. `known_msi_signatures.json`).

**Why this layer exists:** Regression detection (CI-gatable pass/fail), domain trust (biologically grounded thresholds), and reproducibility (deterministic fixture-based validation).

---

## 4. Data Flow

End-to-end trace for a biomarker discovery request:

```
1. Agent receives prompt: "Find MSI biomarkers in the proteomics data"
                |
2. Agent calls BiomarkerDiscoverySkill.run(target="msi", modalities=["proteomics"])
                |
3. Skill calls _call_tool("load_dataset", ...) ──> MCP server
                |
4. MCP server: LoadDatasetInput.model_validate(args)
               importlib.import_module("mcp_server.tools.data_loader")
               await module.run_tool(validated_input)
                |
5. Tool delegates to core: OmicsDataLoader().load_clinical("train")
                |
6. Response flows back: core dict -> Pydantic output -> JSON -> skill report
                |
7. Skill continues: impute_missing -> check_availability -> select_biomarkers
                    -> run_classification -> match_cross_omics -> explain_features
                |
8. Skill returns consolidated report dict to agent
                |
9. Agent presents findings to user
```

For production execution, the same logical flow runs as a GCP Workflow (`workflows/definitions/biomarker_discovery.yaml`) calling the activity service via HTTP, with step-level retry policies and Cloud SQL progress tracking.

---

## 5. Extending to New Domains

The skill -> workflow -> eval pattern is domain-portable. To add a new domain:

| Component | What stays the same | What changes |
|-----------|-------------------|-------------|
| **Skill** | Constructor signature `__init__(tool_caller)`, `_call_tool()` dispatcher, `async run() -> dict` | Step sequence, tool names, parameter defaults |
| **MCP Tools** | Registry pattern, Pydantic I/O, dynamic dispatch | Schema fields, tool implementations, module paths |
| **Core ML** | Class structure, pure computation pattern | Algorithms, data formats, model types |
| **Workflow** | YAML definition, activity service pattern, progress tracking, retry policies | Phase names, fan-out topology, compensation logic |
| **Eval** | `EvalResult` dataclass, `evaluate()` method, fixture loading | Thresholds, validation logic, fixture data |

**Porting recipe:**

1. Define domain schemas in `mcp_server/schemas/<domain>.py`
2. Implement core computation in `core/<domain>_*.py`
3. Create tool handlers in `mcp_server/tools/<domain>_*.py` and register in `_TOOL_REGISTRY`
4. Build skill in `agent_skills/<domain>.py` following the `__init__(tool_caller)` contract
5. Define workflow YAML in `workflows/definitions/<domain>.yaml` with activities in `workflows/activities/`
6. Add evals in `evals/<domain>_*.py` with fixtures in `evals/fixtures/`

---

## 6. Infrastructure

| Technology | Role | Location |
|-----------|------|----------|
| Pulumi (Python SDK) | Infrastructure as code | `infra/` |
| Python 3.11+ | Runtime | All layers |
| Pydantic v2 | Schema validation | `mcp_server/schemas/`, `workflows/schemas.py`, `core/models.py` |
| MCP SDK | Agent-tool protocol | `mcp_server/server.py` |
| GCP Workflows | Workflow orchestration | `workflows/definitions/` |
| scikit-learn | ML classifiers, feature selection | `core/classifier.py`, `core/feature_selection.py` |
| NumPy / pandas | Data manipulation | `core/` |
| Anthropic SDK | LLM interpretation | `workflows/activities/claude_activities.py`, `agent_skills/literature_grounding.py` |
| pytest | Testing | `tests/` |

---

## 7. Key Design Decisions

### 7.1 Duck-Typed Evals

Evals are plain classes with an `evaluate()` method returning `EvalResult`, not subclasses of an abstract base. This keeps the eval contract minimal and avoids framework lock-in. Any class matching the shape can be used as an eval.

### 7.2 Injectable `tool_caller`

Skills accept a `tool_caller` callable in their constructor rather than importing MCP infrastructure directly. This enables:
- Unit testing with simple mock functions
- Production use with real MCP clients
- Swapping transport layers without changing skill logic

### 7.3 Pydantic at Boundaries Only

Pydantic validation happens at the MCP tool layer (system boundary) and workflow schemas, not inside core ML classes. Core classes use plain Python types (dicts, DataFrames, Series) for maximum flexibility and zero serialization overhead in hot paths.

### 7.4 GCP Workflows for Production, Local Runner for Dev

Skills are lightweight async classes — fast to test, fast to iterate. GCP Workflows add serverless orchestration (step-level retries, fan-out, compensation) only in production. The `LocalWorkflowRunner` calls the same activity functions directly for fast local development without any cloud dependency.

### 7.5 Dynamic Dispatch in MCP Server

The tool registry uses `importlib.import_module()` for lazy loading of tool implementations. This means:
- Server startup is fast (no eager imports of ML dependencies)
- Adding a tool requires only a registry entry, not a code change in the dispatch logic
- Tool modules are isolated — a bug in one tool doesn't prevent others from loading
