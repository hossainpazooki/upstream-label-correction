#!/usr/bin/env python3
"""End-to-end demo of CLUE -- the closed-loop measurement instrument.

CLUE manufactures fidelity-verified synthetic cohorts with a KNOWN mislabel
answer key, runs the cross-omics detector against it, and closes a
generate -> measure -> improve -> regenerate loop to find the detector's
*operating frontier*: the hardest corruption rate it still clears.

This demo drives the real ``CLUELoop`` and prints a rate -> F1 table plus the
frontier. Every number here is measured on SYNTHETIC cohorts -- it is the
detector's behaviour against planted ground truth, NOT real-world clinical
performance (see docs/GAP_AUDIT.md, gap #1).

Usage:
    python scripts/demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Running ``python scripts/demo.py`` puts scripts/ on sys.path, not the repo
# root, so ``import core`` would fail. Put the repo root first explicitly.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> None:
    from clue.loop import CLUELoop

    print("=" * 70)
    print("CLUE -- Closed-Loop Upstream Error-correction (synthetic demo)")
    print("=" * 70)
    print(
        "\nGenerate fidelity-verified cohorts with a known mislabel key, run the\n"
        "cross-omics detector, and escalate the corruption rate until the tuned\n"
        "detector can no longer clear the target F1 -- its operating frontier.\n"
    )

    target_f1 = 0.80
    loop = CLUELoop(
        target_f1=target_f1,
        start_fraction=0.05,
        fraction_step=0.05,
        max_fraction=0.40,
        # Small cohorts keep the demo fast (<~30s); the full presets live in
        # SyntheticCohortGenerator.integration()/.benchmark().
        n_samples=60,
        n_genes_proteomics=800,
        n_genes_rnaseq=1500,
        seed=42,
    )

    print(f"[run] generate -> measure -> improve, target F1 = {target_f1:.2f}\n")
    result = loop.run()

    print(f"  {'rate':>6}  {'tau*':>5}  {'precision':>9}  {'recall':>6}  {'F1':>5}  pass")
    print(f"  {'-' * 6}  {'-' * 5}  {'-' * 9}  {'-' * 6}  {'-' * 5}  ----")
    for r in result.rounds:
        print(
            f"  {r.mislabel_fraction:>5.0%}  {r.best_threshold:>5.2f}  "
            f"{r.precision:>9.2f}  {r.recall:>6.2f}  {r.f1:>5.2f}  "
            f"{'yes' if r.passed else 'no'}"
        )

    print()
    if result.frontier_fraction is not None:
        print(
            f"  operating frontier: {result.frontier_fraction:.0%} "
            f"-- hardest corruption rate the tuned detector still cleared "
            f"(F1 >= {target_f1:.2f})"
        )
    else:
        print(f"  operating frontier: none -- detector did not clear F1 >= {target_f1:.2f} even at the starting rate")

    print("\n" + "=" * 70)
    print(
        "Synthetic measurement only. NOT real-data performance -- see\n"
        "docs/GAP_AUDIT.md (gap #1) and docs/TRANSFER_VALIDATION_RUN.md."
    )
    print("=" * 70)


if __name__ == "__main__":
    main()
