# Pulumi Migration Plan: Go Intent Controller + TypeScript Frontend

## Guiding Principle

Each step leaves the platform functional. No big-bang rewrites.

---

## Final Architecture

| Service | Language | Port | Responsibility |
|---------|----------|------|----------------|
| `web` | TypeScript | 3000 | Dashboard, API routes, agent skills, LLM calls |
| `intent-controller` | Go | 8090 | Intent lifecycle, workflows, activities, Pulumi |
| `ml-service` | Python | 8000 | ML algorithms, evals, DSPy proxy |
| `mcp-server` | Python | 8080 | MCP tools for Claude |

```
┌──────────────────────────────────────────────────────────────────────┐
│                     Next.js App (TypeScript) :3000                    │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────────────┐ │
│  │  Dashboard UI │  │  API Routes  │  │  Agent Skills / Reasoning   │ │
│  │  (React/RSC)  │  │  /api/*      │  │  (Anthropic TS SDK)         │ │
│  └──────────────┘  └──────┬───────┘  └─────────────────────────────┘ │
│                           │ proxy intent/workflow ops                  │
└───────────────────────────┼──────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│              Go Intent Controller :8090                                │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────────────┐ │
│  │  Intent       │  │  Workflow     │  │  Activity Dispatch          │ │
│  │  Lifecycle    │  │  Engine       │  │  (HTTP → ML service)        │ │
│  └──────────────┘  └──────────────┘  └─────────────────────────────┘ │
│  ┌──────────────┐                                                     │
│  │  Pulumi       │  ← Native Go SDK, Automation API                   │
│  │  Integration  │                                                     │
│  └──────────────┘                                                     │
└──────────────────────────────────────────────────────────────────────┘
        │                           │
        ▼                           ▼
┌────────────────┐      ┌──────────────────────────────────────────────┐
│  PostgreSQL 16  │      │            Python ML Service :8000            │
│                 │      │  impute | classify | features | match | eval  │
└────────────────┘      └──────────────────────────────────────────────┘
```

---

## Migration 1: Go — Intent + Workflow (replaces 3 Python processes with 1 binary)

### Scope

**What moves**: `intents/` (8 files), `workflows/` (11 files), `infra/automation/` (3 files) — ~2,753 lines of Python to one Go service.

### Go Package Layout

```
intent-controller/
├── cmd/
│   └── server/
│       └── main.go              # HTTP server bootstrap
├── internal/
│   ├── models/
│   │   ├── intent.go            # Intent, IntentSpec, IntentStatus
│   │   ├── workflow.go          # WorkflowRun, WorkflowStep
│   │   └── activity.go          # ActivityResult, ActivityType
│   ├── store/
│   │   ├── postgres.go          # pgx connection pool + queries
│   │   ├── intent_repo.go       # CRUD for intents
│   │   └── workflow_repo.go     # CRUD for workflow runs
│   ├── intent/
│   │   ├── manager.go           # Create / Get / List / Cancel
│   │   ├── reconciler.go        # Watch loop: intent → desired state
│   │   └── validator.go         # Schema validation for IntentSpec
│   ├── workflow/
│   │   ├── engine.go            # Step-based state machine
│   │   ├── runner.go            # Execute workflow, manage transitions
│   │   └── progress.go          # Progress tracking (replaces workflows/progress.py)
│   ├── activity/
│   │   ├── dispatcher.go        # HTTP dispatch to Python ML service
│   │   ├── ml.go                # ML activity definitions
│   │   ├── data.go              # Data loading activities
│   │   └── pulumi.go            # Pulumi Automation API activities
│   └── api/
│       ├── router.go            # Chi/Gin router setup
│       ├── intent_handler.go    # REST handlers for /intents
│       ├── workflow_handler.go  # REST handlers for /workflows
│       └── middleware.go        # Auth, logging, request ID
├── go.mod
├── go.sum
├── Dockerfile
└── Makefile
```

### REST API

```
POST   /api/v1/intents              Create intent
GET    /api/v1/intents              List intents
GET    /api/v1/intents/:id          Get intent
DELETE /api/v1/intents/:id          Cancel intent
GET    /api/v1/intents/:id/status   Intent status + workflow progress

POST   /api/v1/workflows            Trigger workflow
GET    /api/v1/workflows/:id        Get workflow run
POST   /api/v1/workflows/:id/cancel Cancel workflow run
GET    /api/v1/workflows/:id/steps  List workflow steps with status

GET    /healthz                     Liveness
GET    /readyz                      Readiness (DB + ML service reachable)
```

### Steps

| Step | Description | Gate |
|------|-------------|------|
| 1 | Scaffold Go module, models, store (pgx), Dockerfile | `go build` passes, migrations run |
| 2 | Intent lifecycle: manager, reconciler, validator | Unit tests pass for CRUD + validation |
| 3 | Workflow engine: state machine, runner, progress | Unit tests pass, state transitions correct |
| 4 | Activity dispatch: HTTP calls to Python ML service | Integration test: Go → Python round-trip |
| 5 | REST API: handlers, router, middleware | `curl` smoke tests pass, OpenAPI spec matches |
| 6 | Parallel run: Go + Python side-by-side, compare outputs | Parity validation: same inputs → same results |
| 7 | Decommission: remove `intents/`, `workflows/`, `infra/automation/` | CI green, no Python workflow imports remain |

---

## Migration 2: TypeScript — Frontend + API + Agent Skills

### Key Change from Original Plan

Phase 3 (workflow engine) is **removed** from TS migration. Workflows go to Go. The TypeScript API routes proxy to the Go service for workflow/intent operations.

### What Changes in `web/`

- **Remove**: `lib/workflows/` and `ml-queue.ts` (Go handles this)
- **Add**: `intent-client.ts` (HTTP client for Go service)
- **Add**: `lib/reasoning/` (DSPy → Anthropic SDK)
- **Add**: Dashboard components + tests

### Updated File Structure

```
web/src/
├── app/
│   ├── layout.tsx
│   ├── page.tsx                          # Dashboard
│   ├── workflows/
│   │   ├── page.tsx                      # Workflow list
│   │   └── [id]/page.tsx                 # Workflow detail
│   ├── analyze/page.tsx                  # New analysis
│   ├── biomarkers/
│   │   ├── page.tsx                      # Panel list
│   │   └── [id]/page.tsx                 # Panel detail
│   ├── results/[id]/page.tsx             # Results view
│   └── api/
│       ├── health/route.ts
│       ├── analyze/
│       │   ├── biomarkers/route.ts
│       │   ├── sample-qc/route.ts
│       │   └── [id]/
│       │       ├── status/route.ts
│       │       └── report/route.ts
│       ├── intents/                      # Proxy to Go service
│       │   ├── route.ts
│       │   └── [id]/
│       │       ├── route.ts
│       │       └── status/route.ts
│       ├── workflows/                    # Proxy to Go service
│       │   ├── route.ts
│       │   └── [id]/
│       │       ├── status/route.ts
│       │       └── cancel/route.ts
│       └── biomarkers/
│           ├── panels/route.ts
│           └── [id]/features/route.ts
├── lib/
│   ├── prisma.ts
│   ├── ml-client.ts                      # HTTP client → Python ML
│   ├── intent-client.ts                  # HTTP client → Go intent-controller
│   ├── schemas/
│   │   ├── workflows.ts
│   │   └── omics.ts
│   ├── reasoning/
│   │   ├── biomarker-discovery.ts
│   │   ├── sample-qc.ts
│   │   ├── feature-interpret.ts
│   │   ├── regulatory-report.ts
│   │   └── metrics.ts
│   └── agent-skills/
│       ├── biomarker-discovery.ts
│       ├── sample-qc.ts
│       ├── literature-grounding.ts
│       └── cross-omics-integration.ts
├── components/
│   ├── ui/                               # shadcn/ui primitives
│   ├── workflow-card.tsx
│   ├── biomarker-heatmap.tsx
│   ├── feature-importance-chart.tsx
│   ├── distance-matrix-viz.tsx
│   ├── sample-qc-dashboard.tsx
│   └── workflow-log-viewer.tsx
└── middleware.ts
```

### Steps

| Step | Description | Gate |
|------|-------------|------|
| 1 | Scaffold fixes: Prisma, Tailwind, shadcn, tsconfig | `npm run build` passes |
| 2 | API routes: proxy intent/workflow to Go, direct ML routes | Integration tests pass (TS → Go → Python) |
| 3 | Reasoning modules: DSPy → Anthropic TS SDK | Unit tests pass, output parity with DSPy |
| 4 | Agent skills: migrate 4 Python skills to TypeScript | Skill tests pass |
| 5 | Dashboard UI: pages + components | Playwright E2E tests pass |
| 6 | Decommission: remove FastAPI web routes, Python agent skills | CI green, no Python API imports remain |

---

## Cross-Migration Dependency

```
Go Step 5 (REST API running)
    │
    ▼
TS Step 2 (API routes that proxy to Go)
```

This is the **only hard coupling**. Go must have its REST API operational before TypeScript API routes can proxy intent/workflow operations.

---

## Integration Contracts

### TypeScript → Go (intent-client.ts)

```typescript
// web/src/lib/intent-client.ts
interface IntentClient {
  createIntent(spec: IntentSpec): Promise<Intent>
  getIntent(id: string): Promise<Intent>
  listIntents(filters?: IntentFilter): Promise<Intent[]>
  cancelIntent(id: string): Promise<void>
  getIntentStatus(id: string): Promise<IntentStatus>

  triggerWorkflow(req: WorkflowRequest): Promise<WorkflowRun>
  getWorkflow(id: string): Promise<WorkflowRun>
  cancelWorkflow(id: string): Promise<void>
  getWorkflowSteps(id: string): Promise<WorkflowStep[]>
}
```

### Go → Python ML (activity/dispatcher.go)

```go
// HTTP calls from Go to Python ML service
type MLClient interface {
    Impute(ctx context.Context, req ImputeRequest) (*ImputeResult, error)
    Classify(ctx context.Context, req ClassifyRequest) (*ClassifyResult, error)
    SelectFeatures(ctx context.Context, req FeatureRequest) (*FeatureResult, error)
    MatchOmics(ctx context.Context, req MatchRequest) (*MatchResult, error)
    Evaluate(ctx context.Context, req EvalRequest) (*EvalResult, error)
    RunPipeline(ctx context.Context, req PipelineRequest) (*PipelineResult, error)
}
```

### Python ML Service Endpoints (unchanged)

```
POST /ml/impute       — NMF imputation
POST /ml/classify     — Ensemble classification
POST /ml/features     — Multi-strategy feature selection
POST /ml/match        — Cross-omics matching
POST /ml/evaluate     — Model evaluation metrics
POST /ml/pipeline     — Full pipeline execution
```

---

## Updated docker-compose.yml

```yaml
services:
  # --- Infrastructure ---
  db:
    image: postgres:16-alpine
    ports: ["5432:5432"]
    environment:
      POSTGRES_DB: precision_genomics
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  # --- Go (new) ---
  intent-controller:
    build:
      context: ./intent-controller
      dockerfile: Dockerfile
    ports: ["8090:8090"]
    depends_on: [db, ml-service]
    environment:
      DATABASE_URL: postgresql://postgres:postgres@db:5432/precision_genomics
      ML_SERVICE_URL: http://ml-service:8000
      PORT: "8090"

  # --- TypeScript (new) ---
  web:
    build:
      context: ./web
      dockerfile: Dockerfile
    ports: ["3000:3000"]
    depends_on: [db, redis, ml-service, intent-controller]
    environment:
      DATABASE_URL: postgresql://postgres:postgres@db:5432/precision_genomics
      ML_SERVICE_URL: http://ml-service:8000
      INTENT_CONTROLLER_URL: http://intent-controller:8090
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

## CI/CD Pipeline Updates

```yaml
jobs:
  # --- Python (existing, scoped down) ---
  python-lint-test:
    steps:
      - ruff check core/ ml_service/ mcp_server/ training/ evals/
      - pytest tests/test_core_* tests/test_ml_* tests/test_mcp_*

  # --- Go (new) ---
  go-lint-test:
    steps:
      - cd intent-controller && go vet ./...
      - cd intent-controller && golangci-lint run
      - cd intent-controller && go test ./...

  # --- TypeScript (new) ---
  ts-lint-test:
    steps:
      - cd web && npm ci
      - cd web && npm run lint
      - cd web && npm run type-check
      - cd web && npm run test
      - cd web && npm run build

  # --- Integration ---
  integration:
    needs: [python-lint-test, go-lint-test, ts-lint-test]
    steps:
      - docker compose up -d
      - run parity validation tests
      - run Playwright E2E tests
```

---

## Test Strategy

### Parity Validation Gates

Before decommissioning any Python code, run parity tests:

1. **Intent parity**: Same intent spec → same intent created (Go vs Python)
2. **Workflow parity**: Same workflow → same step sequence and results (Go vs Python)
3. **API parity**: Same HTTP request → same response shape and status codes
4. **Reasoning parity**: Same prompt → comparable quality output (TS SDK vs DSPy)

### Test Distribution

| Service | Framework | Coverage Target |
|---------|-----------|----------------|
| Go intent-controller | `go test` | Intent CRUD, workflow state machine, activity dispatch |
| TypeScript web | Vitest | API routes, reasoning modules, agent skills, components |
| TypeScript E2E | Playwright | Dashboard flows, workflow monitoring |
| Python ML | pytest | ML algorithms, MCP tools, training |
| Integration | docker compose + scripts | Cross-service round-trips, parity validation |

---

## What Stays in Python (unchanged)

1. **core/** — All ML algorithms (imputation, classification, feature selection, matching)
2. **mcp_server/** — MCP tool server (stdio/SSE transport)
3. **training/** — SLM fine-tuning, encoder training, DDP
4. **core/gpu_classifier.py** — cuML GPU classifier
5. **scripts/vertex_train_entrypoint.py** — Vertex AI training
6. **evals/** — Evaluation framework (calls ML code)

## What Migrates to Go

1. **intents/** → Go intent lifecycle + reconciler
2. **workflows/** → Go workflow engine + runner + activities
3. **infra/automation/** → Go Pulumi Automation API (native SDK)

## What Migrates to TypeScript

1. **api/** → Next.js API Routes (proxy to Go for intents/workflows)
2. **dspy_modules/** → Anthropic TS SDK reasoning modules
3. **agent_skills/** → TypeScript agent skills
4. **Dashboard UI** (new) → React/Next.js pages + components

## Estimated File Count

| Category | New Files | Migrated from Python |
|----------|-----------|---------------------|
| Go models/store | 6 | 8 Python files (intents/) |
| Go intent/workflow | 7 | 11 Python files (workflows/) |
| Go activity/api | 8 | 3 Python files (infra/automation/) |
| TS API routes | 13 | 6 Python files (api/) |
| TS schemas | 3 | 2 Python files |
| TS reasoning | 5 | 7 Python files (dspy_modules/) |
| TS agent skills | 4 | 4 Python files (agent_skills/) |
| TS UI pages | 7 | 0 (new) |
| TS UI components | 8 | 0 (new) |
| TS tests | 15 | 20 Python files |
| Config/infra | 8 | 3 Python files |
| **Total** | **~84** | **64 Python files** |
