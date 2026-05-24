"""DSPy module for feature interpretation."""

from __future__ import annotations

try:
    import dspy

    _DSPY_AVAILABLE = True
except ImportError:
    dspy = None
    _DSPY_AVAILABLE = False

if _DSPY_AVAILABLE:

    class FeatureInterpretSignature(dspy.Signature):
        """Interpret a gene feature in biological context."""

        gene_name: str = dspy.InputField(desc="Gene symbol to interpret")
        expression_context: str = dspy.InputField(desc="Expression context and statistics")
        target: str = dspy.InputField(desc="Prediction target (e.g., msi, gender)")
        pathway: str = dspy.OutputField(desc="Biological pathway the gene belongs to")
        mechanism: str = dspy.OutputField(desc="Proposed mechanism linking gene to target")
        confidence: float = dspy.OutputField(desc="Confidence score between 0 and 1")
        pubmed_ids: str = dspy.OutputField(desc="Comma-separated PubMed IDs supporting interpretation")

    class FeatureInterpretModule(dspy.Module):
        """Single-step DSPy module for gene feature interpretation."""

        def __init__(self):
            super().__init__()
            self.interpret = dspy.ChainOfThought(FeatureInterpretSignature)

        def forward(self, gene_name, expression_context, target):
            return self.interpret(
                gene_name=gene_name,
                expression_context=expression_context,
                target=target,
            )
