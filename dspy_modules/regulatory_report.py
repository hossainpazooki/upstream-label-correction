"""DSPy module for regulatory report generation."""

from __future__ import annotations

try:
    import dspy

    _DSPY_AVAILABLE = True
except ImportError:
    dspy = None
    _DSPY_AVAILABLE = False

if _DSPY_AVAILABLE:

    class RegulatoryReportSignature(dspy.Signature):
        """Generate a regulatory-compliant report from analysis results."""

        analysis_results: str = dspy.InputField(desc="Full analysis results")
        biomarker_panel: str = dspy.InputField(desc="Selected biomarker panel")
        qc_summary: str = dspy.InputField(desc="Quality control summary")
        report: str = dspy.OutputField(desc="Regulatory-compliant report text")
        risk_assessment: str = dspy.OutputField(desc="Risk assessment for the biomarker panel")
        recommendations: str = dspy.OutputField(desc="Regulatory recommendations")

    class RegulatoryReportModule(dspy.Module):
        """Single-step DSPy module for regulatory report generation."""

        def __init__(self):
            super().__init__()
            self.generate = dspy.ChainOfThought(RegulatoryReportSignature)

        def forward(self, analysis_results, biomarker_panel, qc_summary):
            return self.generate(
                analysis_results=analysis_results,
                biomarker_panel=biomarker_panel,
                qc_summary=qc_summary,
            )
