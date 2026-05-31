# Temporal-Equivalent Workflow Functionality

**Status:** Implemented — May 2026
**Scope:** `intent-controller/internal/workflow/` (Go workflow engine)

## Why this exists

The platform ran Temporal workflows early on, then migrated off them (Temporal →
GCP Workflows → the current in-process Go engine; see
[archive/TEMPORAL_TO_GCP_WORKFLOWS_MIGRATION.md](archive/TEMPORAL_TO_GCP_WORKFLOWS_MIGRATION.md)).
A later assessment asked whether Temporal should be **re-added**. The conclusion:
**no** — the old workflows never used Temporal's durability/replay, signals, or
continue-as-new; the only Temporal features they actually relied on were
**automatic retries** and **parallel fan-out**, and the in-process Go engine had
dropped both. Re-introducing a full orchestration server (≈ the ~$98/mo VM the
platform deliberately eliminated, plus a third orchestration system) to recover
two features was not worth it.

This document records the alternative that was implemented: recovering those two
capabilities **directly in the Go engine**, at near-zero infrastructure cost and
zero new operational surface.

## What was implemented

### 1. Retries with backoff

`RetryPolicy` + `runWithRetry` (`internal/workflow/engine_exec.go`).

- `DefaultRetryPolicy()` — 3 attempts, exponential backoff 500ms → 10s cap, ×2.
- Every phase runs through `runWithRetry`, so a transient activity failure (e.g.
  an ML-service blip) is retried instead of failing the whole workflow.
- Backoff waits honour context cancellation (`select` on `ctx.Done()`), so a
  cancelled workflow stops promptly instead of sleeping out the backoff.
- The policy lives on the `Engine` (`Engine.retryPolicy`), set in `NewEngine`.

### 2. Parallel fan-out

`Phase.Parallel []PhaseFunc` + `runFanOut` (`internal/workflow/engine.go`,
`engine_exec.go`).

- A phase can now declare `Parallel` branches instead of a single `Activity`.
  When set, all branches run **concurrently** (each independently retried) and
  their result maps are **merged in branch order** (later branch wins on key
  collision, so the merge is deterministic).
- If any branch errors, the lowest-indexed error is returned and no partial
  result is produced.
- `runPhase` dispatches: `Parallel` set → `runFanOut`; otherwise single
  `Activity` → `runWithRetry`. Existing single-activity phases are unchanged.

### 3. Fan-out applied to biomarker discovery

`internal/workflow/phases.go` + `registerDefaults` (`engine.go`).

The `biomarker_discovery` workflow's `imputation` and `feature_selection` phases
previously looped over modalities **sequentially**
(`for _, mod := range modalities`). They now **fan out**: one branch per modality
(`proteomics`, `rnaseq`) via `fanOutModalities(imputeModality)` and
`fanOutModalities(selectFeaturesForModality)`. Each branch returns a
modality-keyed map (`{proteomics: ...}` / `{rnaseq: ...}`) so the merged result
keeps the exact `{proteomics, rnaseq}` shape the downstream `integration` phase
already consumes — a drop-in change. This restores the per-modality parallelism
the COSMO pipeline had under Temporal.

> Note: the fan-out modality set is fixed to `proteomics`/`rnaseq` for the
> biomarker workflow (`biomarkerModalities`). The sequential `phaseImpute` /
> `phaseSelectFeatures` (which honour a dynamic `modalities` param) remain in
> use by the `cosmo_pipeline` workflow.

### 4. Durable execution — resume from checkpoint

`remainingPhases`, `Engine.Recover` (`internal/workflow/engine.go`), `Params`
persistence (`internal/models/workflow.go`, `internal/store/`).

- Each workflow's input `params` is now persisted on the `workflow_executions`
  row (new `params` JSONB column, added via `CREATE TABLE` plus an idempotent
  `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`), so a workflow can be reconstructed
  after a restart.
- `Engine.Recover(ctx)` sweeps for workflows left in `running` by a dead process
  and **resumes each from its last completed phase** — `remainingPhases(def.Phases,
  wf.PhasesCompleted)` drops the already-done phases, and the shared `runPhases`
  core persists progress identically to a fresh run. Phases are idempotent, so
  re-running the in-flight phase is safe.
- A `running` workflow whose type is no longer registered is marked `failed`
  rather than left hanging.
- Wired into `cmd/server/main.go` as a non-blocking goroutine right after
  migrations.

This is **checkpoint-resume**, not Temporal's event-sourced deterministic replay
— lighter, and sufficient because phases are idempotent. See limits for what it
still doesn't cover.

## Mapping to Temporal

| Temporal feature | Used by old workflows? | Recovered here |
|---|---|---|
| `RetryPolicy` (automatic retries) | ✅ all 3 workflows | ✅ `RetryPolicy` + `runWithRetry` |
| Parallel fan-out (`parallel for` / `asyncio.gather`) | ✅ biomarker, 3 modalities | ✅ `Phase.Parallel` + `runFanOut` |
| Saga / compensation | partial (hand-rolled) | not reintroduced (was framework-independent) |
| Durable replay / crash recovery | ❌ not needed then | 🟡 partial — resume from last completed phase (`Engine.Recover`); checkpoint-resume, not event-sourced replay; no cross-replica lease yet |
| Signals / queries | ❌ | ⭕ not provided |
| continue-as-new / heartbeats / child workflows / versioning | ❌ | ⭕ not provided |

## Limits — what this does *not* provide

Single-process **crash recovery now works** (`Engine.Recover` resumes `running`
workflows from their last completed phase). Two things it still does *not* cover:

- **Cross-replica at-most-once.** With more than one controller replica, two
  could recover the same workflow and run the remaining phases twice. A claim/
  lease (`SELECT ... FOR UPDATE SKIP LOCKED` or a `worker_id` + heartbeat) is
  required before scaling past one replica. This is "step 3" and is not yet built.
- **Deterministic replay of non-idempotent steps.** Resume relies on phases being
  idempotent; it re-runs the interrupted phase rather than replaying recorded
  results. Non-idempotent activities would need Temporal-style event sourcing.

**Reconsider Temporal** only if a new requirement appears that this model
genuinely can't serve:

- workflows running hours-to-days,
- human-in-the-loop approval (signals),
- strict crash-recovery / exactly-once on **non-idempotent** steps.

If that happens, start with **Temporal Cloud Starter** (~$25–50/mo), not a
self-hosted server — it avoids re-incurring the VM and version/monitoring burden
that drove the original exit.

## Tests

- `internal/workflow/engine_exec_test.go` — retries (success-after-failures,
  exhaustion, single-attempt, cancellation interrupts backoff) and fan-out
  (merge, deterministic collision, error propagation, a barrier-based
  concurrency proof).
- `internal/workflow/engine_test.go::TestBiomarkerDiscoveryFansOutModalities` —
  asserts the biomarker phases are wired as fan-out (one branch per modality).
- CI runs `go test -race ./...` (the `go-build` job in `.github/workflows/ci.yml`)
  so the concurrency is race-checked on every push.

## Files

| File | Contents |
|---|---|
| `internal/workflow/engine_exec.go` | `RetryPolicy`, `DefaultRetryPolicy`, `runWithRetry`, `runPhase`, `runFanOut` |
| `internal/workflow/engine.go` | `Phase.Parallel`, `Engine.retryPolicy`, `execute()` via `runPhase`, biomarker fan-out wiring |
| `internal/workflow/phases.go` | `biomarkerModalities`, `imputeModality`, `selectFeaturesForModality`, `fanOutModalities` |
| `internal/workflow/engine_exec_test.go`, `engine_test.go` | tests |
