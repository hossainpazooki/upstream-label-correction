"""Shared test fixtures for CLUE.

Generates synthetic multi-omics data matching the precisionFDA schema so
all tests can run without real data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.constants import (
    MSI_PROTEOMICS_PANEL,
    MSI_RNASEQ_PANEL,
    Y_CHROMOSOME_GENES,
)

# Deterministic seed for all synthetic data
RNG = np.random.RandomState(42)

N_SAMPLES = 20
SAMPLE_IDS = [f"S{str(i).zfill(3)}" for i in range(1, N_SAMPLES + 1)]

# Phenotype assignments: ~15% MSI-H, ~50/50 gender
MSI_LABELS = ["MSI-H"] * 3 + ["MSS"] * 17
GENDER_LABELS = ["Male"] * 10 + ["Female"] * 10

# Proteomics gene names: union of MSI panel + gender Y-chr genes + random extras
PROTEOMICS_GENES = list(
    set(
        MSI_PROTEOMICS_PANEL
        + Y_CHROMOSOME_GENES
        + [
            "BRCA1",
            "TP53",
            "EGFR",
            "KRAS",
            "PTEN",
            "APC",
            "MYC",
            "CDH1",
            "VEGFA",
            "BRAF",
            "PIK3CA",
            "ATM",
            "RB1",
            "NRAS",
            "SMAD4",
        ]
    )
)

# RNA-Seq gene names: MSI RNA panel + Y-chr genes + extras (some overlap with proteomics)
RNASEQ_GENES = list(
    set(
        MSI_RNASEQ_PANEL
        + Y_CHROMOSOME_GENES
        + [
            "BRCA1",
            "TP53",
            "EGFR",
            "KRAS",
            "PTEN",
            "APC",
            "MYC",
            "CDH1",
            "VEGFA",
            "BRAF",
            "PIK3CA",
            "ATM",
            "RB1",
            "NRAS",
            "SMAD4",
            "GAPDH",
            "ACTB",
            "TUBA1A",
            "HSP90AA1",
            "ALB",
        ]
    )
)


def _make_expression_matrix(
    sample_ids: list[str],
    gene_names: list[str],
    missing_rate: float = 0.10,
    gender_labels: list[str] | None = None,
) -> pd.DataFrame:
    """Generate synthetic expression data with realistic missing patterns."""
    n_samples = len(sample_ids)
    n_genes = len(gene_names)

    # Base expression: log-normal distribution
    data = RNG.lognormal(mean=2.0, sigma=1.5, size=(n_samples, n_genes))

    df = pd.DataFrame(data, index=sample_ids, columns=gene_names)

    # Introduce ~missing_rate MAR missing values
    mask = RNG.random((n_samples, n_genes)) < missing_rate
    df[mask] = np.nan

    # Y-chromosome genes: set to NaN (MNAR) for female samples
    if gender_labels is not None:
        for i, gender in enumerate(gender_labels):
            if gender == "Female":
                for gene in Y_CHROMOSOME_GENES:
                    if gene in df.columns:
                        df.iloc[i, df.columns.get_loc(gene)] = np.nan

    return df


@pytest.fixture
def sample_clinical_df() -> pd.DataFrame:
    """Synthetic clinical data matching precisionFDA schema."""
    return pd.DataFrame(
        {
            "sample_id": SAMPLE_IDS,
            "MSI_status": MSI_LABELS,
            "gender": GENDER_LABELS,
        }
    )


@pytest.fixture
def sample_proteomics_df() -> pd.DataFrame:
    """Synthetic proteomics expression matrix (samples × genes)."""
    return _make_expression_matrix(SAMPLE_IDS, PROTEOMICS_GENES, missing_rate=0.10, gender_labels=GENDER_LABELS)


@pytest.fixture
def sample_rnaseq_df() -> pd.DataFrame:
    """Synthetic RNA-Seq expression matrix (samples × genes)."""
    return _make_expression_matrix(SAMPLE_IDS, RNASEQ_GENES, missing_rate=0.08, gender_labels=GENDER_LABELS)


@pytest.fixture
def sample_mismatch_labels() -> pd.Series:
    """Known mismatch labels for 20 samples (2 are swapped)."""
    labels = [False] * N_SAMPLES
    labels[3] = True  # S004 is mislabeled
    labels[14] = True  # S015 is mislabeled
    return pd.Series(labels, index=SAMPLE_IDS, name="is_mislabeled")


@pytest.fixture
def sample_msi_labels() -> pd.Series:
    """MSI status as binary labels."""
    return pd.Series(
        [1 if m == "MSI-H" else 0 for m in MSI_LABELS],
        index=SAMPLE_IDS,
        name="msi",
    )


@pytest.fixture
def sample_gender_labels() -> pd.Series:
    """Gender as binary labels."""
    return pd.Series(
        [1 if g == "Male" else 0 for g in GENDER_LABELS],
        index=SAMPLE_IDS,
        name="gender",
    )


@pytest.fixture
def tmp_data_dir(tmp_path: object) -> object:
    """Create a temporary data directory with synthetic TSV files."""
    from pathlib import Path

    data_dir = Path(str(tmp_path)) / "raw"
    data_dir.mkdir(parents=True)

    # Clinical TSV
    clinical = pd.DataFrame(
        {
            "sample_id": SAMPLE_IDS,
            "MSI_status": MSI_LABELS,
            "gender": GENDER_LABELS,
        }
    )
    clinical.to_csv(data_dir / "train_cli.tsv", sep="\t", index=False)

    # Proteomics TSV (genes as rows — transposed before save)
    pro = _make_expression_matrix(SAMPLE_IDS, PROTEOMICS_GENES, missing_rate=0.10, gender_labels=GENDER_LABELS)
    pro.T.to_csv(data_dir / "train_pro.tsv", sep="\t")

    # RNA-Seq TSV (genes as rows)
    rna = _make_expression_matrix(SAMPLE_IDS, RNASEQ_GENES, missing_rate=0.08, gender_labels=GENDER_LABELS)
    rna.T.to_csv(data_dir / "train_rna.tsv", sep="\t")

    return data_dir


@pytest.fixture
def client():
    """FastAPI test client for the ML service."""
    from fastapi.testclient import TestClient

    from ml_service.main import app

    return TestClient(app)
