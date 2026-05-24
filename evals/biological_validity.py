import json
from pathlib import Path
from typing import TYPE_CHECKING

from evals import EvalResult

if TYPE_CHECKING:
    from core.storage import StorageBackend


class BiologicalValidityEval:
    """Evaluate if agent-selected genes cover known MSI pathways."""

    def __init__(self, fixtures_path: str | None = None, storage_backend: "StorageBackend | None" = None):
        if storage_backend is not None and fixtures_path:
            data_bytes = storage_backend.read_bytes(fixtures_path)
            data = json.loads(data_bytes)
        else:
            path = Path(fixtures_path or Path(__file__).parent / "fixtures" / "known_msi_signatures.json")
            with open(path) as f:
                data = json.load(f)
        self.pathways = data["pathways"]

    def evaluate(self, agent_selected_genes: list[str], threshold: float = 0.60) -> EvalResult:
        """Score = fraction of pathways with at least 1 gene represented.
        PASS if score >= threshold (default 60%)."""
        gene_set = set(agent_selected_genes)
        pathways_covered = 0
        pathway_details = {}
        for pathway, genes in self.pathways.items():
            overlap = gene_set & set(genes)
            covered = len(overlap) > 0
            pathway_details[pathway] = {
                "covered": covered,
                "genes_found": sorted(overlap),
                "genes_expected": genes,
            }
            if covered:
                pathways_covered += 1

        score = pathways_covered / len(self.pathways) if self.pathways else 0
        return EvalResult(
            name="biological_validity",
            passed=score >= threshold,
            score=score,
            threshold=threshold,
            details={
                "pathways_covered": pathways_covered,
                "total_pathways": len(self.pathways),
                "pathway_details": pathway_details,
            },
        )
