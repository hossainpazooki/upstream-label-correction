"""DSPy metrics wrapping existing eval framework."""

from __future__ import annotations

import re


def biological_validity_metric(example, prediction, trace=None) -> float:
    """Wraps BiologicalValidityEval. Extract genes from prediction, evaluate."""
    from evals.biological_validity import BiologicalValidityEval

    report_text = getattr(prediction, "report", "") or getattr(prediction, "interpretations", "")
    genes = extract_genes_from_report(report_text)
    if not genes:
        return 0.0

    evaluator = BiologicalValidityEval()
    result = evaluator.evaluate(genes, threshold=0.60)
    return result.score


def hallucination_metric(example, prediction, trace=None) -> float:
    """Wraps HallucinationDetectionEval."""
    from evals.hallucination_detection import HallucinationDetectionEval

    pubmed_ids_str = getattr(prediction, "pubmed_ids", "")
    if not pubmed_ids_str:
        return 1.0

    pmids = [p.strip() for p in pubmed_ids_str.split(",") if p.strip()]
    interpretations = [{"pubmed_ids": pmids}]

    evaluator = HallucinationDetectionEval()
    result = evaluator.evaluate(interpretations, threshold=0.90)
    return result.score


def composite_metric(example, prediction, trace=None) -> float:
    """Weighted combo, hard fail if hallucination < 0.90."""
    bio_score = biological_validity_metric(example, prediction, trace)
    hall_score = hallucination_metric(example, prediction, trace)

    if hall_score < 0.90:
        return 0.0

    return 0.6 * bio_score + 0.4 * hall_score


def extract_genes_from_report(report_text: str) -> list[str]:
    """Extract gene names from a report text using regex.

    Matches common gene name patterns: uppercase letters followed by
    optional digits (e.g., BRCA1, TP53, MLH1, TAP1).
    """
    pattern = r"\b([A-Z][A-Z0-9]{1,}[0-9]*)\b"
    candidates = re.findall(pattern, report_text)
    # Filter out common non-gene uppercase words
    stopwords = {
        "THE",
        "AND",
        "FOR",
        "NOT",
        "ARE",
        "BUT",
        "FROM",
        "WITH",
        "THIS",
        "THAT",
        "HAVE",
        "HAS",
        "HAD",
        "WAS",
        "WERE",
        "BEEN",
        "BEING",
        "WILL",
        "WOULD",
        "COULD",
        "SHOULD",
        "MAY",
        "MIGHT",
        "MUST",
        "SHALL",
        "CAN",
        "EACH",
        "WHICH",
        "THEIR",
        "ALL",
        "ANY",
        "DNA",
        "RNA",
        "QC",
        "MSI",
        "PCR",
        "WHO",
        "FDA",
    }
    return [g for g in candidates if g not in stopwords]
