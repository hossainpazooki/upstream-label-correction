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
from evals.transfer_validation import (
    TransferValidationEval,
    mislabel_type_from_sum_tab2,
)

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


# --- mislabel_type_from_sum_tab2: sum_tab_2.csv -> {sample_id: type} ---------
#
# Each row (sample, Clinical, RNAseq, Proteomics) records the sample index each
# modality truly came from. A sample is mislabeled iff a modality's source index
# != its own index; type is molecular-first (proteomics > rnaseq > clinical);
# clean samples are omitted. These pin the converter that turns the precisionFDA
# answer key into real ground truth (gap #1 pre-staging).


def test_mislabel_proteomics_swap():
    rows = [{"sample": "Training_2", "Clinical": 2, "RNAseq": 2, "Proteomics": 80}]
    assert mislabel_type_from_sum_tab2(rows) == {"Training_2": "proteomics"}


def test_mislabel_rnaseq_swap():
    rows = [{"sample": "Training_6", "Clinical": 6, "RNAseq": 21, "Proteomics": 6}]
    assert mislabel_type_from_sum_tab2(rows) == {"Training_6": "rnaseq"}


def test_mislabel_clinical_only_swap():
    rows = [{"sample": "Training_3", "Clinical": 11, "RNAseq": 3, "Proteomics": 3}]
    assert mislabel_type_from_sum_tab2(rows) == {"Training_3": "clinical"}


def test_clean_sample_omitted():
    rows = [{"sample": "Training_4", "Clinical": 4, "RNAseq": 4, "Proteomics": 4}]
    out = mislabel_type_from_sum_tab2(rows)
    assert out == {}
    assert "Training_4" not in out


def test_molecular_first_priority_proteomics_over_rnaseq():
    # Both proteomics and rnaseq swapped -> proteomics wins (molecular-first).
    rows = [{"sample": "Training_7", "Clinical": 7, "RNAseq": 30, "Proteomics": 55}]
    assert mislabel_type_from_sum_tab2(rows) == {"Training_7": "proteomics"}


def test_bom_and_header_case_robustness():
    # BOM-prefixed + mixed-case header keys still parse to the right type.
    rows = [{"﻿sample": "Training_9", "CLINICAL": 9, "rnaseq": 9, "Proteomics": 12}]
    assert mislabel_type_from_sum_tab2(rows) == {"Training_9": "proteomics"}


def test_mixed_cohort_clean_absent_and_types_exact():
    rows = [
        {"sample": "Training_1", "Clinical": 1, "RNAseq": 1, "Proteomics": 1},  # clean
        {"sample": "Training_2", "Clinical": 2, "RNAseq": 2, "Proteomics": 80},  # prot
        {"sample": "Training_6", "Clinical": 6, "RNAseq": 21, "Proteomics": 6},  # rna
        {"sample": "Training_3", "Clinical": 11, "RNAseq": 3, "Proteomics": 3},  # clin
    ]
    out = mislabel_type_from_sum_tab2(rows)
    assert out == {
        "Training_2": "proteomics",
        "Training_6": "rnaseq",
        "Training_3": "clinical",
    }
    assert "Training_1" not in out
