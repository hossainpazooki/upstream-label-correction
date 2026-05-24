"""Mine examples from pipeline runs for DSPy training."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.storage import StorageBackend

try:
    import dspy

    _DSPY_AVAILABLE = True
except ImportError:
    dspy = None
    _DSPY_AVAILABLE = False

logger = logging.getLogger(__name__)


class AutoPromptExampleMiner:
    """Mine examples from pipeline runs for DSPy training."""

    def __init__(self, storage: StorageBackend | None = None):
        self.storage = storage

    def mine_from_pipeline_run(self, run_results: dict) -> list[dict]:
        """Extract training examples from a completed pipeline run.

        Looks for dataset_summary, imputation_stats, feature_list, target,
        and report fields in the run results.
        """
        examples = []

        dataset_summary = run_results.get("dataset_summary", "")
        imputation_stats = run_results.get("imputation_stats", "")
        feature_list = run_results.get("feature_list", "")
        target = run_results.get("target", "")
        report = run_results.get("report", "")

        if dataset_summary and report:
            examples.append(
                {
                    "dataset_summary": dataset_summary,
                    "imputation_stats": imputation_stats,
                    "feature_list": feature_list,
                    "target": target,
                    "report": report,
                    "_input_keys": ["dataset_summary", "imputation_stats", "feature_list", "target"],
                }
            )

        interpretations = run_results.get("interpretations", [])
        for interp in interpretations:
            gene = interp.get("gene_name", "")
            if gene:
                examples.append(
                    {
                        "gene_name": gene,
                        "expression_context": interp.get("expression_context", ""),
                        "target": target,
                        "pathway": interp.get("pathway", ""),
                        "mechanism": interp.get("mechanism", ""),
                        "pubmed_ids": interp.get("pubmed_ids", ""),
                        "_input_keys": ["gene_name", "expression_context", "target"],
                    }
                )

        logger.info("Mined %d examples from pipeline run", len(examples))
        return examples

    def format_for_dspy(self, examples: list[dict]) -> list:
        """Convert mined examples to DSPy Example objects."""
        if not _DSPY_AVAILABLE:
            return examples

        dspy_examples = []
        for ex in examples:
            input_keys = ex.pop("_input_keys", [])
            example = dspy.Example(**ex)
            if input_keys:
                example = example.with_inputs(*input_keys)
            dspy_examples.append(example)
        return dspy_examples
