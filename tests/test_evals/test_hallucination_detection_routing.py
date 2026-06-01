"""Integration coverage for the ml_service /ml/evaluate hallucination_detection route.

Mirrors tests/test_evals/test_adversarial_robustness.py::TestAdversarialRobustnessRouting:
a FastAPI TestClient drives POST /ml/evaluate with eval_name="hallucination_detection" and
we assert the ROUTING wires up correctly (eval_name -> _eval_hallucination_detection runner
-> well-formed dict with name/passed/score/threshold/details). The evaluator internals are
already covered by tests/test_evals/test_hallucination_detection.py, so we do NOT re-test
them here.

Mock seam (documented per task): ml_service.main._eval_hallucination_detection imports
``HallucinationDetectionEval`` lazily at call time and constructs it with no verifier, which
means the DEFAULT verifier would make LIVE PubMed HTTP calls. To keep the test offline and
deterministic we patch ``evals.hallucination_detection.HallucinationDetectionEval`` so its
``.evaluate(...)`` returns a canned EvalResult — the real default verifier is never built and
no network call can be issued. As belt-and-suspenders, we also patch ``httpx.get`` to raise
so any accidental network attempt fails the test loudly instead of going out to the wire.
"""

import httpx
import pytest

from evals import EvalResult


class _FakeHallucinationDetectionEval:
    """Drop-in stand-in that returns a canned result with no verifier / no network."""

    last_call: dict = {}

    def __init__(self, pubmed_verifier=None):
        # A real default verifier is never created here, so no PubMed HTTP client exists.
        self.pubmed_verifier = pubmed_verifier

    def evaluate(self, interpretations, threshold=0.90):
        total = sum(len(i.get("pubmed_ids", [])) for i in interpretations)
        type(self).last_call = {"threshold": threshold, "total_citations": total}
        return EvalResult(
            name="hallucination_detection",
            passed=threshold <= 0.90,
            score=0.90,
            threshold=threshold,
            details={
                "total_citations": total,
                "verified_citations": total,
                "unverified_pmids": [],
            },
        )


@pytest.fixture
def _no_network(monkeypatch):
    """Make any HTTP attempt blow up so the test proves it never touches the wire."""

    def _boom(*args, **kwargs):
        raise AssertionError("hallucination_detection routing test attempted a network call")

    monkeypatch.setattr(httpx, "get", _boom)


class TestHallucinationDetectionRouting:
    """Integration coverage for the ml_service /ml/evaluate hallucination route."""

    def test_hallucination_routes_to_runner_no_network(self, monkeypatch, _no_network):
        """POST eval_name=hallucination_detection -> runner -> well-formed dict, no network."""
        from fastapi.testclient import TestClient

        from ml_service.main import app

        # The helper imports HallucinationDetectionEval at call time, so patch the source module.
        _FakeHallucinationDetectionEval.last_call = {}
        monkeypatch.setattr(
            "evals.hallucination_detection.HallucinationDetectionEval",
            _FakeHallucinationDetectionEval,
        )

        client = TestClient(app)
        response = client.post(
            "/ml/evaluate",
            json={
                "eval_name": "hallucination_detection",
                "threshold": 0.90,
                "params": {"interpretations": [{"text": "Gene X", "pubmed_ids": ["12345", "67890"]}]},
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "hallucination_detection"
        assert body["passed"] is True
        assert body["score"] == 0.90
        assert body["threshold"] == 0.90
        for key in ("total_citations", "verified_citations", "unverified_pmids"):
            assert key in body["details"]
        # The runner forwarded both the interpretations and the gate threshold to the eval.
        assert _FakeHallucinationDetectionEval.last_call["threshold"] == 0.90
        assert _FakeHallucinationDetectionEval.last_call["total_citations"] == 2

    def test_hallucination_threshold_forwarded(self, monkeypatch, _no_network):
        """A high gate threshold flips passed to False, proving threshold is routed through."""
        from fastapi.testclient import TestClient

        from ml_service.main import app

        monkeypatch.setattr(
            "evals.hallucination_detection.HallucinationDetectionEval",
            _FakeHallucinationDetectionEval,
        )

        client = TestClient(app)
        response = client.post(
            "/ml/evaluate",
            json={
                "eval_name": "hallucination_detection",
                "threshold": 0.99,
                "params": {"interpretations": []},
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "hallucination_detection"
        assert body["threshold"] == 0.99
        assert body["passed"] is False
