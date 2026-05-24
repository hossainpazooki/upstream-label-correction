"""DSPy module for biomarker discovery prompt optimization."""

from __future__ import annotations

try:
    import dspy

    _DSPY_AVAILABLE = True
except ImportError:
    dspy = None
    _DSPY_AVAILABLE = False

if _DSPY_AVAILABLE:

    class AssessDataQualitySignature(dspy.Signature):
        """Assess the quality of a genomics dataset for biomarker discovery."""

        dataset_summary: str = dspy.InputField(desc="Summary statistics of the dataset")
        assessment: str = dspy.OutputField(desc="Quality assessment narrative")
        quality_score: float = dspy.OutputField(desc="Quality score between 0 and 1")

    class EvaluateImputationSignature(dspy.Signature):
        """Evaluate the effectiveness of missing data imputation."""

        imputation_stats: str = dspy.InputField(desc="Statistics about the imputation process")
        evaluation: str = dspy.OutputField(desc="Evaluation of imputation quality")
        recommendation: str = dspy.OutputField(desc="Recommendation for imputation strategy")

    class InterpretFeaturesSignature(dspy.Signature):
        """Interpret selected features in biological context."""

        feature_list: str = dspy.InputField(desc="List of selected features/genes")
        target: str = dspy.InputField(desc="Prediction target (e.g., msi, gender)")
        interpretations: str = dspy.OutputField(desc="Biological interpretations of features")
        confidence: float = dspy.OutputField(desc="Confidence score between 0 and 1")

    class SynthesizeReportSignature(dspy.Signature):
        """Synthesize a final biomarker discovery report."""

        quality_assessment: str = dspy.InputField(desc="Data quality assessment")
        imputation_eval: str = dspy.InputField(desc="Imputation evaluation")
        feature_interpretations: str = dspy.InputField(desc="Feature interpretations")
        report: str = dspy.OutputField(desc="Final synthesized report")
        recommendations: str = dspy.OutputField(desc="Actionable recommendations")

    class BiomarkerDiscoveryModule(dspy.Module):
        """Multi-step DSPy module for biomarker discovery analysis."""

        def __init__(self):
            super().__init__()
            self.assess_quality = dspy.ChainOfThought(AssessDataQualitySignature)
            self.evaluate_imputation = dspy.ChainOfThought(EvaluateImputationSignature)
            self.interpret_features = dspy.ChainOfThought(InterpretFeaturesSignature)
            self.synthesize_report = dspy.ChainOfThought(SynthesizeReportSignature)

        def forward(self, dataset_summary, imputation_stats, feature_list, target):
            quality = self.assess_quality(dataset_summary=dataset_summary)
            imputation = self.evaluate_imputation(imputation_stats=imputation_stats)
            features = self.interpret_features(feature_list=feature_list, target=target)
            report = self.synthesize_report(
                quality_assessment=quality.assessment,
                imputation_eval=imputation.evaluation,
                feature_interpretations=features.interpretations,
            )
            return report
