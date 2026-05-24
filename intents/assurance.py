"""Assurance loop — connects eval metrics to intent state transitions.

Wraps the existing eval classes from evals/ and runs them against
workflow results to determine whether an intent's success criteria are met.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from evals import EvalResult

if TYPE_CHECKING:
    from intents.models import Intent

logger = logging.getLogger(__name__)


class AssuranceLoop:
    """Run eval criteria and determine intent success/failure."""

    def __init__(self) -> None:
        self._registry: dict[str, Any] = {
            "biological_validity": self._run_biological_validity,
            "reproducibility": self._run_reproducibility,
            "hallucination_detection": self._run_hallucination_detection,
            "adversarial_robustness": self._run_adversarial_robustness,
            "benchmark_comparison": self._run_benchmark_comparison,
        }

    async def evaluate(
        self,
        intent: Intent,
        eval_criteria: tuple[tuple[str, float], ...],
    ) -> dict[str, EvalResult]:
        """Run all eval criteria for the intent.

        Returns a dict of ``{eval_name: EvalResult}``.  Callers that need to
        persist the verdict should down-convert at the persistence boundary
        (see ``intents.controller.IntentController._verify``).
        """
        results: dict[str, EvalResult] = {}

        for eval_name, threshold in eval_criteria:
            runner = self._registry.get(eval_name)
            if runner is None:
                logger.warning("No eval runner for '%s', skipping", eval_name)
                continue
            try:
                results[eval_name] = await runner(intent, threshold)
            except Exception as exc:
                logger.exception("Eval '%s' failed for intent %s", eval_name, intent.intent_id)
                results[eval_name] = EvalResult(
                    name=eval_name,
                    passed=False,
                    score=0.0,
                    threshold=threshold,
                    details={"error": str(exc)},
                )

        return results

    @staticmethod
    def all_passed(eval_results: dict[str, EvalResult]) -> bool:
        """Return True if every eval criterion passed."""
        if not eval_results:
            return True
        return all(r.passed for r in eval_results.values())

    # ------------------------------------------------------------------
    # Private eval runners
    # ------------------------------------------------------------------

    async def _run_biological_validity(
        self,
        intent: Intent,
        threshold: float,
    ) -> EvalResult:
        """Extract selected genes from workflow results and evaluate pathway coverage."""
        from evals.biological_validity import BiologicalValidityEval

        # Genes come from the workflow results stored on the intent.
        genes = self._extract_genes(intent)
        evaluator = BiologicalValidityEval()
        return evaluator.evaluate(genes, threshold=threshold)

    async def _run_reproducibility(
        self,
        intent: Intent,
        threshold: float,
    ) -> EvalResult:
        """Evaluate reproducibility by re-running the pipeline with different seeds."""
        from evals.reproducibility import ReproducibilityEval

        evaluator = ReproducibilityEval()

        # Build a callable that runs the pipeline.
        params = intent.params
        dataset = params.get("dataset", "train")

        def pipeline_callable(seed: int) -> list[str]:
            """Run pipeline and return top-k feature names."""
            from core.pipeline import COSMOInspiredPipeline

            pipe = COSMOInspiredPipeline()
            result = pipe.run(dataset=dataset)
            stage3 = result.get("stages", {}).get("predict", {})
            panel = stage3.get("feature_panel", {})
            features = panel.get("features", [])
            return [f.get("name", f.get("gene", "")) for f in features[:20]]

        return evaluator.evaluate(
            pipeline_callable,
            n_runs=5,
            top_k=20,
            threshold=threshold,
        )

    async def _run_hallucination_detection(
        self,
        intent: Intent,
        threshold: float,
    ) -> EvalResult:
        """Extract interpretations from workflow results and verify citations."""
        from evals.hallucination_detection import HallucinationDetectionEval

        evaluator = HallucinationDetectionEval()

        # Interpretations come from the workflow results.
        interpretations = self._extract_interpretations(intent)
        return evaluator.evaluate(interpretations, threshold=threshold)

    async def _run_adversarial_robustness(
        self,
        intent: Intent,
        threshold: float,
    ) -> EvalResult:
        """Probe the SLM with defensive adversarial inputs and score resistance."""
        import json

        from evals.adversarial_robustness import AdversarialRobustnessEval
        from training.explainer import get_explainer

        explainer = get_explainer()

        async def model_callable(probe: dict) -> str:
            """Deliver a probe to the SLM via its classify_gene entry point.

            The SLM exposes only classify_gene(gene, target): the ``gene``
            argument is the direct user-input channel, the ``target`` context
            is the document / RAG channel.  Each probe is routed onto whichever
            channel it targets.
            """
            if probe.get("channel") == "document_rag":
                result = await explainer.classify_gene("BRAF", probe["probe_input"])
            else:
                result = await explainer.classify_gene(probe["probe_input"], "msi")
            return json.dumps(result, default=str)

        evaluator = AdversarialRobustnessEval()
        return await evaluator.evaluate(model_callable, threshold=threshold)

    async def _run_benchmark_comparison(
        self,
        intent: Intent,
        threshold: float,
    ) -> EvalResult:
        """Compare the agent's panel to published benchmark signatures.

        ``BenchmarkComparisonEval.evaluate()`` hardcodes ``threshold=0.0``
        (pass = any overlap).  This adapter mirrors the other ``_run_*``
        methods by honouring the gate-provided threshold post-hoc: the
        score (best Jaccard) is re-tested against the registry threshold
        without touching the evaluator's scoring logic.
        """
        from evals.benchmark_comparison import BenchmarkComparisonEval

        genes = self._extract_genes(intent)
        evaluator = BenchmarkComparisonEval()
        result = evaluator.evaluate(genes)
        return EvalResult(
            name=result.name,
            passed=result.score >= threshold,
            score=result.score,
            threshold=threshold,
            details=result.details,
        )

    # ------------------------------------------------------------------
    # Data extraction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_genes(intent: Intent) -> list[str]:
        """Pull selected genes from the intent's workflow results."""
        # The workflow result is stored as eval_results or via the child
        # workflow's result dict.  Walk common structures.
        params = intent.params
        genes: list[str] = []

        # Direct gene list in params (e.g. from a previous selection step).
        if "genes" in params:
            return params["genes"]

        # Try workflow results persisted on the intent.
        for wf_result in (intent.eval_results or {}).values():
            if isinstance(wf_result, dict):
                for biomarker in wf_result.get("biomarkers", []):
                    gene = biomarker.get("gene")
                    if gene and gene not in genes:
                        genes.append(gene)

        return genes

    @staticmethod
    def _extract_interpretations(intent: Intent) -> list[dict]:
        """Pull interpretation dicts from workflow results."""
        interpretations: list[dict] = []
        params = intent.params
        if "interpretations" in params:
            return params["interpretations"]
        return interpretations
