"""SLM evaluation suite: biological validity and hallucination detection."""

from __future__ import annotations

import logging
import time
from typing import Any

from evals.biological_validity import BiologicalValidityEval
from evals.hallucination_detection import HallucinationDetectionEval

logger = logging.getLogger(__name__)


class SLMEvalSuite:
    """Runner over two evaluators (biological validity + hallucination detection); not itself an ``EvalResult`` producer."""

    def __init__(self, slm_explainer: Any) -> None:
        self.slm_explainer = slm_explainer

    async def run(self, test_genes: list[str]) -> dict:
        """Run BiologicalValidityEval and HallucinationDetectionEval against SLM outputs.

        Returns
        -------
        dict
            {
                hallucination: EvalResult,
                biological_validity: EvalResult,
                pass: bool,
                latency_ms_per_gene: float,
            }
        """
        # Generate SLM outputs for all test genes
        outputs: list[dict] = []
        start = time.monotonic()

        for gene in test_genes:
            result = await self.slm_explainer.classify_gene(gene, "msi")
            outputs.append(result)

        elapsed_ms = (time.monotonic() - start) * 1000
        latency_per_gene = elapsed_ms / len(test_genes) if test_genes else 0

        # Extract gene names for biological validity
        selected_genes = [o.get("gene", "") for o in outputs if o.get("msi_relevant", False)]

        # Biological validity eval
        bio_eval = BiologicalValidityEval()
        bio_result = bio_eval.evaluate(selected_genes)

        # Hallucination detection eval
        halluc_eval = HallucinationDetectionEval()
        halluc_result = halluc_eval.evaluate(outputs)

        overall_pass = bio_result.passed and halluc_result.passed

        logger.info(
            "SLM eval: bio_validity=%.2f (%s), hallucination=%.2f (%s), latency=%.1fms/gene",
            bio_result.score,
            "PASS" if bio_result.passed else "FAIL",
            halluc_result.score,
            "PASS" if halluc_result.passed else "FAIL",
            latency_per_gene,
        )

        return {
            "hallucination": halluc_result,
            "biological_validity": bio_result,
            "pass": overall_pass,
            "latency_ms_per_gene": latency_per_gene,
        }
