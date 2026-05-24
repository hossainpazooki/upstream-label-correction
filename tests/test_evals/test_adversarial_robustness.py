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
# Gate integration
# ---------------------------------------------------------------------------


def test_registered_in_assurance_loop():
    """The evaluator is wired into the gate's runner registry."""
    from intents.assurance import AssuranceLoop

    assert "adversarial_robustness" in AssuranceLoop()._registry


@pytest.mark.asyncio
async def test_assurance_adapter_runs_corpus_through_slm(monkeypatch):
    """The gate adapter routes the real probe corpus through an injected SLM."""
    from intents.assurance import AssuranceLoop
    from intents.models import Intent

    class _MockExplainer:
        async def classify_gene(self, gene, target):
            return {
                "pathway": "none_established",
                "mechanism": "no leak",
                "confidence": 0.5,
                "msi_relevant": False,
            }

    monkeypatch.setattr(
        "training.explainer.get_explainer",
        lambda config=None: _MockExplainer(),
    )

    loop = AssuranceLoop()
    intent = Intent(intent_id="val-test", intent_type="validation", params={})
    result = await loop._run_adversarial_robustness(intent, 1.0)

    assert result.name == "adversarial_robustness"
    assert result.passed is True
    assert result.score == 1.0
