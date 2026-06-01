"""Omics imputation with MNAR/MAR classification and NMF-based filling.

Implements Missing-Not-At-Random (MNAR) detection for Y-chromosome genes
in female samples, and Missing-At-Random (MAR) imputation via NMF.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from core.constants import Y_CHROMOSOME_GENES

try:
    from sklearn.decomposition import NMF
except ImportError:
    NMF = None  # type: ignore[assignment,misc]


class OmicsImputer:
    """Classify and impute missing values in omics expression matrices."""

    def classify_missingness(
        self,
        expression_matrix: pd.DataFrame,
        clinical_df: pd.DataFrame,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Classify each missing value as MNAR or MAR.

        Y-chromosome genes missing in female samples are MNAR; all other
        missing values are MAR.

        Returns
        -------
        mnar_mask : pd.DataFrame
            Boolean mask where True = MNAR missing value.
        mar_mask : pd.DataFrame
            Boolean mask where True = MAR missing value.
        """
        is_missing = expression_matrix.isna()

        # Build gender lookup
        clinical = clinical_df.copy()
        if "sample_id" in clinical.columns:
            clinical = clinical.set_index("sample_id")

        gender_map: dict[str, str] = {}
        if "gender" in clinical.columns:
            gender_map = clinical["gender"].to_dict()

        # MNAR: Y-chromosome genes missing in female samples
        mnar_mask = pd.DataFrame(False, index=expression_matrix.index, columns=expression_matrix.columns)

        y_genes_in_data = [g for g in Y_CHROMOSOME_GENES if g in expression_matrix.columns]

        for sample_id in expression_matrix.index:
            gender = gender_map.get(sample_id, "Unknown")
            if gender == "Female":
                for gene in y_genes_in_data:
                    if is_missing.at[sample_id, gene]:
                        mnar_mask.at[sample_id, gene] = True

        # MAR = missing but not MNAR
        mar_mask = is_missing & ~mnar_mask

        return mnar_mask, mar_mask

    def impute_nmf(
        self,
        matrix: pd.DataFrame,
        n_components: int | str = "auto",
        max_iter: int = 500,
        random_state: int = 42,
    ) -> pd.DataFrame:
        """NMF imputation for MAR missing values.

        If ``n_components`` is ``"auto"``, sweep k in [2, 5, 8, 10, 15] and
        pick the value with the lowest reconstruction error on 10% held-out
        observed entries.
        """
        if NMF is None:
            raise ImportError("scikit-learn is required for NMF imputation")

        result = matrix.copy()

        # Replace remaining NaN with 0 for NMF (non-negative requirement)
        filled = result.fillna(0.0)
        # Ensure non-negative
        filled = filled.clip(lower=0.0)

        observed_mask = ~matrix.isna()

        if isinstance(n_components, str) and n_components == "auto":
            n_components = self._auto_select_k(filled, observed_mask, max_iter, random_state)

        # Clamp n_components to valid range
        max_k = min(filled.shape[0], filled.shape[1])
        n_components = min(n_components, max(1, max_k - 1))
        n_components = max(1, n_components)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = NMF(
                n_components=n_components,
                init="nndsvda",
                max_iter=max_iter,
                random_state=random_state,
            )
            W = model.fit_transform(filled)
            H = model.components_
            reconstructed = W @ H

        # Only fill missing positions
        for i in range(result.shape[0]):
            for j in range(result.shape[1]):
                if matrix.isna().iloc[i, j]:
                    result.iloc[i, j] = max(0.0, reconstructed[i, j])

        return result

    def _auto_select_k(
        self,
        filled: pd.DataFrame,
        observed_mask: pd.DataFrame,
        max_iter: int,
        random_state: int,
    ) -> int:
        """Select k via held-out masking: mask 10% of observed values, sweep k."""
        rng = np.random.RandomState(random_state)

        observed_positions = list(zip(*np.where(observed_mask.values), strict=False))
        n_holdout = max(1, int(len(observed_positions) * 0.10))
        holdout_idx = rng.choice(len(observed_positions), size=n_holdout, replace=False)
        holdout_positions = [observed_positions[i] for i in holdout_idx]

        # Build training matrix with holdout masked
        train_matrix = filled.copy()
        true_values = []
        for i, j in holdout_positions:
            true_values.append(filled.iloc[i, j])
            train_matrix.iloc[i, j] = 0.0

        true_values = np.array(true_values)

        candidates = [k for k in [2, 5, 8, 10, 15] if k < min(filled.shape)]
        if not candidates:
            return max(1, min(filled.shape) - 1)

        best_k = candidates[0]
        best_error = float("inf")

        for k in candidates:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                try:
                    model = NMF(
                        n_components=k,
                        init="nndsvda",
                        max_iter=max_iter,
                        random_state=random_state,
                    )
                    W = model.fit_transform(train_matrix.values.clip(min=0))
                    H = model.components_
                    recon = W @ H

                    predicted = np.array([recon[i, j] for i, j in holdout_positions])
                    error = np.mean((true_values - predicted) ** 2)

                    if error < best_error:
                        best_error = error
                        best_k = k
                except Exception:  # noqa: S112
                    # this k failed (e.g. NMF did not converge); try the next k
                    continue

        return best_k

    def impute(
        self,
        expression_matrix: pd.DataFrame,
        clinical_df: pd.DataFrame,
    ) -> tuple[pd.DataFrame, dict]:
        """Full imputation pipeline: classify -> zero-fill MNAR -> NMF for MAR.

        Returns
        -------
        filled_matrix : pd.DataFrame
            Expression matrix with all NaN values filled.
        imputation_stats : dict
            Statistics about the imputation process.
        """
        mnar_mask, mar_mask = self.classify_missingness(expression_matrix, clinical_df)

        total_missing = int(expression_matrix.isna().sum().sum())
        n_mnar = int(mnar_mask.sum().sum())
        n_mar = int(mar_mask.sum().sum())

        # Step 1: Zero-fill MNAR positions
        filled = expression_matrix.copy()
        filled[mnar_mask] = 0.0

        # Step 2: NMF imputation for MAR positions
        if n_mar > 0:
            filled = self.impute_nmf(filled)

        stats = {
            "total_missing": total_missing,
            "n_mnar": n_mnar,
            "n_mar": n_mar,
            "pct_mnar": round(n_mnar / max(total_missing, 1) * 100, 2),
            "pct_mar": round(n_mar / max(total_missing, 1) * 100, 2),
            "remaining_nan": int(filled.isna().sum().sum()),
        }

        return filled, stats
