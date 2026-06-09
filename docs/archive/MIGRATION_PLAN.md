# Migration Plan: TypeScript + Next.js Full-Stack with Python ML Core

> ⚠️ **SUPERSEDED — historical reference only.**
> This plan put the workflow engine and intent lifecycle in TypeScript. That
> decision was reversed: **workflow orchestration and intent lifecycle now live
> in the Go `intent-controller`** (`intent-controller/`), with the Next.js API
> routes proxying to it. Infrastructure also moved from Terraform/Python-Pulumi
> to TypeScript Pulumi in `infra-ts/`.
>
> This was superseded by [`PULUMI_MIGRATION_PLAN.md`](PULUMI_MIGRATION_PLAN.md),
> which has itself now been **executed and retired** to this archive (the
> polyglot split is complete). Use both files only to understand earlier
> history. In particular, Phase 3 ("Workflow Orchestration Migration" to TS)
> below is **no longer in effect** — see Migration 1 in the Pulumi plan.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Next.js App (TypeScript)                  │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │  Dashboard UI │  │  API Routes  │  │  Middleware (Auth,     │ │
│  │  (React/RSC)  │  │  /api/*      │  │  Audit, CORS)          │ │
│  └──────────────┘  └──────┬───────┘  └────────────────────────┘ │
│                           │                                      │
│  ┌──────────────┐  ┌──────┴───────┐  ┌────────────────────────┐ │
│  │  Workflow     │  │  MCP Server  │  │  DSPy Client           │ │
│  │  Orchestrator │  │  (TS SDK)    │  │  (calls Python DSPy)   │ │
│  └──────┬───────┘  └──────┬───────┘  └────────────────────────┘ │
│                           │                                      │
│  ┌──────────────┐  ┌──────┴───────┐                              │
│  │  ML Client   │  │  Redis Queue │  ← BullMQ for long ops      │
│  │  (HTTP)      │  │  (BullMQ)    │                              │
│  └──────┬───────┘  └──────┬───────┘                              │
└─────────┼─────────────────┼──────────────────────────────────────┘
          │                 │
          ▼                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Python ML Microservices                         │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │  ML Service   │  │  Redis Worker│  │  Training Service      │ │
│  │  (FastAPI)    │  │  (long-run   │  │  (Vertex AI)           │ │
│  │  - impute     │  │   pipelines) │  │  - SLM fine-tune       │ │
│  │  - classify   │  │  - pipeline  │  │  - encoder train       │ │
│  │  - features   │  │  - training  │  │  - DDP training        │ │
│  │  - match      │  │  - DSPy      │  │                        │ │
│  │  - DSPy proxy │  │   compile    │  │                        │ │
│  └──────────────┘  └──────────────┘  └────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────┐  ┌──────────────┐
│  PostgreSQL 16       │  │  Redis 7     │
└─────────────────────┘  └──────────────┘
```

---

## Phase 1: Project Scaffolding & Infrastructure

### 1.1 Initialize Next.js TypeScript project
- Create `web/` directory with Next.js 15 (App Router)
- TypeScript strict mode, ESLint, Prettier
- Tailwind CSS + shadcn/ui for dashboard components
- `package.json` with all dependencies

### 1.2 Database layer (Prisma)
- Replace SQLModel/SQLAlchemy with Prisma ORM
- Migrate `core/models.py` and `core/database.py` to `prisma/schema.prisma`
- Tables: experiments, workflows, biomarker_panels, analysis_results
- PostgreSQL connection via `DATABASE_URL`

### 1.3 Docker Compose update
- Add `web` service (Next.js, port 3000)
- Rename existing Python services to `ml-service`, `mcp-server`, `training-worker`
- Keep `db` and `redis` as-is
- Add nginx reverse proxy (optional, for unified domain routing)

**Files created:**
```
web/
├── package.json
├── tsconfig.json
├── next.config.ts
├── tailwind.config.ts
├── prisma/
│   └── schema.prisma
├── src/
│   ├── app/
│   │   └── layout.tsx
│   └── lib/
│       └── prisma.ts
├── Dockerfile
└── .env.example
```

---

## Phase 2: API Routes Migration (FastAPI → Next.js API Routes)

### 2.1 Core API routes
Migrate all 11 FastAPI endpoints to Next.js Route Handlers:

| Python (FastAPI)                     | TypeScript (Next.js)                          |
|--------------------------------------|-----------------------------------------------|
| `GET /health`                        | `src/app/api/health/route.ts`                 |
| `GET /`                              | `src/app/api/route.ts`                        |
| `POST /analyze/biomarkers`           | `src/app/api/analyze/biomarkers/route.ts`     |
| `POST /analyze/sample-qc`           | `src/app/api/analyze/sample-qc/route.ts`      |
| `GET /analyze/{id}/status`          | `src/app/api/analyze/[id]/status/route.ts`    |
| `GET /analyze/{id}/report`          | `src/app/api/analyze/[id]/report/route.ts`    |
| `POST /workflows/run`               | `src/app/api/workflows/route.ts`              |
| `GET /workflows/{id}/status`        | `src/app/api/workflows/[id]/status/route.ts`  |
| `POST /workflows/{id}/cancel`       | `src/app/api/workflows/[id]/cancel/route.ts`  |
| `GET /biomarkers/panels`            | `src/app/api/biomarkers/panels/route.ts`      |
| `GET /biomarkers/{id}/features`     | `src/app/api/biomarkers/[id]/features/route.ts`|

### 2.2 Middleware migration
- `api/middleware/auth.py` → Next.js middleware (`src/middleware.ts`) with JWT via `jose`
- `api/middleware/audit.py` → Custom middleware or Next.js instrumentation hook

### 2.3 ML service client
- Create `src/lib/ml-client.ts` — typed HTTP client (fetch/axios) for calling Python ML service
- All ML-heavy routes proxy to Python: imputation, classification, feature selection, cross-omics matching

### 2.4 Validation schemas
- Migrate Pydantic schemas to Zod schemas
- `workflows/schemas.py` → `src/lib/schemas/workflows.ts`
- `mcp_server/schemas/omics.py` → `src/lib/schemas/omics.ts`

**Files created:**
```
web/src/
├── app/api/
│   ├── health/route.ts
│   ├── analyze/
│   │   ├── biomarkers/route.ts
│   │   ├── sample-qc/route.ts
│   │   └── [id]/
│   │       ├── status/route.ts
│   │       └── report/route.ts
│   ├── workflows/
│   │   ├── route.ts
│   │   └── [id]/
│   │       ├── status/route.ts
│   │       └── cancel/route.ts
│   └── biomarkers/
│       ├── panels/route.ts
│       └── [id]/features/route.ts
├── middleware.ts
└── lib/
    ├── ml-client.ts
    └── schemas/
        ├── workflows.ts
        └── omics.ts
```

---

## Phase 3: Workflow Orchestration Migration

### 3.1 Workflow engine (TypeScript)
- Rewrite `workflows/local_runner.py` as TypeScript workflow engine
- State machine pattern with step-based execution
- PostgreSQL-backed progress tracking (replaces `workflows/progress.py`)

### 3.2 Activity definitions
- Activities become typed async functions that call the Python ML service
- `ml_activities.py` → `src/lib/workflows/activities/ml.ts` (proxies to Python)
- `data_activities.py` → `src/lib/workflows/activities/data.ts` (some logic migrated, heavy ops proxied)
- `claude_activities.py` → `src/lib/workflows/activities/claude.ts` (uses Anthropic TS SDK directly)
- `dspy_activities.py` → `src/lib/workflows/activities/reasoning.ts` (rewritten with Anthropic SDK)
- `gpu_training_activities.py` → `src/lib/workflows/activities/training.ts` (proxies to Python)

### 3.3 Activity service
- `workflows/activity_service.py` → integrated into Next.js API routes
- No separate FastAPI service needed

**Files created:**
```
web/src/lib/workflows/
├── engine.ts          # Workflow state machine
├── progress.ts        # PostgreSQL progress tracking
├── types.ts           # Workflow type definitions
└── activities/
    ├── ml.ts          # ML service proxy
    ├── data.ts        # Data loading/processing
    ├── claude.ts      # Claude API (Anthropic TS SDK)
    ├── reasoning.ts   # Replaces DSPy modules
    └── training.ts    # Training service proxy
```

---

## Phase 4: DSPy → Anthropic TypeScript SDK

### 4.1 Replace DSPy modules with direct Claude calls
DSPy modules become structured prompt templates with the Anthropic TypeScript SDK:

| DSPy Module                          | TypeScript Replacement                   |
|--------------------------------------|------------------------------------------|
| `dspy_modules/biomarker_discovery.py`| `src/lib/reasoning/biomarker-discovery.ts`|
| `dspy_modules/sample_qc.py`         | `src/lib/reasoning/sample-qc.ts`         |
| `dspy_modules/feature_interpret.py`  | `src/lib/reasoning/feature-interpret.ts`  |
| `dspy_modules/regulatory_report.py`  | `src/lib/reasoning/regulatory-report.ts`  |
| `dspy_modules/metrics.py`           | `src/lib/reasoning/metrics.ts`            |
| `dspy_modules/compile.py`           | Not needed (DSPy compilation is Python-specific) |

### 4.2 Agent skills migration
- `agent_skills/biomarker_discovery.py` → `src/lib/agent-skills/biomarker-discovery.ts`
- `agent_skills/sample_qc.py` → `src/lib/agent-skills/sample-qc.ts`
- `agent_skills/literature_grounding.py` → `src/lib/agent-skills/literature-grounding.ts`
- `agent_skills/cross_omics_integration.py` → `src/lib/agent-skills/cross-omics-integration.ts`

These are orchestration functions that call the ML service + Claude API — fully migratable.

**Files created:**
```
web/src/lib/
├── reasoning/
│   ├── biomarker-discovery.ts
│   ├── sample-qc.ts
│   ├── feature-interpret.ts
│   ├── regulatory-report.ts
│   └── metrics.ts
└── agent-skills/
    ├── biomarker-discovery.ts
    ├── sample-qc.ts
    ├── literature-grounding.ts
    └── cross-omics-integration.ts
```

---

## Phase 5: Dashboard UI (New)

### 5.1 Pages
- `/` — Landing / overview dashboard
- `/workflows` — List running/completed workflows with status
- `/workflows/[id]` — Workflow detail with real-time progress (SSE/polling)
- `/analyze` — New analysis form (biomarkers or sample QC)
- `/biomarkers` — Panel browser with feature drill-down
- `/biomarkers/[id]` — Panel detail with feature importance charts
- `/results/[id]` — Analysis results with visualizations

### 5.2 Components (shadcn/ui + Recharts)
- Workflow status cards with progress bars
- Biomarker heatmap / feature importance bar charts
- Cross-omics distance matrix visualization
- Sample QC metrics dashboard
- Real-time workflow log viewer

### 5.3 Data fetching
- React Server Components for initial data
- SWR/React Query for client-side polling
- Server Actions for form submissions

**Files created:**
```
web/src/
├── app/
│   ├── page.tsx                    # Dashboard
│   ├── workflows/
│   │   ├── page.tsx                # Workflow list
│   │   └── [id]/page.tsx           # Workflow detail
│   ├── analyze/page.tsx            # New analysis
│   ├── biomarkers/
│   │   ├── page.tsx                # Panel list
│   │   └── [id]/page.tsx           # Panel detail
│   └── results/[id]/page.tsx       # Results view
└── components/
    ├── ui/                         # shadcn/ui primitives
    ├── workflow-card.tsx
    ├── biomarker-heatmap.tsx
    ├── feature-importance-chart.tsx
    ├── distance-matrix-viz.tsx
    ├── sample-qc-dashboard.tsx
    └── workflow-log-viewer.tsx
```

---

## Phase 6: Python ML Service Refactor

### 6.1 Consolidate Python into a single ML service
- Merge `core/` logic into a lean FastAPI microservice
- Expose endpoints:
  - `POST /ml/impute` — NMF imputation
  - `POST /ml/classify` — Ensemble classification (train + predict)
  - `POST /ml/features` — Multi-strategy feature selection
  - `POST /ml/match` — Cross-omics matching
  - `POST /ml/evaluate` — Model evaluation metrics
  - `POST /ml/synthetic` — Synthetic cohort generation
  - `POST /ml/pipeline` — Full pipeline execution
- Remove FastAPI web routes (moved to Next.js)
- Keep MCP server as separate service (unchanged)
- Keep training service as separate service (unchanged)

### 6.2 Slim down Python dependencies
- Remove `pydantic-settings`, web-related deps from ML service
- Keep only: numpy, pandas, scikit-learn, scipy, statsmodels, FastAPI (for ML API), joblib

### 6.3 New Dockerfile
- `Dockerfile.ml` — Minimal Python ML service image
- Multi-stage build, only ML dependencies

---

## Phase 7: Evaluation & Testing Migration

### 7.1 TypeScript tests (Vitest)
- Migrate all API route tests to Vitest
- Migrate workflow tests
- Migrate agent skill tests
- Migrate reasoning module tests
- Add E2E tests with Playwright for dashboard

### 7.2 Python tests (keep)
- Keep all `tests/test_core_*` tests for ML service
- Keep MCP tool tests
- Keep training tests

### 7.3 Integration tests
- Add cross-service integration tests (Next.js ↔ Python ML service)

---

## Phase 8: Docker Compose & Deployment

### 8.1 Updated docker-compose.yml
```yaml
services:
  # --- Infrastructure ---
  db:
    image: postgres:16-alpine
    ports: ["5432:5432"]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  # --- TypeScript (new) ---
  web:
    build:
      context: ./web
      dockerfile: Dockerfile
    ports: ["3000:3000"]
    depends_on: [db, redis, ml-service]
    environment:
      DATABASE_URL: postgresql://postgres:postgres@db:5432/precision_genomics
      ML_SERVICE_URL: http://ml-service:8000
      MCP_SERVER_URL: http://mcp-server:8080

  # --- Python ML (refactored) ---
  ml-service:
    build:
      context: .
      dockerfile: Dockerfile.ml
    ports: ["8000:8000"]
    depends_on: [db, redis]

  # --- Python MCP (unchanged) ---
  mcp-server:
    build:
      context: .
      dockerfile: Dockerfile.mcp
    ports: ["8080:8080"]
    depends_on: [db, redis]

  # --- Python Training (unchanged) ---
  training-worker:
    build:
      context: .
      dockerfile: Dockerfile.worker
    depends_on: [db, redis]
```

---

## Migration Order & Dependencies

```
Phase 1 (Scaffolding)     ← No dependencies, start here
    │
Phase 6 (Python ML svc)   ← Can run in parallel with Phase 1
    │
Phase 2 (API routes)      ← Depends on Phase 1 + Phase 6
    │
Phase 3 (Workflows)       ← Depends on Phase 2
    │
Phase 4 (DSPy → TS SDK)   ← Depends on Phase 2
    │
Phase 5 (Dashboard UI)    ← Depends on Phase 2
    │
Phase 7 (Testing)         ← Depends on all above
    │
Phase 8 (Docker/Deploy)   ← Final integration
```

---

## Tech Stack Summary

| Layer              | Current (Python)                  | Target (TypeScript)                    |
|--------------------|-----------------------------------|----------------------------------------|
| **Frontend**       | None                              | Next.js 15, React 19, Tailwind, shadcn |
| **API**            | FastAPI                           | Next.js API Routes (Route Handlers)    |
| **Validation**     | Pydantic                          | Zod                                    |
| **ORM**            | SQLModel                          | Prisma                                 |
| **Auth**           | Custom JWT middleware              | NextAuth.js or jose + middleware       |
| **LLM Client**     | anthropic (Python)                | @anthropic-ai/sdk (TypeScript)         |
| **Prompt Eng**     | DSPy                              | Direct Anthropic SDK calls             |
| **Workflows**      | Custom local runner               | TypeScript state machine               |
| **ML/Science**     | numpy, scipy, sklearn, torch      | **Stays in Python** (microservice)     |
| **MCP Server**     | mcp (Python SDK)                  | **Stays in Python** (unchanged)        |
| **Training**       | transformers, PEFT, TRL           | **Stays in Python** (unchanged)        |
| **Testing**        | pytest                            | Vitest + Playwright                    |
| **Containerization**| Docker multi-stage               | Docker multi-stage (Node + Python)     |

---

## What Stays in Python (unchanged)

1. **core/** — All ML algorithms (imputation, classification, feature selection, matching)
2. **mcp_server/** — MCP tool server (stdio/SSE transport)
3. **training/** — SLM fine-tuning, encoder training, DDP
4. **core/gpu_classifier.py** — cuML GPU classifier
5. **scripts/vertex_train_entrypoint.py** — Vertex AI training
6. **evals/** — Evaluation framework (calls ML code)

## What Migrates to TypeScript

1. **api/** → Next.js API Routes
2. **workflows/** → TypeScript workflow engine + activities
3. **dspy_modules/** → Anthropic TS SDK reasoning modules
4. **agent_skills/** → TypeScript agent skills
5. **Dashboard UI** (new) → React/Next.js pages + components

## Estimated File Count

| Category       | New TS Files | Migrated from Python |
|----------------|-------------|---------------------|
| API routes     | 11          | 6 Python files      |
| Schemas        | 3           | 2 Python files      |
| Workflows      | 8           | 11 Python files     |
| Reasoning      | 5           | 7 Python files      |
| Agent Skills   | 4           | 4 Python files      |
| UI Pages       | 7           | 0 (new)             |
| UI Components  | 8           | 0 (new)             |
| Tests          | 15          | 20 Python files     |
| Config/Infra   | 6           | 3 Python files      |
| **Total**      | **~67**     | **53 Python files** |
