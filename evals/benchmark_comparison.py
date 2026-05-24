import json
from pathlib import Path
from typing import TYPE_CHECKING

from evals import EvalResult

if TYPE_CHECKING:
    from core.storage import StorageBackend


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

    def evaluate(self, agent_panel: list[str], benchmark_name: str | None = None) -> EvalResult:
        """Compare agent panel to published benchmarks. Returns overlap metrics."""
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
            passed=best_jaccard > 0,  # any overlap is useful
            score=best_jaccard,
            threshold=0.0,
            details={"comparisons": comparisons},
        )
