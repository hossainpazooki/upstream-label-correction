"""The CLUE loop wired into the intent lifecycle's VERIFY step.

`mislabel_detection` is registered as an assurance eval: VERIFY generates a
synthetic cohort from the intent params, runs the improve step (detector
threshold tuning), and gates the intent on the tuned F1. Small, seeded cohorts
keep these deterministic.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("scipy")
pytest.importorskip("sklearn")

from intents.assurance import AssuranceLoop  # noqa: E402


def _intent(**overrides):
    params = {
        "n_samples": 30,
        "n_genes_proteomics": 150,
        "n_genes_rnaseq": 200,
        "mislabel_fraction": 0.20,
        "seed": 7,
    }
    params.update(overrides)
    return SimpleNamespace(intent_id="clue-test", params=params)


def test_mislabel_detection_is_registered():
    assert "mislabel_detection" in AssuranceLoop()._registry


async def test_verify_runs_tuned_detection_and_passes():
    results = await AssuranceLoop().evaluate(_intent(), (("mislabel_detection", 0.8),))

    assert "mislabel_detection" in results
    r = results["mislabel_detection"]
    assert r.name == "mislabel_detection"
    assert r.details.get("tuned") is True
    assert "best_threshold" in r.details
    # The tuned detector clears the 0.8 gate on this cohort.
    assert r.passed is True
    assert AssuranceLoop.all_passed(results) is True


async def test_untuned_path_available_when_requested():
    results = await AssuranceLoop().evaluate(_intent(tune_detector=False), (("mislabel_detection", 0.5),))
    r = results["mislabel_detection"]
    assert r.details.get("tuned") is not True
    assert 0.0 <= r.score <= 1.0


async def test_unreachable_threshold_fails_the_gate():
    results = await AssuranceLoop().evaluate(_intent(), (("mislabel_detection", 1.01),))
    assert results["mislabel_detection"].passed is False
    assert AssuranceLoop.all_passed(results) is False
