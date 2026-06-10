"""Integration coverage for the ml_service /ml/evaluate mislabel_detection routing.

Mirrors tests/test_evals/test_reproducibility_routing.py: a FastAPI TestClient drives
POST /ml/evaluate with eval_name="mislabel_detection" and we assert the ROUTING wires
up correctly — in particular that ``params["improve_mode"]`` selects the lever:

* default / "threshold" -> tuned distance threshold (existing contract, unchanged);
* "retrain"/"both"      -> the held-out classifier-retrain F1 is the gated score.

The CLUE loop internals (threshold tuning, retrain/no-leakage seeding) are covered by
tests/test_clue_loop.py, so here we patch the two heavy inner calls
(``clue.loop.tune_decision_threshold`` and ``clue.loop.retrain_and_score``) to keep the
routing test fast and fully deterministic — we are testing the wiring, not the math.
"""

import pytest

pytest.importorskip("sklearn")

# Caller-supplied cohort params. Post-gap-#5 the gate IGNORES these (seed,
# sizes, fraction) and pins them server-side — they are kept here precisely to
# assert they no longer steer the cohort.
SMALL = {"n_samples": 30, "n_genes_proteomics": 150, "n_genes_rnaseq": 200, "seed": 7}

# Canned tuned-threshold result; n_molecular_swaps mirrors the metrics dict shape.
_FAKE_TUNE = (0.5, {"precision": 1.0, "recall": 1.0, "f1": 1.0, "n_molecular_swaps": 4})


@pytest.fixture
def small_gate(monkeypatch):
    """Shrink the server-pinned gate cohort so routing tests stay fast.

    The gate ignores caller cohort params (gap #5), so a tiny cohort can no
    longer be requested via params; tests pin the policy constants down instead.
    """
    monkeypatch.setattr("ml_service.main._GATE_N_SAMPLES", 30)
    monkeypatch.setattr("ml_service.main._GATE_N_GENES_PROTEOMICS", 150)
    monkeypatch.setattr("ml_service.main._GATE_N_GENES_RNASEQ", 200)


class TestMislabelDetectionRouting:
    """Integration coverage for the /ml/evaluate mislabel_detection route + improve_mode."""

    def test_default_routes_to_threshold_path(self, monkeypatch, small_gate):
        """No improve_mode -> tuned distance threshold (byte-identical default contract)."""
        from fastapi.testclient import TestClient

        from ml_service.main import app

        monkeypatch.setattr("clue.loop.tune_decision_threshold", lambda *a, **k: _FAKE_TUNE)

        client = TestClient(app)
        response = client.post(
            "/ml/evaluate",
            json={"eval_name": "mislabel_detection", "threshold": 0.8, "params": dict(SMALL)},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "mislabel_detection"
        assert body["score"] == 1.0
        assert body["passed"] is True
        # The default path reports the tuned threshold and tags itself, unchanged.
        assert body["details"]["best_threshold"] == 0.5
        assert body["details"]["tuned"] is True
        # Retrain-only keys must NOT leak into the default contract.
        assert "improve_mode" not in body["details"]

    def test_retrain_routes_to_held_out_classifier_f1(self, monkeypatch, small_gate):
        """improve_mode=retrain -> score is the held-out retrain F1, details name the lever.

        Also guards gap #5: the disjoint train seed is derived from the
        server-assigned intent_id, NOT from the caller-supplied ``params["seed"]``
        (7 here), so a caller cannot seed-shop the gate cohort.
        """
        from fastapi.testclient import TestClient

        from ml_service.main import _gate_seed, app

        monkeypatch.setattr("clue.loop.tune_decision_threshold", lambda *a, **k: _FAKE_TUNE)
        monkeypatch.setattr(
            "clue.loop.retrain_and_score",
            lambda *a, **k: {"f1": 0.6, "precision": 0.55, "recall": 0.65},
        )

        client = TestClient(app)
        response = client.post(
            "/ml/evaluate",
            json={
                "eval_name": "mislabel_detection",
                "threshold": 0.5,
                "intent_id": "itest-seed-derivation",
                "params": {**SMALL, "improve_mode": "retrain", "mislabel_fraction": 0.2},
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "mislabel_detection"
        assert body["score"] == 0.6  # held-out retrain F1 is the headline / gated score
        assert body["passed"] is True
        d = body["details"]
        assert d["improve_mode"] == "retrain"
        assert d["retrain_f1"] == 0.6
        assert d["threshold_f1"] == 1.0  # distance path still reported alongside
        # Train seed = intent_id-derived seed + offset (iter 0) — NOT the caller's seed=7.
        assert d["train_seed"] == _gate_seed("itest-seed-derivation") + 1000
        assert d["train_seed"] != 7 + 1000

    def test_both_gates_on_retrain_but_reports_threshold(self, monkeypatch, small_gate):
        """improve_mode=both -> gate on retrain F1, threshold F1 retained in details."""
        from fastapi.testclient import TestClient

        from ml_service.main import app

        monkeypatch.setattr("clue.loop.tune_decision_threshold", lambda *a, **k: _FAKE_TUNE)
        monkeypatch.setattr(
            "clue.loop.retrain_and_score",
            lambda *a, **k: {"f1": 0.3, "precision": 0.3, "recall": 0.3},
        )

        client = TestClient(app)
        response = client.post(
            "/ml/evaluate",
            json={
                "eval_name": "mislabel_detection",
                "threshold": 0.5,
                "params": {**SMALL, "improve_mode": "both", "mislabel_fraction": 0.2},
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["score"] == 0.3
        assert body["passed"] is False  # 0.3 < 0.5 gate, driven by retrain F1
        assert body["details"]["threshold_f1"] == 1.0
