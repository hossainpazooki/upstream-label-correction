"""Tests for core.synthetic — SyntheticCohortGenerator."""

from __future__ import annotations

import pandas as pd
import pytest
from scipy import stats

from core.constants import KNOWN_MSI_PATHWAY_MARKERS, Y_CHROMOSOME_GENES
from core.synthetic import SyntheticCohortGenerator


@pytest.fixture()
def cohort():
    gen = SyntheticCohortGenerator.unit(seed=42)
    return gen.generate_cohort()


class TestOutputShapes:
    def test_clinical_shape(self, cohort):
        clin = cohort["clinical"]
        assert isinstance(clin, pd.DataFrame)
        assert len(clin) == 20
        assert set(clin.columns) >= {"sample_id", "MSI_status", "gender"}

    def test_proteomics_shape(self, cohort):
        pro = cohort["proteomics"]
        assert isinstance(pro, pd.DataFrame)
        assert len(pro) == 20
        # sample_id + gene columns
        assert pro.shape[1] == 100 + 1

    def test_rnaseq_shape(self, cohort):
        rna = cohort["rnaseq"]
        assert isinstance(rna, pd.DataFrame)
        assert len(rna) == 20
        assert rna.shape[1] == 150 + 1


class TestGroundTruth:
    def test_ground_truth_keys(self, cohort):
        gt = cohort["ground_truth"]
        assert "mislabeled_samples" in gt
        assert "mislabel_type" in gt
        assert "swap_pairs" in gt
        assert "msi_h_samples" in gt
        assert "gender_map" in gt

    def test_mislabeled_samples_exist(self, cohort):
        gt = cohort["ground_truth"]
        assert len(gt["mislabeled_samples"]) > 0

    def test_swap_pairs_valid(self, cohort):
        gt = cohort["ground_truth"]
        all_ids = set(cohort["clinical"]["sample_id"])
        for a, b in gt["swap_pairs"]:
            assert a in all_ids
            assert b in all_ids
            assert a != b

    def test_mislabel_type_valid(self, cohort):
        gt = cohort["ground_truth"]
        valid_types = {"proteomics", "rnaseq", "clinical"}
        for _sid, mtype in gt["mislabel_type"].items():
            assert mtype in valid_types


class TestMSISignal:
    def test_msi_pathway_genes_detectable(self):
        """At least some MSI pathway genes should show significant difference."""
        gen = SyntheticCohortGenerator.unit(seed=42)
        # Use a fresh cohort without mislabeling to test clean signal
        gen.mislabel_fraction = 0.0
        data = gen.generate_cohort()

        clin = data["clinical"]
        pro = data["proteomics"]
        msi_h = clin["MSI_status"] == "MSI-H"

        significant_count = 0
        all_pathway_genes = [g for genes in KNOWN_MSI_PATHWAY_MARKERS.values() for g in genes]

        for gene in all_pathway_genes:
            if gene not in pro.columns:
                continue
            vals_h = pro.loc[msi_h, gene].dropna()
            vals_s = pro.loc[~msi_h, gene].dropna()
            if len(vals_h) < 2 or len(vals_s) < 2:
                continue
            _, p = stats.ttest_ind(vals_h, vals_s, equal_var=False)
            if p < 0.05:
                significant_count += 1

        assert significant_count >= 1, "Expected at least 1 MSI pathway gene with p < 0.05"


class TestReproducibility:
    def test_same_seed_identical(self):
        gen1 = SyntheticCohortGenerator.unit(seed=99)
        gen2 = SyntheticCohortGenerator.unit(seed=99)
        d1 = gen1.generate_cohort()
        d2 = gen2.generate_cohort()

        pd.testing.assert_frame_equal(d1["clinical"], d2["clinical"])
        pd.testing.assert_frame_equal(d1["proteomics"], d2["proteomics"])
        pd.testing.assert_frame_equal(d1["rnaseq"], d2["rnaseq"])

    def test_different_seed_differs(self):
        gen1 = SyntheticCohortGenerator.unit(seed=1)
        gen2 = SyntheticCohortGenerator.unit(seed=2)
        d1 = gen1.generate_cohort()
        d2 = gen2.generate_cohort()

        # At least the expression values should differ
        assert not d1["proteomics"].drop(columns="sample_id").equals(d2["proteomics"].drop(columns="sample_id"))


class TestYChromosomeSignal:
    def test_y_chr_near_zero_for_females(self):
        gen = SyntheticCohortGenerator.unit(seed=42)
        gen.mislabel_fraction = 0.0
        data = gen.generate_cohort()

        clin = data["clinical"]
        pro = data["proteomics"]
        female_mask = clin["gender"] == "Female"

        for gene in Y_CHROMOSOME_GENES:
            if gene not in pro.columns:
                continue
            vals = pro.loc[female_mask, gene]
            # After missingness injection, these should be NaN (MNAR)
            # or zero (before missingness). Either way, non-NaN values
            # should be near zero.
            non_nan = vals.dropna()
            if len(non_nan) > 0:
                assert (non_nan.abs() < 1e-6).all(), f"{gene} has non-zero values in female samples"
