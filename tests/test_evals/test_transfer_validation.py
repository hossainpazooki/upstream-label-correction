"""Tests for the [PROPOSED] real-data transfer-validation seam (gap #1).

The seam must SKIP gracefully — never fabricate a real-data metric — whenever
the real omics data or the curated mislabel ground-truth file is absent, which
is the current state of this repo (``data/raw`` is empty, challenge labels
withheld). These tests pin that skip behaviour so the eval can be wired into
VERIFY today without ever reporting a synthetic-derived number as real-data
performance.
"""

from __future__ import annotations

import json
import types

import pytest

from evals import EvalResult
from evals.transfer_validation import TransferValidationEval

pytest.importorskip("pandas")


def test_skips_when_ground_truth_absent(tmp_path):
    # No curated label file -> inapplicable, passes vacuously, flagged proposed.
    missing = tmp_path / "nope.json"
    result = TransferValidationEval().evaluate(dataset="test", ground_truth_path=str(missing))
    assert isinstance(result, EvalResult)
    assert result.name == "transfer_validation"
    assert result.details["applicable"] is False
    assert result.details["proposed"] is True
    assert result.passed is True
    assert "ground-truth" in result.details["reason"]


def test_skips_when_real_omics_absent(tmp_path, monkeypatch):
    # Ground truth present, but the real omics TSVs are not -> still inapplicable
    # (must not score against missing data). Point the loader at an empty dir.
    gt = tmp_path / "test_mislabels.json"
    gt.write_text(json.dumps({"mislabel_type": {"S1": "proteomics", "S2": "rnaseq"}}))
    empty = tmp_path / "raw"
    empty.mkdir()
    monkeypatch.setattr(
        "core.data_loader.get_settings",
        lambda: types.SimpleNamespace(raw_data_dir=str(empty)),
    )

    result = TransferValidationEval().evaluate(dataset="test", ground_truth_path=str(gt))
    assert result.details["applicable"] is False
    assert result.passed is True
    assert "omics data not present" in result.details["reason"]
