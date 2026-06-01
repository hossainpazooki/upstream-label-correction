"""Integration coverage for the ml_service /ml/evaluate reproducibility routing path.

Mirrors tests/test_evals/test_adversarial_robustness.py::TestAdversarialRobustnessRouting:
a FastAPI TestClient drives POST /ml/evaluate with eval_name="reproducibility" and we
assert the ROUTING wires up correctly (eval_name -> _eval_reproducibility runner ->
well-formed dict with name/passed/score/threshold/details). The evaluator internals are
already covered by tests/test_evals/test_reproducibility.py, so we do NOT re-test them.

Mock seam (documented per task): ml_service.main._eval_reproducibility imports
``ReproducibilityEval`` *and* ``COSMOInspiredPipeline`` lazily at call time. The lightest,
fully deterministic seam is to patch ``evals.reproducibility.ReproducibilityEval`` so its
``.evaluate(...)`` returns a canned EvalResult. This short-circuits the construction of the
real evaluator before ``pipeline_callable`` is ever invoked, so the SLOW
``COSMOInspiredPipeline().run(...)`` path never executes and the test stays fast.
"""

from evals import EvalResult


class _FakeReproducibilityEval:
    """Drop-in stand-in for evals.ReproducibilityEval that returns a canned result.

    Captures the call so the test can assert the runner forwarded the gate threshold.
    """

    last_call: dict = {}

    def evaluate(self, pipeline_callable, n_runs=10, top_k=20, threshold=0.85):
        # Record what the runner passed, but never invoke pipeline_callable: that is
        # what keeps the COSMOInspiredPipeline().run(...) path (SLOW) from running.
        type(self).last_call = {"n_runs": n_runs, "top_k": top_k, "threshold": threshold}
        return EvalResult(
            name="reproducibility",
            passed=threshold <= 0.95,
            score=0.95,
            threshold=threshold,
            details={
                "n_runs": n_runs,
                "top_k": top_k,
                "pairwise_jaccard_scores": [0.95],
                "min_jaccard": 0.95,
                "max_jaccard": 0.95,
            },
        )


class TestReproducibilityRouting:
    """Integration coverage for the ml_service /ml/evaluate reproducibility route."""

    def test_reproducibility_routes_to_runner(self, monkeypatch):
        """POST eval_name=reproducibility -> _eval_reproducibility -> well-formed dict."""
        from fastapi.testclient import TestClient

        from ml_service.main import app

        # The helper imports ReproducibilityEval at call time, so patch the source module.
        _FakeReproducibilityEval.last_call = {}
        monkeypatch.setattr("evals.reproducibility.ReproducibilityEval", _FakeReproducibilityEval)

        client = TestClient(app)
        response = client.post(
            "/ml/evaluate",
            json={"eval_name": "reproducibility", "threshold": 0.85, "params": {}},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "reproducibility"
        assert body["passed"] is True
        assert body["score"] == 0.95
        assert body["threshold"] == 0.85
        for key in ("n_runs", "top_k", "pairwise_jaccard_scores", "min_jaccard", "max_jaccard"):
            assert key in body["details"]
        # The runner forwards the gate threshold and its fixed n_runs/top_k=20 to the eval.
        assert _FakeReproducibilityEval.last_call["threshold"] == 0.85
        assert _FakeReproducibilityEval.last_call["top_k"] == 20

    def test_reproducibility_threshold_forwarded(self, monkeypatch):
        """A high gate threshold flips passed to False, proving threshold is routed through."""
        from fastapi.testclient import TestClient

        from ml_service.main import app

        monkeypatch.setattr("evals.reproducibility.ReproducibilityEval", _FakeReproducibilityEval)

        client = TestClient(app)
        response = client.post(
            "/ml/evaluate",
            json={"eval_name": "reproducibility", "threshold": 0.99, "params": {}},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "reproducibility"
        assert body["threshold"] == 0.99
        assert body["passed"] is False
