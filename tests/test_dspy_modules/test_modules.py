"""Tests for DSPy module instantiation and forward signatures."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_dspy():
    """Create a mock dspy module with necessary classes."""
    mock = MagicMock()

    class MockSignature:
        pass

    class MockModule:
        def __init__(self):
            pass

    mock.Signature = MockSignature
    mock.Module = MockModule
    mock.InputField = MagicMock(return_value="input")
    mock.OutputField = MagicMock(return_value="output")
    mock.ChainOfThought = MagicMock(return_value=MagicMock())
    return mock


class TestBiomarkerDiscoveryModule:
    def test_instantiation(self, mock_dspy):
        with patch.dict("sys.modules", {"dspy": mock_dspy}):
            # Re-import to pick up mock
            import importlib

            import dspy_modules.biomarker_discovery as mod

            importlib.reload(mod)
            if hasattr(mod, "BiomarkerDiscoveryModule"):
                module = mod.BiomarkerDiscoveryModule()
                assert hasattr(module, "assess_quality")
                assert hasattr(module, "evaluate_imputation")
                assert hasattr(module, "interpret_features")
                assert hasattr(module, "synthesize_report")

    def test_forward_signature(self, mock_dspy):
        with patch.dict("sys.modules", {"dspy": mock_dspy}):
            import importlib

            import dspy_modules.biomarker_discovery as mod

            importlib.reload(mod)
            if hasattr(mod, "BiomarkerDiscoveryModule"):
                module = mod.BiomarkerDiscoveryModule()
                # Mock sub-module returns
                mock_result = MagicMock()
                mock_result.assessment = "good"
                mock_result.evaluation = "adequate"
                mock_result.interpretations = "gene X is relevant"
                module.assess_quality = MagicMock(return_value=mock_result)
                module.evaluate_imputation = MagicMock(return_value=mock_result)
                module.interpret_features = MagicMock(return_value=mock_result)
                module.synthesize_report = MagicMock(return_value=mock_result)

                result = module.forward(
                    dataset_summary="100 samples",
                    imputation_stats="5% missing",
                    feature_list="BRCA1, TP53",
                    target="msi",
                )
                assert result is not None
                module.assess_quality.assert_called_once()
                module.synthesize_report.assert_called_once()


class TestSampleQCModule:
    def test_instantiation(self, mock_dspy):
        with patch.dict("sys.modules", {"dspy": mock_dspy}):
            import importlib

            import dspy_modules.sample_qc as mod

            importlib.reload(mod)
            if hasattr(mod, "SampleQCModule"):
                module = mod.SampleQCModule()
                assert hasattr(module, "analyze_classification")
                assert hasattr(module, "analyze_distance")
                assert hasattr(module, "cross_validate")


class TestFeatureInterpretModule:
    def test_instantiation(self, mock_dspy):
        with patch.dict("sys.modules", {"dspy": mock_dspy}):
            import importlib

            import dspy_modules.feature_interpret as mod

            importlib.reload(mod)
            if hasattr(mod, "FeatureInterpretModule"):
                module = mod.FeatureInterpretModule()
                assert hasattr(module, "interpret")


class TestRegulatoryReportModule:
    def test_instantiation(self, mock_dspy):
        with patch.dict("sys.modules", {"dspy": mock_dspy}):
            import importlib

            import dspy_modules.regulatory_report as mod

            importlib.reload(mod)
            if hasattr(mod, "RegulatoryReportModule"):
                module = mod.RegulatoryReportModule()
                assert hasattr(module, "generate")
