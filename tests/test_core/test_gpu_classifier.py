"""Tests for GPU classifier and get_classifier factory."""

from __future__ import annotations

import pytest

from core.classifier import EnsembleMismatchClassifier, get_classifier

try:
    import cuml  # noqa: F401

    _CUML_AVAILABLE = True
except ImportError:
    _CUML_AVAILABLE = False


class TestGetClassifierFactory:
    def test_returns_cpu_by_default(self):
        clf = get_classifier()
        assert isinstance(clf, EnsembleMismatchClassifier)

    def test_returns_cpu_when_gpu_not_preferred(self):
        clf = get_classifier(prefer_gpu=False)
        assert isinstance(clf, EnsembleMismatchClassifier)

    def test_returns_cpu_when_cuml_unavailable(self):
        # When cuML is not installed, prefer_gpu=True should fall back to CPU
        if _CUML_AVAILABLE:
            pytest.skip("cuML is available, cannot test fallback")
        clf = get_classifier(prefer_gpu=True)
        assert isinstance(clf, EnsembleMismatchClassifier)

    def test_respects_random_state(self):
        clf = get_classifier(random_state=123)
        assert clf.random_state == 123


@pytest.mark.skipif(not _CUML_AVAILABLE, reason="cuML not installed")
class TestGPUEnsembleMismatchClassifier:
    def test_import(self):
        from core.gpu_classifier import GPUEnsembleMismatchClassifier

        clf = GPUEnsembleMismatchClassifier(random_state=42)
        assert clf.random_state == 42

    def test_factory_returns_gpu(self):
        clf = get_classifier(prefer_gpu=True)
        from core.gpu_classifier import GPUEnsembleMismatchClassifier

        assert isinstance(clf, GPUEnsembleMismatchClassifier)
