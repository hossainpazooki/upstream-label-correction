# Learnings

Durable, hard-won lessons from working on CLUE — things that cost a red CI run, a
wrong assumption, or an adversarial round to discover. Read alongside
[`CLAUDE.md`](CLAUDE.md) (rules/commands) and [`docs/GAP_AUDIT.md`](docs/GAP_AUDIT.md)
(the gate-hardening record).

## Verification & CI

- **CI lint runs `ruff check` AND `ruff format --check`.** A passing `ruff check`
  does *not* catch formatting drift. Running only `ruff check` locally let
  unformatted `ml_service/main.py` through and turned **3 CI runs red** (the
  `lint` job, not tests). Always run both before handing over a commit.
- **Don't trust a self-reported success** — a workflow's, a subagent's, or your
  own. Re-run the load-bearing check and recompute empirical numbers from the raw
  source at the point of claiming them. Every "green" this session was
  independently re-verified; the skeptic pass repeatedly overturned plausible
  assumptions (e.g. that `load_dataset` existed, that `benchmark_comparison`'s
  reference was external).
- **Keep CI action majors current.** GitHub forces Node-20 JS actions onto Node
  24 (June 16, 2026); bump `actions/*` to their Node-24 majors proactively rather
  than waiting for the forced migration to maybe break a run.

## Determinism (a hard invariant here)

- **Route all randomness through a seeded stream** — `PCG64` (generator) /
  `RandomState(42)` (detector). A test asserting an exact `recall==1.0`
  (`test_detects_all_molecular_swaps`) passed on Windows but **flaked on Linux
  CI** via float/BLAS ordering until the cross-omics iteration was made
  deterministic. Global `np.random` use breaks byte-identical reproduction and
  makes results test-order-dependent.

## The gate's validity boundary (correct-shaped-lies lens)

- **Synthetic self-scoring is not real-world validation.** The gate measures the
  detector against the generator's own planted ground truth, so ACHIEVED means
  self-consistent, not correct. State this boundary wherever the gate is
  described; never report a synthetic number as real-data performance.
- **A "held-out" cohort from the same generator is not independent.** Disjoint
  seeds still plant identical signal geometry, so threshold selection on a sibling
  cohort removes per-cohort-noise overfit but retains shared-structure optimism.
  Genuine independence needs a real oracle with an externally-authored key (gap #1)
  — it was never closeable *in code*, only by getting real organizer-keyed data,
  which has now arrived for the train partition (F1 0.914 — see the gap-#1 closure
  note below).
- **Across a trust boundary, corroborate — don't trust a boolean you can't
  recompute.** The Go gate now cross-checks the ML service's self-reported
  `passed` against the response's `score`/`threshold` and fails closed on
  inconsistency. Make gates server-authoritative (auth, server-pinned inputs).
- **A number can be recomputed-from-raw and still be a correct-shaped lie — if
  you verified the wrong thing.** A workflow scored the detector on real COSMO
  (Zhang-lab) matrices and produced a fixed-0.5 micro-F1 of 0.85, verified twice
  from raw and via a separate code path. But the "answer key" was a label-shuffle
  the scoring script wrote *itself* (the public tarball ships base matrices, **no
  keys** — the premise was wrong). Real biology made the *features* independent of
  CLUE's generator; it did **not** make the *oracle* independent — we still chose
  the corruption, so gap #1's circularity was **relocated, not broken**, and
  rnaseq-only injection ⇒ recall 1.0 ⇒ optimistic. Lesson: scrutinize what a
  metric *means*, not just whether its arithmetic checks out. "Independent of our
  generator" is not "independent of us." (Holding the threshold fixed at 0.5 to
  avoid gap #2 was correct — it just wasn't the thing that needed guarding.)
- **An external error MODEL is not an external KEY — and a swept distribution
  beats a single optimistic point.** Run 1 injected one easy error type
  (rnaseq-only label swaps) at one fraction/seed and got recall 1.0 / F1 ~0.85 —
  an optimistic point estimate that read as "works." Run 2 instead followed
  COSMO's *published* swap/duplicate/shift taxonomy across both molecular
  modalities and swept a 3x3x3 grid (fractions x seeds x cohorts), reporting a
  distribution: fixed-0.5 F1 = 0.805 mean, range [0.559, 0.939]; precision drops
  on a real-data false-positive floor that single-type/single-point injection had
  hidden. Two lessons: (1) report a distribution over a documented grid, never one
  cherry-picked point, and mix realistic error types rather than the easiest one;
  (2) adopting an outside party's error *MODEL* makes the recipe principled but
  does **not** make the *key* independent — *we* still realize which samples get
  corrupted, so it stays a robustness characterization, not independent validation
  or a gap-#1 closure (the only closure is the gated precisionFDA clinical key).
- **Real public multi-omics matrices need defensive ingestion.** The COSMO
  tarball had no keys/README/simulated cohorts the premise assumed (verify the
  data, not the spec); matrices are genes-as-rows so **transpose** before the
  detector's samples x genes contract; proteome NaN ran ~21% (Chick) vs ~0%
  (CCRCC) and correlates with worse precision; an O(n^2 * genes) Spearman forces
  deterministic gene/sample caps — cap with a seeded `RandomState` and **log**
  every cap and every skipped cohort (no silent truncation).
- **Gap #1's train oracle is now CLOSED — and the "missing" data was publicly
  mirrored all along.** The blocker for independent validation was always the real
  precisionFDA molecular matrices (`train_pro`/`train_rna`), assumed absent from any
  public repo. They were in fact in a participant's public repo
  (`ACHG2018/fda-mislabeling-challenge` `challenge_data/`). With them in `data/raw/`,
  `transfer_validation('train')` scores **F1 0.914** (precision 0.842, recall 1.000;
  TP 16/FP 3/FN 0, fixed 0.5) against the **organizers'** `sum_tab_2.csv` key — a key
  independent of both us and the generator, so this is the genuine independent
  validation the COSMO self-injected run (0.805) could never be. Two lessons:
  (1) before declaring data "unavailable," search the public participant/mirror
  ecosystem of a *public competition*, not just the official portal — the blocker
  was where we looked, not whether the data exists; (2) "independent of our
  generator" finally became "independent of us" only when the *key* came from a
  third party. **Still open:** the *blind* precisionFDA test oracle (withheld
  labels) and a provenance cross-check of the mirror against the official source.
  See [`docs/TRANSFER_VALIDATION_RUN.md`](docs/TRANSFER_VALIDATION_RUN.md) Run 3.

## Workflow / process

- **Fan-out → refute → synthesize** is the default shape for design/audit work:
  parallel proposers, an adversarial skeptic that recomputes from raw sources,
  then a synthesizer. Close multi-file builds with an integration agent that runs
  the real pipeline — then verify its evidence yourself.
- **Bound adversarial/verification agents.** An unbounded skeptic told to recompute
  "at the pinned config for several seeds" generated full-size cohorts in a loop
  and wedged for ~38 min. Scale-invariant checks should use a small fast config
  with an explicit cap.
- **Commits:** one `git add` per line, ASCII single-line message, **no
  `Co-Authored-By`/attribution trailer** (per `~/.claude/rules/git.md`). The user
  runs commits; hand over paste-safe commands.
