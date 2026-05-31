"""Synthetic multi-omics cohort generator with planted biological signal.

Generates clinical, proteomics, and RNA-Seq DataFrames with known ground truth
for MSI phenotype, gender, cross-omics concordance, mislabeling, and structured
missingness. See docs/SYNTHETIC_DATA_STRATEGY.md for design rationale.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.constants import (
    GENDER_PROTEOMICS_PANEL,
    GENDER_RNASEQ_PANEL,
    KNOWN_MSI_PATHWAY_MARKERS,
    MSI_PROTEOMICS_PANEL,
    MSI_RNASEQ_PANEL,
    Y_CHROMOSOME_GENES,
)


class SyntheticCohortGenerator:
    """Generate a synthetic multi-omics cohort with planted ground truth.

    All randomness flows through a single ``numpy.random.Generator`` seeded at
    construction time for deterministic reproducibility.
    """

    def __init__(
        self,
        n_samples: int = 80,
        n_genes_proteomics: int = 5000,
        n_genes_rnaseq: int = 15000,
        msi_fraction: float = 0.4,
        mislabel_fraction: float = 0.05,
        seed: int = 42,
    ) -> None:
        self.n_samples = n_samples
        self.n_genes_proteomics = n_genes_proteomics
        self.n_genes_rnaseq = n_genes_rnaseq
        self.msi_fraction = msi_fraction
        self.mislabel_fraction = mislabel_fraction
        self.seed = seed
        self.rng = np.random.Generator(np.random.PCG64(seed))

    # ------------------------------------------------------------------
    # Presets
    # ------------------------------------------------------------------

    @classmethod
    def unit(cls, seed: int = 42) -> SyntheticCohortGenerator:
        return cls(
            n_samples=20,
            n_genes_proteomics=100,
            n_genes_rnaseq=150,
            seed=seed,
        )

    @classmethod
    def integration(cls, seed: int = 42) -> SyntheticCohortGenerator:
        return cls(
            n_samples=80,
            n_genes_proteomics=5000,
            n_genes_rnaseq=15000,
            seed=seed,
        )

    @classmethod
    def benchmark(cls, seed: int = 42) -> SyntheticCohortGenerator:
        return cls(
            n_samples=500,
            n_genes_proteomics=7000,
            n_genes_rnaseq=15000,
            seed=seed,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_cohort(self) -> dict:
        """Generate a complete synthetic cohort.

        Returns
        -------
        dict with keys ``"clinical"``, ``"proteomics"``, ``"rnaseq"``,
        ``"ground_truth"``.
        """
        clinical = self._generate_clinical()
        proteomics_genes = self._build_gene_list("proteomics", self.n_genes_proteomics)
        rnaseq_genes = self._build_gene_list("rnaseq", self.n_genes_rnaseq)

        proteomics = self._generate_expression(clinical, proteomics_genes, modality="proteomics")
        rnaseq = self._generate_expression(clinical, rnaseq_genes, modality="rnaseq")

        # Cross-omics concordance via shared latent factors
        self._inject_cross_omics_signal(clinical, proteomics, rnaseq, proteomics_genes, rnaseq_genes)

        # Mislabel injection
        clinical, proteomics, rnaseq, mislabel_truth = self._inject_mislabels(clinical, proteomics, rnaseq)

        # Structured missingness
        self._inject_missingness(proteomics, clinical, proteomics_genes)
        self._inject_missingness(rnaseq, clinical, rnaseq_genes, is_rnaseq=True)

        ground_truth = {
            **mislabel_truth,
            "msi_h_samples": clinical.loc[clinical["MSI_status"] == "MSI-H", "sample_id"].tolist(),
            "gender_map": dict(zip(clinical["sample_id"], clinical["gender"], strict=False)),
        }

        return {
            "clinical": clinical,
            "proteomics": proteomics,
            "rnaseq": rnaseq,
            "ground_truth": ground_truth,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _generate_clinical(self) -> pd.DataFrame:
        n_msi = max(2, int(self.n_samples * self.msi_fraction))
        n_mss = self.n_samples - n_msi
        msi_labels = ["MSI-H"] * n_msi + ["MSS"] * n_mss

        n_male = self.n_samples // 2
        n_female = self.n_samples - n_male
        gender_labels = ["Male"] * n_male + ["Female"] * n_female
        self.rng.shuffle(gender_labels)

        sample_ids = [f"S{i:03d}" for i in range(1, self.n_samples + 1)]

        return pd.DataFrame(
            {
                "sample_id": sample_ids,
                "MSI_status": msi_labels,
                "gender": gender_labels,
            }
        )

    def _build_gene_list(self, modality: str, n_genes: int) -> list[str]:
        """Build gene column names: known panels first, then synthetic."""
        if modality == "proteomics":
            panel = list(
                dict.fromkeys(
                    MSI_PROTEOMICS_PANEL
                    + GENDER_PROTEOMICS_PANEL
                    + list(KNOWN_MSI_PATHWAY_MARKERS.get("immune_infiltration", []))
                    + list(KNOWN_MSI_PATHWAY_MARKERS.get("interferon_response", []))
                    + list(KNOWN_MSI_PATHWAY_MARKERS.get("antigen_presentation", []))
                    + list(KNOWN_MSI_PATHWAY_MARKERS.get("mismatch_repair_adjacent", []))
                    + Y_CHROMOSOME_GENES
                )
            )
        else:
            panel = list(
                dict.fromkeys(
                    MSI_RNASEQ_PANEL
                    + GENDER_RNASEQ_PANEL
                    + list(KNOWN_MSI_PATHWAY_MARKERS.get("immune_infiltration", []))
                    + list(KNOWN_MSI_PATHWAY_MARKERS.get("interferon_response", []))
                    + list(KNOWN_MSI_PATHWAY_MARKERS.get("antigen_presentation", []))
                    + list(KNOWN_MSI_PATHWAY_MARKERS.get("mismatch_repair_adjacent", []))
                    + Y_CHROMOSOME_GENES
                )
            )

        # Truncate panel if n_genes is smaller
        panel = panel[:n_genes]
        n_remaining = n_genes - len(panel)
        synth = [f"SYNTH_GENE_{i:05d}" for i in range(n_remaining)]
        return panel + synth

    def _generate_expression(
        self,
        clinical: pd.DataFrame,
        gene_list: list[str],
        modality: str,
    ) -> pd.DataFrame:
        """Generate base expression with MSI and gender signal."""
        n = self.n_samples
        g = len(gene_list)

        # Base log-normal expression (moderate variance for signal detectability)
        base = self.rng.lognormal(mean=2.0, sigma=0.8, size=(n, g))

        # MSI signal injection — fold-changes applied to MSI-H samples
        msi_effect_size = {
            "immune_infiltration": 3.0,
            "interferon_response": 4.0,
            "antigen_presentation": 2.5,
            "mismatch_repair_adjacent": 2.0,
        }
        msi_h_mask = (clinical["MSI_status"] == "MSI-H").values
        gene_index = {name: idx for idx, name in enumerate(gene_list)}

        for pathway, genes in KNOWN_MSI_PATHWAY_MARKERS.items():
            fold = msi_effect_size[pathway]
            for gene in genes:
                if gene not in gene_index:
                    continue
                col = gene_index[gene]
                for row in np.where(msi_h_mask)[0]:
                    noise = self.rng.normal(0, 0.15)
                    base[row, col] *= fold + noise

        # Gender / Y-chromosome signal
        for gene in Y_CHROMOSOME_GENES:
            if gene not in gene_index:
                continue
            col = gene_index[gene]
            for row in range(n):
                if clinical.iloc[row]["gender"] == "Male":
                    base[row, col] = self.rng.lognormal(4.0, 0.5)
                else:
                    base[row, col] = 0.0

        # Pathway correlation structure (block-correlated noise)
        pathway_blocks = {
            "immune": ["PTPRC", "ITGB2", "LCP1", "NCF2"],
            "interferon": ["GBP1", "GBP4", "IRF1", "IFI35", "WARS"],
        }
        for _block_name, block_genes in pathway_blocks.items():
            indices = [gene_index[g] for g in block_genes if g in gene_index]
            if len(indices) < 2:
                continue
            k = len(indices)
            rho = 0.6
            cov = np.full((k, k), rho) + np.eye(k) * (1 - rho)
            L = np.linalg.cholesky(cov)
            for row in range(n):
                z = self.rng.standard_normal(k)
                correlated = L @ z
                for j, col in enumerate(indices):
                    base[row, col] *= np.exp(correlated[j] * 0.3)

        df = pd.DataFrame(base, columns=gene_list)
        df.insert(0, "sample_id", clinical["sample_id"].values)
        return df

    def _inject_cross_omics_signal(
        self,
        clinical: pd.DataFrame,
        proteomics: pd.DataFrame,
        rnaseq: pd.DataFrame,
        pro_genes: list[str],
        rna_genes: list[str],
    ) -> None:
        """Add shared latent factors for overlapping genes."""
        overlapping = set(pro_genes) & set(rna_genes) - {"sample_id"}
        if not overlapping:
            return

        n_latent = 5
        sample_profiles = self.rng.standard_normal((self.n_samples, n_latent))

        for gene in overlapping:
            loading = self.rng.standard_normal(n_latent) * 0.5
            for row in range(self.n_samples):
                shared = float(sample_profiles[row] @ loading)
                pro_val = proteomics.at[row, gene]
                rna_val = rnaseq.at[row, gene]
                proteomics.at[row, gene] = pro_val * np.exp(shared + self.rng.normal(0, 0.2))
                rnaseq.at[row, gene] = rna_val * np.exp(shared + self.rng.normal(0, 0.3))

    def _inject_mislabels(
        self,
        clinical: pd.DataFrame,
        proteomics: pd.DataFrame,
        rnaseq: pd.DataFrame,
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
        """Swap data between sample pairs to simulate mislabeling."""
        empty_truth: dict = {"mislabeled_samples": [], "mislabel_type": {}, "swap_pairs": []}
        if self.mislabel_fraction <= 0:
            return clinical, proteomics, rnaseq, empty_truth

        n_to_swap = max(2, int(self.n_samples * self.mislabel_fraction))
        if n_to_swap % 2 != 0:
            n_to_swap += 1
        # Ensure we don't try to pick more than available
        n_to_swap = min(n_to_swap, self.n_samples)
        if n_to_swap % 2 != 0:
            n_to_swap -= 1

        swap_indices = self.rng.choice(self.n_samples, size=n_to_swap, replace=False)
        pairs = list(zip(swap_indices[::2], swap_indices[1::2], strict=False))

        swap_types = ["proteomics", "rnaseq", "clinical"]
        ground_truth: dict = {
            "mislabeled_samples": [],
            "mislabel_type": {},
            "swap_pairs": [],
        }

        expr_cols_pro = [c for c in proteomics.columns if c != "sample_id"]
        expr_cols_rna = [c for c in rnaseq.columns if c != "sample_id"]

        for i, (idx_a, idx_b) in enumerate(pairs):
            swap_type = swap_types[i % len(swap_types)]
            sid_a = clinical.iloc[idx_a]["sample_id"]
            sid_b = clinical.iloc[idx_b]["sample_id"]

            if swap_type == "proteomics":
                row_a = proteomics.loc[idx_a, expr_cols_pro].copy()
                row_b = proteomics.loc[idx_b, expr_cols_pro].copy()
                proteomics.loc[idx_a, expr_cols_pro] = row_b.values
                proteomics.loc[idx_b, expr_cols_pro] = row_a.values
            elif swap_type == "rnaseq":
                row_a = rnaseq.loc[idx_a, expr_cols_rna].copy()
                row_b = rnaseq.loc[idx_b, expr_cols_rna].copy()
                rnaseq.loc[idx_a, expr_cols_rna] = row_b.values
                rnaseq.loc[idx_b, expr_cols_rna] = row_a.values
            elif swap_type == "clinical":
                for col in ["MSI_status", "gender"]:
                    val_a = clinical.at[idx_a, col]
                    val_b = clinical.at[idx_b, col]
                    clinical.at[idx_a, col] = val_b
                    clinical.at[idx_b, col] = val_a

            ground_truth["mislabeled_samples"].extend([sid_a, sid_b])
            ground_truth["mislabel_type"][sid_a] = swap_type
            ground_truth["mislabel_type"][sid_b] = swap_type
            ground_truth["swap_pairs"].append((sid_a, sid_b))

        return clinical, proteomics, rnaseq, ground_truth

    def _inject_missingness(
        self,
        expr_df: pd.DataFrame,
        clinical: pd.DataFrame,
        gene_list: list[str],
        is_rnaseq: bool = False,
    ) -> None:
        """Inject MNAR and MAR missingness in-place."""
        expr_cols = [c for c in expr_df.columns if c != "sample_id"]
        data = expr_df[expr_cols].values.astype(float)

        # MNAR: Y-chromosome genes -> NaN for female samples
        gene_index = {name: idx for idx, name in enumerate(expr_cols)}
        female_mask = (clinical["gender"] == "Female").values
        for gene in Y_CHROMOSOME_GENES:
            if gene in gene_index:
                col = gene_index[gene]
                data[female_mask, col] = np.nan

        # MNAR: detection-limit censoring for low-abundance values
        valid = data[~np.isnan(data)]
        if len(valid) > 0:
            threshold = np.percentile(valid, 5)
            low_mask = data < threshold
            censor = low_mask & (self.rng.random(data.shape) < 0.70)
            data[censor] = np.nan

        # MAR: batch-correlated dropout
        n_batches = 3
        batch_assign = self.rng.choice(n_batches, size=self.n_samples)
        n_affected = max(1, int(len(expr_cols) * 0.05))

        for batch_id in range(n_batches):
            batch_rows = np.where(batch_assign == batch_id)[0]
            affected_cols = self.rng.choice(len(expr_cols), size=n_affected, replace=False)
            for col in affected_cols:
                dropout_rate = self.rng.uniform(0.15, 0.40)
                for row in batch_rows:
                    if self.rng.random() < dropout_rate:
                        data[row, col] = np.nan

        expr_df[expr_cols] = data
