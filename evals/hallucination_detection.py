from evals import EvalResult


class HallucinationDetectionEval:
    """Evaluate hallucination rate in generated interpretations by verifying PubMed citations."""

    def __init__(self, pubmed_verifier=None):
        self.pubmed_verifier = pubmed_verifier or self._default_verifier

    @staticmethod
    def _default_verifier(pmid: str) -> bool:
        """Verify a PubMed ID via E-utilities API. Returns True if valid."""
        try:
            import httpx

            resp = httpx.get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
                params={"db": "pubmed", "id": pmid, "retmode": "json"},
                timeout=10,
            )
            data = resp.json()
            result = data.get("result", {})
            return pmid in result and "error" not in result.get(pmid, {})
        except Exception:
            return False

    def evaluate(self, interpretations: list[dict], threshold: float = 0.90) -> EvalResult:
        """For each cited PubMed ID, verify existence. Score = fraction verifiable.
        PASS if >= threshold."""
        total_citations = 0
        verified_citations = 0
        unverified = []

        for interp in interpretations:
            pmids = interp.get("pubmed_ids", [])
            for pmid in pmids:
                total_citations += 1
                if self.pubmed_verifier(str(pmid)):
                    verified_citations += 1
                else:
                    unverified.append(str(pmid))

        score = verified_citations / total_citations if total_citations > 0 else 1.0
        return EvalResult(
            name="hallucination_detection",
            passed=score >= threshold,
            score=score,
            threshold=threshold,
            details={
                "total_citations": total_citations,
                "verified_citations": verified_citations,
                "unverified_pmids": unverified,
            },
        )
