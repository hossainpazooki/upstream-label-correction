"""Build training datasets for SLM fine-tuning.

Produces instruction-input-output triples from:
A) Ground-truth examples from known MSI pathway markers (~50)
B) Distillation examples via Anthropic API (~500)
C) Negative examples from housekeeping genes (~150)
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.storage import StorageBackend

from core.constants import (
    KNOWN_MSI_PATHWAY_MARKERS,
    PATHWAY_MECHANISMS,
)
from training.format_utils import split_dataset

logger = logging.getLogger(__name__)

_INSTRUCTION = (
    "Classify the following gene's relevance to microsatellite instability (MSI) "
    "in colorectal cancer. Return a JSON object with fields: gene, pathway, "
    "mechanism, confidence, and msi_relevant (boolean)."
)

# Common housekeeping genes unlikely to be MSI-specific
_HOUSEKEEPING_GENES = [
    "ACTB",
    "GAPDH",
    "HPRT1",
    "RPL13A",
    "SDHA",
    "TBP",
    "YWHAZ",
    "B2M",
    "HMBS",
    "HSP90AB1",
    "LDHA",
    "NONO",
    "PGK1",
    "PPIH",
    "PPIA",
    "RPLP0",
    "RPS18",
    "RPS9",
    "UBC",
    "UBB",
    "GUSB",
    "TFRC",
    "ALAS1",
    "IPO8",
    "POLR2A",
    "PSMC4",
    "PUM1",
    "RPL30",
    "RPS13",
    "SF3A1",
]


def build_ground_truth_examples() -> list[dict]:
    """Iterate KNOWN_MSI_PATHWAY_MARKERS + PATHWAY_MECHANISMS, produce ~50 instruction-input-output triples."""
    examples: list[dict] = []

    for pathway, genes in KNOWN_MSI_PATHWAY_MARKERS.items():
        mechanism = PATHWAY_MECHANISMS.get(pathway, "")
        for gene in genes:
            output = {
                "gene": gene,
                "pathway": pathway,
                "mechanism": mechanism,
                "confidence": 0.95,
                "msi_relevant": True,
            }
            examples.append(
                {
                    "instruction": _INSTRUCTION,
                    "input": f"Gene: {gene}\nContext: msi_classification",
                    "output": json.dumps(output),
                    "source": "ground_truth",
                    "pathway": pathway,
                }
            )

    # Add cross-pathway examples with multiple pathway annotations
    multi_pathway_genes: dict[str, list[str]] = {}
    for pathway, genes in KNOWN_MSI_PATHWAY_MARKERS.items():
        for gene in genes:
            multi_pathway_genes.setdefault(gene, []).append(pathway)

    for gene, pathways in multi_pathway_genes.items():
        if len(pathways) > 1:
            output = {
                "gene": gene,
                "pathway": ", ".join(pathways),
                "mechanism": "; ".join(PATHWAY_MECHANISMS.get(p, "") for p in pathways),
                "confidence": 0.95,
                "msi_relevant": True,
            }
            examples.append(
                {
                    "instruction": _INSTRUCTION,
                    "input": f"Gene: {gene}\nContext: multi_pathway_analysis",
                    "output": json.dumps(output),
                    "source": "ground_truth",
                    "pathway": ", ".join(pathways),
                }
            )

    logger.info("Built %d ground truth examples", len(examples))
    return examples


async def build_distillation_examples(
    genes: list[str],
    n_per_gene: int = 3,
) -> list[dict]:
    """Call Anthropic API to generate examples, verify against HallucinationDetectionEval.

    Target ~500 examples from distillation.
    """
    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic package not installed; skipping distillation examples")
        return []

    client = anthropic.Anthropic()
    examples: list[dict] = []

    for gene in genes:
        for i in range(n_per_gene):
            context_variants = [
                "msi_classification",
                "biomarker_discovery",
                "pathway_analysis",
            ]
            context = context_variants[i % len(context_variants)]

            prompt = (
                f"You are a genomics expert. For the gene {gene}, provide a JSON object "
                f"with these fields:\n"
                f"- gene: the gene symbol\n"
                f"- pathway: the biological pathway (or 'none_established' if unknown)\n"
                f"- mechanism: brief mechanism description\n"
                f"- confidence: float 0-1\n"
                f"- msi_relevant: boolean\n"
                f"Context: {context}\n"
                f"Return ONLY valid JSON, no markdown."
            )

            try:
                response = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=512,
                    messages=[{"role": "user", "content": prompt}],
                )
                output_text = response.content[0].text.strip()

                # Validate JSON
                parsed = json.loads(output_text)
                if not isinstance(parsed, dict) or "gene" not in parsed:
                    continue

                examples.append(
                    {
                        "instruction": _INSTRUCTION,
                        "input": f"Gene: {gene}\nContext: {context}",
                        "output": output_text,
                        "source": "distillation",
                        "pathway": parsed.get("pathway", "unknown"),
                    }
                )
            except Exception:
                logger.warning("Failed to generate distillation example for %s", gene)
                continue

    # Verify with HallucinationDetectionEval if examples have citations
    from evals.hallucination_detection import HallucinationDetectionEval

    evaluator = HallucinationDetectionEval()
    interpretations = []
    for ex in examples:
        try:
            parsed = json.loads(ex["output"])
            if "pubmed_ids" in parsed:
                interpretations.append(parsed)
        except json.JSONDecodeError:
            continue

    if interpretations:
        result = evaluator.evaluate(interpretations)
        logger.info(
            "Hallucination eval on distillation: score=%.2f passed=%s",
            result.score,
            result.passed,
        )

    logger.info("Built %d distillation examples", len(examples))
    return examples


def build_negative_examples(genes: list[str] | None = None) -> list[dict]:
    """Housekeeping genes with pathway: none_established. ~150 examples."""
    genes = genes or _HOUSEKEEPING_GENES
    examples: list[dict] = []

    contexts = [
        "msi_classification",
        "biomarker_discovery",
        "pathway_analysis",
        "differential_expression",
        "clinical_correlation",
    ]

    for gene in genes:
        for context in contexts:
            output = {
                "gene": gene,
                "pathway": "none_established",
                "mechanism": (
                    f"{gene} is a housekeeping gene with no established specific role "
                    f"in microsatellite instability pathways."
                ),
                "confidence": 0.90,
                "msi_relevant": False,
            }
            examples.append(
                {
                    "instruction": _INSTRUCTION,
                    "input": f"Gene: {gene}\nContext: {context}",
                    "output": json.dumps(output),
                    "source": "negative",
                    "pathway": "none_established",
                }
            )

    logger.info("Built %d negative examples", len(examples))
    return examples


def build_full_dataset(
    output_path: str | None = None,
    storage: StorageBackend | None = None,
) -> dict:
    """Orchestrate A+B+C, split 80/10/10, return stats dict.

    Note: Distillation examples (B) require async and the Anthropic API.
    This synchronous function builds only ground-truth (A) and negative (C) examples.
    Use build_distillation_examples separately for (B).
    """
    ground_truth = build_ground_truth_examples()
    negatives = build_negative_examples()

    all_examples = ground_truth + negatives
    train, val, test = split_dataset(all_examples)

    dataset = {
        "train": train,
        "val": val,
        "test": test,
    }

    stats = {
        "total": len(all_examples),
        "ground_truth": len(ground_truth),
        "negative": len(negatives),
        "train": len(train),
        "val": len(val),
        "test": len(test),
    }

    if output_path:
        serialized = json.dumps(dataset, indent=2).encode()
        if storage is not None:
            storage.write_bytes(output_path, serialized)
        else:
            from pathlib import Path

            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(serialized)

    logger.info("Built full dataset: %s", stats)
    return stats
