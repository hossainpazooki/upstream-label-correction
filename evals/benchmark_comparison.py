import json
from pathlib import Path
from typing import TYPE_CHECKING

from evals import EvalResult

if TYPE_CHECKING:
    from core.storage import StorageBackend

#: Minimum best-Jaccard overlap for the benchmark check to PASS. The old default
#: of 0.0 passed on ANY single-gene overlap — a no-op gate; this non-trivial
#: floor requires real recovery of the known marker set (~5+ overlapping genes
#: for a typical ~30-gene panel) rather than a one-gene fluke.
DEFAULT_BENCHMARK_JACCARD = 0.10


class BenchmarkComparisonEval:
    """Compare agent-selected panel against published benchmark signatures."""

    def __init__(self, fixtures_path: str | None = None, storage_backend: "StorageBackend | None" = None):
        if storage_backend is not None and fixtures_path:
            data_bytes = storage_backend.read_bytes(fixtures_path)
            data = json.loads(data_bytes)
        else:
            path = Path(fixtures_path or Path(__file__).parent / "fixtures" / "known_msi_signatures.json")
            with open(path) as f:
                data = json.load(f)
        self.benchmarks = data["published_signatures"]

    def jaccard(self, a: set, b: set) -> float:
        if not a and not b:
            return 1.0
        return len(a & b) / len(a | b)

    def evaluate(
        self,
        agent_panel: list[str],
        benchmark_name: str | None = None,
        threshold: float = DEFAULT_BENCHMARK_JACCARD,
    ) -> EvalResult:
        """Compare an agent-selected panel to published MSI signatures (marker recovery).

        PASS only if the best Jaccard overlap clears ``threshold`` (default
        ``DEFAULT_BENCHMARK_JACCARD``). The previous default of 0.0 passed on any
        single-gene overlap — a no-op gate — which this replaces.

        Honest scope: this is **not** independent external validation. The
        reference signatures live in the SAME gene namespace the synthetic
        generator plants its MSI/pathway signal into (the fixture's pathway block
        is byte-identical to ``core.constants.KNOWN_MSI_PATHWAY_MARKERS``), so a
        high overlap mostly confirms the panel recovered the known *planted*
        markers — a self-consistency check, not an outside-the-generator oracle
        (cf. gap #1/#3). ``details["independent_reference"]`` records this.
        """
        agent_set = set(agent_panel)
        comparisons = {}
        best_jaccard = 0.0

        benchmarks_to_check = (
            {benchmark_name: self.benchmarks[benchmark_name]}
            if benchmark_name and benchmark_name in self.benchmarks
            else self.benchmarks
        )

        for name, genes in benchmarks_to_check.items():
            bench_set = set(genes)
            j = self.jaccard(agent_set, bench_set)
            overlap = sorted(agent_set & bench_set)
            unique_to_agent = sorted(agent_set - bench_set)
            unique_to_benchmark = sorted(bench_set - agent_set)
            comparisons[name] = {
                "jaccard": j,
                "overlap_count": len(overlap),
                "overlap_genes": overlap,
                "unique_to_agent": unique_to_agent,
                "unique_to_benchmark": unique_to_benchmark,
                "agent_panel_size": len(agent_set),
                "benchmark_size": len(bench_set),
            }
            best_jaccard = max(best_jaccard, j)

        return EvalResult(
            name="benchmark_comparison",
            passed=best_jaccard >= threshold,
            score=best_jaccard,
            threshold=threshold,
            details={
                "comparisons": comparisons,
                # The reference overlaps the generator's own planted namespace, so
                # this is marker-recovery / self-consistency, not external validation.
                "independent_reference": False,
                "reference_note": (
                    "published signatures share the generator's planted gene "
                    "namespace; this is panel/marker recovery, not an outside-"
                    "the-generator oracle (gap #1/#3)"
                ),
            },
        )
