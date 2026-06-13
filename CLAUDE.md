# upstream-label-correction (CLUE)

**CLUE — Closed-Loop Upstream Error-correction.** An agentic loop that generates
fidelity-verified synthetic multi-omics cohorts to measure — and improve —
label-error detection at corruption rates real data can't probe. Built on the
precisionFDA NCI-CPTAC Multi-omics Sample Mislabeling Correction Challenge.

> Global working rules (file-op style, git default, **adversarial verification**,
> workflow discipline, shared agents) are loaded from `~/.claude/` — they are not
> repeated here. This file holds only what's specific to CLUE.

Authoritative docs to read first: [`README.md`](README.md). The verification and
honesty rules in `~/.claude/rules/verification-and-honesty.md` matter
especially here — the whole point of the project is measuring a detector against
ground truth, so empirical claims must be recomputed and refuted before they're
written down.

## Architecture (polyglot)

- **`intent-controller/` (Go)** — the intent lifecycle + workflow engine. It is
  the **single authority for `ACHIEVED`**: `verify()` runs each `IntentSpec` eval
  criterion via the ML service and gates on the aggregate. Multi-replica-safe
  (Postgres `FOR UPDATE SKIP LOCKED` lease).
- **`core/` + `evals/` + `clue/` (Python)** — the ML engine
  (`SyntheticCohortGenerator`, cross-omics detector), the eval stack, and the
  closed loop (`CLUELoop`).
- **`ml_service/` (FastAPI)** — `/ml/evaluate` routes `eval_name` → the matching
  eval runner; this is the controller↔ML seam.
- **`web/` (Next.js)** + **`infra-ts/` (Pulumi)** — dashboard/MCP and GCP IaC.

## Commands

- Go: `cd intent-controller && go build ./... && go vet ./... && go test ./...`
  (integration tests are behind `-tags=integration` and need Postgres via `DATABASE_URL`).
- Python: `python -m pytest` · lint `python -m ruff check <paths>`.

## Security / integrity model — read [`docs/GAP_AUDIT.md`](docs/GAP_AUDIT.md)

The verification gate has been hardened across an 8-finding audit (read through
the `correct-shaped-lies` red-team lens). It is now **server-authoritative**:
authenticated control plane (`X-Service-Token`), server-pinned cohort params (no
caller seed-shopping), a dual decorrelated fidelity detector, and a Go-side
consistency check that won't trust a self-inconsistent `passed`. `GAP_AUDIT.md`
is the authoritative per-finding record.

## Gotchas (durable)

- **Determinism is a hard invariant** — all randomness flows through a seeded
  `PCG64` stream (generator) or `RandomState(42)` (detector). Don't introduce
  global-`np.random` use; it breaks byte-identical reproduction.
- **The gate validates synthetic self-consistency, NOT real-world performance.**
  That gap (#1, no held-out oracle) is **blocked on real data, not code**:
  `data/raw/` holds real precisionFDA/CPTAC data and is **gitignored**
  (`*.tsv`/`*.csv`/`*.json`) so that data never enters history.
  `evals/transfer_validation.py` is a `[PROPOSED]` seam that activates when the
  molecular matrices land — see `data/raw/README.md`. Never report a synthetic
  number as real-data performance.
- **Windows-local** is cp1252 + CRLF: keep `print()`/stdout ASCII; run `gofmt -w`
  only on files you changed (it flags untouched files for CRLF).
