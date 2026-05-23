import itertools

from evals import EvalResult


class ReproducibilityEval:
    """Evaluate reproducibility of feature selection across multiple runs."""

    def evaluate(self, pipeline_callable, n_runs: int = 10, top_k: int = 20, threshold: float = 0.85) -> EvalResult:
        """Run pipeline n times, measure pairwise Jaccard similarity of top-k features.
        PASS if average Jaccard >= threshold."""
        all_features = []
        for i in range(n_runs):
            result = pipeline_callable(seed=i)
            features = result[:top_k] if isinstance(result, list) else list(result)[:top_k]
            all_features.append(set(features))

        # Pairwise Jaccard
        jaccard_scores = []
        for a, b in itertools.combinations(all_features, 2):
            if len(a | b) == 0:
                jaccard_scores.append(1.0)
            else:
                jaccard_scores.append(len(a & b) / len(a | b))

        avg_jaccard = sum(jaccard_scores) / len(jaccard_scores) if jaccard_scores else 0
        return EvalResult(
            name="reproducibility",
            passed=avg_jaccard >= threshold,
            score=avg_jaccard,
            threshold=threshold,
            details={
                "n_runs": n_runs,
                "top_k": top_k,
                "pairwise_jaccard_scores": jaccard_scores,
                "min_jaccard": min(jaccard_scores) if jaccard_scores else 0,
                "max_jaccard": max(jaccard_scores) if jaccard_scores else 0,
            },
        )
