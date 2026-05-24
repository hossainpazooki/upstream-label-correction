"""Tests for SLM explainer classes (mock-based)."""

from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from training.explainer import (
    LocalGenomicsExplainer,
    VertexGenomicsExplainer,
    get_explainer,
)


class TestLocalGenomicsExplainer:
    @pytest.mark.asyncio
    async def test_classify_gene_returns_dict(self):
        explainer = LocalGenomicsExplainer(adapter_path="/fake/path")

        expected = {
            "gene": "PTPRC",
            "pathway": "immune_infiltration",
            "mechanism": "Leukocyte surface marker",
            "confidence": 0.95,
            "msi_relevant": True,
        }

        mock_tokenizer = MagicMock()
        mock_tokenizer.pad_token = "<pad>"
        mock_tokenizer.pad_token_id = 0
        mock_tokenizer.decode.return_value = json.dumps(expected)

        mock_inputs = MagicMock()
        mock_inputs.__getitem__ = lambda s, k: MagicMock(shape=[1, 5])
        mock_tokenizer.return_value = mock_inputs

        mock_model = MagicMock()
        mock_model.device = "cpu"
        mock_model.generate.return_value = [[1, 2, 3, 4, 5, 6, 7, 8]]

        explainer._model = mock_model
        explainer._tokenizer = mock_tokenizer

        # Mock torch at module level
        mock_torch = MagicMock()
        mock_torch.no_grad.return_value.__enter__ = MagicMock()
        mock_torch.no_grad.return_value.__exit__ = MagicMock()

        with patch.dict(sys.modules, {"torch": mock_torch}):
            result = await explainer.classify_gene("PTPRC", "msi")

        assert isinstance(result, dict)
        assert result["gene"] == "PTPRC"
        assert result["msi_relevant"] is True

    @pytest.mark.asyncio
    async def test_classify_gene_handles_invalid_json(self):
        explainer = LocalGenomicsExplainer(adapter_path="/fake/path")

        mock_tokenizer = MagicMock()
        mock_tokenizer.pad_token = "<pad>"
        mock_tokenizer.pad_token_id = 0
        mock_tokenizer.decode.return_value = "not valid json at all"

        mock_inputs = MagicMock()
        mock_inputs.__getitem__ = lambda s, k: MagicMock(shape=[1, 5])
        mock_tokenizer.return_value = mock_inputs

        mock_model = MagicMock()
        mock_model.device = "cpu"
        mock_model.generate.return_value = [[1, 2, 3, 4, 5, 6, 7, 8]]

        explainer._model = mock_model
        explainer._tokenizer = mock_tokenizer

        mock_torch = MagicMock()
        mock_torch.no_grad.return_value.__enter__ = MagicMock()
        mock_torch.no_grad.return_value.__exit__ = MagicMock()

        with patch.dict(sys.modules, {"torch": mock_torch}):
            result = await explainer.classify_gene("ACTB", "msi")

        assert result["gene"] == "ACTB"
        assert result["pathway"] == "parse_error"
        assert result["msi_relevant"] is False


class TestVertexGenomicsExplainer:
    @pytest.mark.asyncio
    async def test_classify_gene_returns_dict(self):
        explainer = VertexGenomicsExplainer(endpoint_name="projects/test/endpoints/123")

        mock_response = MagicMock()
        mock_response.predictions = [
            json.dumps(
                {
                    "gene": "GBP1",
                    "pathway": "interferon_response",
                    "mechanism": "Guanylate-binding protein",
                    "confidence": 0.90,
                    "msi_relevant": True,
                }
            )
        ]

        mock_endpoint = MagicMock()
        mock_endpoint.predict.return_value = mock_response
        explainer._endpoint = mock_endpoint

        result = await explainer.classify_gene("GBP1", "msi")

        assert result["gene"] == "GBP1"
        assert result["pathway"] == "interferon_response"
        assert result["msi_relevant"] is True

    @pytest.mark.asyncio
    async def test_classify_gene_handles_invalid_response(self):
        explainer = VertexGenomicsExplainer(endpoint_name="projects/test/endpoints/123")

        mock_response = MagicMock()
        mock_response.predictions = ["not valid json"]

        mock_endpoint = MagicMock()
        mock_endpoint.predict.return_value = mock_response
        explainer._endpoint = mock_endpoint

        result = await explainer.classify_gene("UNKNOWN", "msi")

        assert result["gene"] == "UNKNOWN"
        assert result["pathway"] == "parse_error"

    @pytest.mark.asyncio
    async def test_classify_gene_dict_response(self):
        explainer = VertexGenomicsExplainer(endpoint_name="projects/test/endpoints/123")

        mock_response = MagicMock()
        mock_response.predictions = [
            {
                "gene": "TAP1",
                "pathway": "antigen_presentation",
                "mechanism": "Transporter",
                "confidence": 0.91,
                "msi_relevant": True,
            }
        ]

        mock_endpoint = MagicMock()
        mock_endpoint.predict.return_value = mock_response
        explainer._endpoint = mock_endpoint

        result = await explainer.classify_gene("TAP1", "msi")

        assert result["gene"] == "TAP1"


class TestGetExplainer:
    def test_returns_vertex_when_endpoint_set(self):
        config = MagicMock()
        config.slm_endpoint_name = "projects/test/endpoints/123"
        config.slm_adapter_path = None

        explainer = get_explainer(config)
        assert isinstance(explainer, VertexGenomicsExplainer)

    def test_returns_local_when_adapter_set(self):
        config = MagicMock()
        config.slm_endpoint_name = None
        config.slm_adapter_path = "/path/to/adapter"

        explainer = get_explainer(config)
        assert isinstance(explainer, LocalGenomicsExplainer)

    def test_raises_when_no_config(self):
        config = MagicMock()
        config.slm_endpoint_name = None
        config.slm_adapter_path = None

        with pytest.raises(ValueError, match="No SLM configuration found"):
            get_explainer(config)
