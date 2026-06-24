"""Integration coverage for the ml_service /ml/evaluate transfer_validation routing.

Mirrors tests/test_evals/test_fidelity_gate_routing.py: a FastAPI TestClient
drives POST /ml/evaluate with eval_name="transfer_validation" and we assert the
ROUTING wires up correctly — the request reaches ``_eval_transfer_validation``,
which delegates to ``evals.transfer_validation.TransferValidationEval`` and
returns a well-formed, JSON-serializable dict.

The transfer-validation eval's gate-safety invariant is that it SKIPS gracefully
(``applicable=False``, ``passed=True``, ``score=1.0``) whenever the real omics
matrices or the curated mislabel ground-truth file are absent — the state of CI
(no ``data/raw``). This repo may have the real TRAIN matrices present locally, so
to keep the routing test deterministic and CI-faithful we point the raw-data
resolver at an empty directory: the ground-truth file is then absent and the
runner takes the graceful-skip branch regardless of the host's data state. The
real-data scoring math itself is covered by tests/test_evals/test_transfer_validation.py;
here we are testing the wiring + the no-data-passes invariant the gate relies on.
"""

import pytest

pytest.importorskip("pandas")


@pytest.fixture
def no_real_data(monkeypatch, tmp_path):
    """Force the no-real-data path deterministically (CI-faithful).

    ``TransferValidationEval`` builds the ground-truth path as
    ``Path(get_raw_dir()) / f"{dataset}_mislabels.json"``. Pointing ``get_raw_dir``
    at an empty dir makes that file absent, so the eval takes its graceful-skip
    branch — exactly what CI sees with no ``data/raw`` — even on a host where the
    real TRAIN matrices happen to be present.
    """
    empty = tmp_path / "raw"
    empty.mkdir()
    monkeypatch.setattr("evals.transfer_validation.get_raw_dir", lambda: str(empty))


class TestTransferValidationRouting:
    """Integration coverage for the /ml/evaluate transfer_validation route."""

    def test_routes_to_transfer_validation_runner(self, no_real_data):
        """POST routes to the runner and returns a well-formed transfer_validation dict."""
        from fastapi.testclient import TestClient

        from ml_service.main import app

        client = TestClient(app)
        response = client.post(
            "/ml/evaluate",
            json={
                "eval_name": "transfer_validation",
                "threshold": 0.70,
                "params": {"dataset": "train"},
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, dict)
        # Well-formed EvalResult shape (the routing reached the eval, not the
        # legacy COSMO fallback).
        assert body["name"] == "transfer_validation"
        assert isinstance(body["score"], (int, float))
        assert isinstance(body["passed"], bool)
        assert isinstance(body["details"], dict)
        assert body["details"]["dataset"] == "train"

    def test_no_real_data_is_graceful_skip(self, no_real_data):
        """With no real data present the result is a graceful skip, so the gate passes vacuously."""
        from fastapi.testclient import TestClient

        from ml_service.main import app

        client = TestClient(app)
        response = client.post(
            "/ml/evaluate",
            json={
                "eval_name": "transfer_validation",
                "threshold": 0.70,
                "params": {"dataset": "train"},
            },
        )

        assert response.status_code == 200
        body = response.json()
        d = body["details"]
        assert d["applicable"] is False
        assert d["proposed"] is True
        assert "ground-truth" in d["reason"]
        # Gate-safety invariant: a graceful skip passes vacuously at score 1.0,
        # carrying the threshold the runner resolved (0.70 here).
        assert body["passed"] is True
        assert body["score"] == 1.0
        assert body["threshold"] == 0.70

    def test_zero_threshold_falls_back_to_default_floor(self, no_real_data):
        """threshold=0.0 (assurance default) -> runner falls back to the 0.50 floor."""
        from fastapi.testclient import TestClient

        from ml_service.main import app

        client = TestClient(app)
        response = client.post(
            "/ml/evaluate",
            json={
                "eval_name": "transfer_validation",
                "threshold": 0.0,
                "params": {"dataset": "train"},
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["threshold"] == 0.50  # fell back from 0.0
        assert body["passed"] is True
        assert body["details"]["applicable"] is False
