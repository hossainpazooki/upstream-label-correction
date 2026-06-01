"""Tests for the AdversarialRobustnessEval evaluator."""

from pathlib import Path

import pytest

from evals.adversarial_robustness import AdversarialRobustnessEval

FIXTURES_PATH = str(
    Path(__file__).resolve().parent.parent.parent / "evals" / "fixtures" / "adversarial" / "probes.json"
)


@pytest.fixture
def evaluator():
    return AdversarialRobustnessEval(fixtures_path=FIXTURES_PATH)


async def _resisting_model(probe):
    """A well-behaved model: returns a clean classification, leaks nothing."""
    return "classification: pathway none_established, msi_relevant false"


async def _fully_compromised_model(probe):
    """A model that fails every probe by echoing its first compromise marker."""
    return "leaked -> " + probe["compromise_markers"][0]


class TestAdversarialRobustnessEval:
    @pytest.mark.asyncio
    async def test_all_probes_resisted_passes(self, evaluator):
        """A model that leaks nothing resists every probe -> score 1.0, PASS."""
        result = await evaluator.evaluate(_resisting_model)
        assert result.passed is True
        assert result.score == 1.0
        assert result.name == "adversarial_robustness"
        assert result.details["resisted"] == result.details["total_probes"]
        assert result.details["failed_probes"] == []

    @pytest.mark.asyncio
    async def test_fully_compromised_fails(self, evaluator):
        """A model that emits every probe's marker fails the gate -> score 0.0."""
        result = await evaluator.evaluate(_fully_compromised_model)
        assert result.passed is False
        assert result.score == 0.0
        assert len(result.details["failed_probes"]) == result.details["total_probes"]

    @pytest.mark.asyncio
    async def test_single_leak_fails_at_default_threshold(self, evaluator):
        """Default threshold is 1.0 -- a single leaked probe fails the gate."""

        async def _one_leak(probe):
            if probe["id"] == "pe-001":
                return probe["compromise_markers"][0]
            return "clean response"

        result = await evaluator.evaluate(_one_leak)
        total = result.details["total_probes"]
        assert result.threshold == 1.0
        assert result.passed is False
        assert result.score == (total - 1) / total
        assert result.details["failed_probes"] == ["pe-001"]

    @pytest.mark.asyncio
    async def test_explicit_lower_threshold_tolerates_one_leak(self, evaluator):
        """An explicit lower threshold lets a near-perfect score pass."""

        async def _one_leak(probe):
            if probe["id"] == "pe-001":
                return probe["compromise_markers"][0]
            return "clean response"

        result = await evaluator.evaluate(_one_leak, threshold=0.5)
        assert result.threshold == 0.5
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_score_reflects_per_class_resistance(self, evaluator):
        """A model compromised only on the injection channel still resists extraction."""

        async def _leak_injection_only(probe):
            if probe["attack_class"] == "indirect_injection":
                return probe["compromise_markers"][0]
            return "clean"

        result = await evaluator.evaluate(_leak_injection_only)
        by_class = result.details["by_attack_class"]
        assert by_class["prompt_extraction"]["resisted"] == by_class["prompt_extraction"]["total"]
        assert by_class["indirect_injection"]["resisted"] == 0
        expected = by_class["prompt_extraction"]["total"] / result.details["total_probes"]
        assert result.score == expected
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_result_conforms_to_eval_contract(self, evaluator):
        """The result is an EvalResult with the five contract fields."""
        result = await evaluator.evaluate(_resisting_model)
        assert isinstance(result.name, str)
        assert isinstance(result.passed, bool)
        assert isinstance(result.score, float)
        assert isinstance(result.threshold, float)
        assert isinstance(result.details, dict)
        assert result.name == "adversarial_robustness"

    @pytest.mark.asyncio
    async def test_details_structure(self, evaluator):
        """The details dict carries the expected keys, including corpus version."""
        result = await evaluator.evaluate(_resisting_model)
        for key in ("total_probes", "resisted", "failed_probes", "by_attack_class", "corpus_version"):
            assert key in result.details
        assert isinstance(result.details["corpus_version"], str)
        assert result.details["corpus_version"] == evaluator.corpus_version

    def test_corpus_has_both_attack_classes(self, evaluator):
        """The versioned corpus covers prompt-extraction and indirect-injection probes."""
        classes = {probe["attack_class"] for probe in evaluator.probes}
        assert classes == {"prompt_extraction", "indirect_injection"}
        for probe in evaluator.probes:
            for key in ("id", "attack_class", "channel", "probe_input", "compromise_markers"):
                assert key in probe


# ---------------------------------------------------------------------------
# Gate integration: ml_service /ml/evaluate eval-routing path
#
# Replaces the former intents.assurance.AssuranceLoop coupling
# (test_registered_in_assurance_loop / test_assurance_adapter_runs_corpus_through_slm),
# which was removed when the Python intents/ package was decommissioned. These
# exercise the end-to-end gate via POST eval_name="adversarial_robustness".
# ---------------------------------------------------------------------------


def _make_explainer_factory(classify_gene):
    """Build a get_explainer() replacement returning a fake explainer.

    ``classify_gene`` is the async ``(self, gene, target) -> dict`` coroutine the
    fake exposes, matching training.explainer.Explainer.classify_gene's signature.
    """

    class _FakeExplainer:
        pass

    _FakeExplainer.classify_gene = classify_gene
    return lambda: _FakeExplainer()


class TestAdversarialRobustnessRouting:
    """Integration coverage for the ml_service /ml/evaluate routing path."""

    def test_resisting_model_passes_via_endpoint(self, monkeypatch):
        """A benign SLM that leaks nothing resists every probe -> score 1.0, PASS."""
        from fastapi.testclient import TestClient

        from ml_service.main import app

        async def classify_gene(self, gene, target):
            # Leaks neither prompt-extraction headers nor injection canaries.
            return {"classification": "none", "msi_relevant": False}

        # The helper imports get_explainer at call time, so patch the source module.
        monkeypatch.setattr("training.explainer.get_explainer", _make_explainer_factory(classify_gene))

        client = TestClient(app)
        response = client.post(
            "/ml/evaluate",
            json={"eval_name": "adversarial_robustness", "threshold": 1.0, "params": {}},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "adversarial_robustness"
        assert body["passed"] is True
        assert body["score"] == 1.0
        for key in ("total_probes", "resisted", "failed_probes", "by_attack_class", "corpus_version"):
            assert key in body["details"]

    def test_leaking_model_fails_via_endpoint(self, monkeypatch):
        """An SLM that echoes the probe input leaks injection canaries -> PASS is False."""
        from fastapi.testclient import TestClient

        from ml_service.main import app

        async def classify_gene(self, gene, target):
            # Echo both positional args back: for document_rag probes the second
            # arg is the probe_input, which embeds the injection canary marker, so
            # at least one probe is compromised -> score < 1.0 at threshold 1.0.
            return {"gene": gene, "target": target}

        monkeypatch.setattr("training.explainer.get_explainer", _make_explainer_factory(classify_gene))

        client = TestClient(app)
        response = client.post(
            "/ml/evaluate",
            json={"eval_name": "adversarial_robustness", "threshold": 1.0, "params": {}},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "adversarial_robustness"
        assert body["passed"] is False
        assert body["score"] < 1.0
