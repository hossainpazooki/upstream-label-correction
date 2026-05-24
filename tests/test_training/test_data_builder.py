"""Tests for training data builder and format utilities."""

from __future__ import annotations

import json

from training.data_builder import build_ground_truth_examples
from training.format_utils import format_alpaca, split_dataset


class TestFormatAlpaca:
    def test_format_structure(self):
        result = format_alpaca("Do something", "input text", '{"key": "value"}')
        assert "### Instruction:" in result
        assert "Do something" in result
        assert "### Input:" in result
        assert "input text" in result
        assert "### Response:" in result
        assert '{"key": "value"}' in result

    def test_format_ordering(self):
        result = format_alpaca("inst", "inp", "out")
        inst_pos = result.index("### Instruction:")
        inp_pos = result.index("### Input:")
        resp_pos = result.index("### Response:")
        assert inst_pos < inp_pos < resp_pos


class TestSplitDataset:
    def test_split_ratios(self):
        examples = [{"id": i} for i in range(100)]
        train, val, test = split_dataset(examples, train_frac=0.8, val_frac=0.1)
        assert len(train) == 80
        assert len(val) == 10
        assert len(test) == 10

    def test_split_deterministic(self):
        examples = [{"id": i} for i in range(50)]
        t1, v1, te1 = split_dataset(examples, seed=42)
        t2, v2, te2 = split_dataset(examples, seed=42)
        assert t1 == t2
        assert v1 == v2
        assert te1 == te2

    def test_split_no_data_loss(self):
        examples = [{"id": i} for i in range(37)]
        train, val, test = split_dataset(examples)
        all_ids = {e["id"] for e in train + val + test}
        assert all_ids == {i for i in range(37)}

    def test_split_different_seeds(self):
        examples = [{"id": i} for i in range(50)]
        t1, _, _ = split_dataset(examples, seed=1)
        t2, _, _ = split_dataset(examples, seed=2)
        assert t1 != t2


class TestBuildGroundTruthExamples:
    def test_returns_non_empty(self):
        examples = build_ground_truth_examples()
        assert len(examples) > 0

    def test_required_keys(self):
        examples = build_ground_truth_examples()
        required_keys = {"instruction", "input", "output", "source", "pathway"}
        for ex in examples:
            assert required_keys.issubset(ex.keys()), f"Missing keys in {ex.keys()}"

    def test_output_is_valid_json(self):
        examples = build_ground_truth_examples()
        for ex in examples:
            parsed = json.loads(ex["output"])
            assert "gene" in parsed
            assert "pathway" in parsed
            assert "msi_relevant" in parsed

    def test_source_is_ground_truth(self):
        examples = build_ground_truth_examples()
        for ex in examples:
            assert ex["source"] == "ground_truth"

    def test_covers_all_pathways(self):
        from core.constants import KNOWN_MSI_PATHWAY_MARKERS

        examples = build_ground_truth_examples()
        pathways_seen = set()
        for ex in examples:
            for p in ex["pathway"].split(", "):
                pathways_seen.add(p)
        for pathway in KNOWN_MSI_PATHWAY_MARKERS:
            assert pathway in pathways_seen
