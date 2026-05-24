"""DSPy module for sample quality control prompt optimization."""

from __future__ import annotations

try:
    import dspy

    _DSPY_AVAILABLE = True
except ImportError:
    dspy = None
    _DSPY_AVAILABLE = False

if _DSPY_AVAILABLE:

    class AnalyzeClassificationSignature(dspy.Signature):
        """Analyze classification-based QC results."""

        classification_results: str = dspy.InputField(desc="Classification QC results")
        target: str = dspy.InputField(desc="Prediction target used for classification")
        analysis: str = dspy.OutputField(desc="Analysis of classification QC")
        flagged_samples: str = dspy.OutputField(desc="Comma-separated list of flagged sample IDs")
        confidence: float = dspy.OutputField(desc="Confidence in flagging between 0 and 1")

    class AnalyzeDistanceSignature(dspy.Signature):
        """Analyze distance matrix-based QC results."""

        distance_results: str = dspy.InputField(desc="Distance matrix QC results")
        analysis: str = dspy.OutputField(desc="Analysis of distance-based QC")
        flagged_samples: str = dspy.OutputField(desc="Comma-separated list of flagged sample IDs")
        confidence: float = dspy.OutputField(desc="Confidence in flagging between 0 and 1")

    class CrossValidateSignature(dspy.Signature):
        """Cross-validate flags from multiple QC methods."""

        classification_flags: str = dspy.InputField(desc="Flags from classification QC")
        distance_flags: str = dspy.InputField(desc="Flags from distance QC")
        concordant_flags: str = dspy.OutputField(desc="Flags agreed upon by both methods")
        summary: str = dspy.OutputField(desc="Summary of cross-validation")
        concordance_rate: float = dspy.OutputField(desc="Rate of agreement between methods")

    class SampleQCModule(dspy.Module):
        """Multi-step DSPy module for sample quality control."""

        def __init__(self):
            super().__init__()
            self.analyze_classification = dspy.ChainOfThought(AnalyzeClassificationSignature)
            self.analyze_distance = dspy.ChainOfThought(AnalyzeDistanceSignature)
            self.cross_validate = dspy.ChainOfThought(CrossValidateSignature)

        def forward(self, classification_results, distance_results, target):
            classification = self.analyze_classification(classification_results=classification_results, target=target)
            distance = self.analyze_distance(distance_results=distance_results)
            result = self.cross_validate(
                classification_flags=classification.flagged_samples,
                distance_flags=distance.flagged_samples,
            )
            return result
