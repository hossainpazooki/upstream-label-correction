"""Integration coverage for the ml_service /ml/evaluate fidelity_gate routing.

Mirrors tests/test_evals/test_mislabel_detection_routing.py: a FastAPI
TestClient drives POST /ml/evaluate with eval_name="fidelity_gate" and we assert
the ROUTING wires up correctly — the runner reaches the gate, the AUROC-threshold
fallback applies when the gate is called ungated (threshold 0.0), and the
not-applicable (clean cohort) path passes vacuously.

The gate's AUROC math is covered by tests/test_evals/test_fidelity_gate.py, so
here we patch the heavy inner call (``evals.fidelity_gate.fidelity_auroc``) to
keep the routing test fast and deterministic — we are testing the wiring.
"""

import pytest

pytest.importorskip("sklearn")

SMALL = {"n_samples": 30, "n_genes_proteomics": 150, "n_genes_rnaseq": 200, "seed": 7}
_FAKE_BREAKDOWN = {"n_molecular_swaps": 4, "n_clean": 24, "n_clinical_excluded": 2}


class TestFidelityGateRouting:
    """Integration coverage for the /ml/evaluate fidelity_gate route."""

    def test_routes_and_scores_auroc(self, monkeypatch):
        from fastapi.testclient import TestClient

        from ml_service.main import app

        monkeypatch.setattr(
            "evals.fidelity_gate.fidelity_auroc",
            lambda *a, **k: (0.95, dict(_FAKE_BREAKDOWN)),
        )

        client = TestClient(app)
        response = client.post(
            "/ml/evaluate",
            json={"eval_name": "fidelity_gate", "threshold": 0.8, "params": dict(SMALL)},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "fidelity_gate"
        assert body["score"] == 0.95
        assert body["passed"] is True
        assert body["details"]["applicable"] is True
        assert body["details"]["auroc"] == 0.95

    def test_zero_threshold_falls_back_to_default_auroc_bar(self, monkeypatch):
        """threshold=0.0 (assurance default) must not pass any cohort — the gate
        falls back to its own 0.80 AUROC bar, so an AUROC of 0.70 fails."""
        from fastapi.testclient import TestClient

        from ml_service.main import app

        monkeypatch.setattr(
            "evals.fidelity_gate.fidelity_auroc",
            lambda *a, **k: (0.70, dict(_FAKE_BREAKDOWN)),
        )

        client = TestClient(app)
        response = client.post(
            "/ml/evaluate",
            json={"eval_name": "fidelity_gate", "threshold": 0.0, "params": dict(SMALL)},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["threshold"] == 0.80  # fell back from 0.0
        assert body["score"] == 0.70
        assert body["passed"] is False

    def test_not_applicable_clean_cohort_passes(self, monkeypatch):
        from fastapi.testclient import TestClient

        from ml_service.main import app

        monkeypatch.setattr(
            "evals.fidelity_gate.fidelity_auroc",
            lambda *a, **k: (None, {"n_molecular_swaps": 0, "n_clean": 30, "n_clinical_excluded": 0}),
        )

        client = TestClient(app)
        response = client.post(
            "/ml/evaluate",
            json={"eval_name": "fidelity_gate", "threshold": 0.8, "params": {**SMALL, "mislabel_fraction": 0.0}},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["passed"] is True
        assert body["details"]["applicable"] is False
        assert body["score"] == 1.0
