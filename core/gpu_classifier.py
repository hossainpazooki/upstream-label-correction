"""GPU-accelerated ensemble classifier using cuML."""

from __future__ import annotations

import logging

import numpy as np

try:
    from cuml.ensemble import RandomForestClassifier as cuRF
    from cuml.linear_model import LogisticRegression as cuLR
    from cuml.neighbors import KNeighborsClassifier as cuKNN

    _CUML_AVAILABLE = True
except ImportError:
    _CUML_AVAILABLE = False

logger = logging.getLogger(__name__)


class GPUEnsembleMismatchClassifier:
    """Same API as EnsembleMismatchClassifier but using cuML GPU estimators.

    Requires NVIDIA GPU with RAPIDS/cuML installed.
    """

    def __init__(self, random_state: int = 42) -> None:
        if not _CUML_AVAILABLE:
            raise ImportError("cuML is required for GPU classifier")
        self.random_state = random_state
        self.classifiers_: dict = {}
        self.meta_learner_ = None
        self.is_fitted_ = False

    def _make_base_classifiers(self) -> dict:
        """Build GPU-accelerated base classifiers."""
        return {
            "knn": cuKNN(n_neighbors=3),
            "lr": cuLR(max_iter=5000),
            "rf": cuRF(
                n_estimators=100,
                max_depth=5,
                random_state=self.random_state,
            ),
        }

    def fit(
        self,
        X: np.ndarray,
        y_gender: np.ndarray,
        y_msi: np.ndarray,
        mismatch_labels: np.ndarray,
    ) -> GPUEnsembleMismatchClassifier:
        """Train base classifiers and meta-learner on GPU."""
        X_arr = np.asarray(X, dtype=np.float32)
        y_gender_arr = np.asarray(y_gender).ravel()
        y_msi_arr = np.asarray(y_msi).ravel()
        mismatch_arr = np.asarray(mismatch_labels).ravel().astype(np.int32)

        if np.any(np.isnan(X_arr)):
            X_arr = np.nan_to_num(X_arr, nan=0.0)

        base_classifiers = self._make_base_classifiers()

        meta_cols = []
        for clf_name, clf in base_classifiers.items():
            # Gender
            key_g = f"{clf_name}_gender"
            clf_g = self._clone_clf(clf)
            clf_g.fit(X_arr, y_gender_arr)
            self.classifiers_[key_g] = clf_g
            meta_cols.append(
                clf_g.predict(X_arr).get() if hasattr(clf_g.predict(X_arr), "get") else np.asarray(clf_g.predict(X_arr))
            )

            # MSI
            key_m = f"{clf_name}_msi"
            clf_m = self._clone_clf(clf)
            clf_m.fit(X_arr, y_msi_arr)
            self.classifiers_[key_m] = clf_m
            meta_cols.append(
                clf_m.predict(X_arr).get() if hasattr(clf_m.predict(X_arr), "get") else np.asarray(clf_m.predict(X_arr))
            )

        meta_features = np.column_stack(meta_cols).astype(np.float32)

        self.meta_learner_ = cuLR(max_iter=5000)
        self.meta_learner_.fit(meta_features, mismatch_arr)
        self.is_fitted_ = True
        return self

    def predict_ensemble(self, X: np.ndarray) -> dict:
        """Generate ensemble predictions."""
        if not self.is_fitted_:
            raise RuntimeError("Classifier not fitted. Call fit() first.")

        X_arr = np.asarray(X, dtype=np.float32)
        if np.any(np.isnan(X_arr)):
            X_arr = np.nan_to_num(X_arr, nan=0.0)

        per_classifier = {}
        meta_cols = []
        for key, clf in self.classifiers_.items():
            preds = clf.predict(X_arr)
            preds_np = preds.get() if hasattr(preds, "get") else np.asarray(preds)
            per_classifier[key] = preds_np.tolist()
            meta_cols.append(preds_np)

        meta_features = np.column_stack(meta_cols).astype(np.float32)
        ensemble_preds = self.meta_learner_.predict(meta_features)
        ensemble_np = ensemble_preds.get() if hasattr(ensemble_preds, "get") else np.asarray(ensemble_preds)

        return {
            "ensemble_predictions": ensemble_np.tolist(),
            "per_classifier_predictions": per_classifier,
        }

    def evaluate(self, X_test: np.ndarray, y_test: np.ndarray) -> dict:
        """Evaluate ensemble on test data."""
        from sklearn.metrics import f1_score, precision_score, recall_score

        result = self.predict_ensemble(X_test)
        preds = np.array(result["ensemble_predictions"])
        y_true = np.asarray(y_test).ravel().astype(int)

        return {
            "f1": float(f1_score(y_true, preds, average="weighted", zero_division=0)),
            "precision": float(precision_score(y_true, preds, average="weighted", zero_division=0)),
            "recall": float(recall_score(y_true, preds, average="weighted", zero_division=0)),
        }

    @staticmethod
    def _clone_clf(clf):
        """Create a fresh instance of the same classifier type."""
        cls = type(clf)
        params = clf.get_params()
        return cls(**params)
