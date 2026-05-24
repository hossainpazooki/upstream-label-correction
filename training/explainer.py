"""SLM-based genomics explainer with local and Vertex AI backends."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class LocalGenomicsExplainer:
    """Loads PEFT adapter model locally with 4-bit quantization."""

    def __init__(self, adapter_path: str) -> None:
        self.adapter_path = adapter_path
        self._model = None
        self._tokenizer = None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return

        try:
            from peft import PeftModel
            from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        except ImportError as exc:
            raise ImportError("Local explainer requires: pip install peft transformers bitsandbytes torch") from exc

        # Load adapter config to find base model
        import os

        adapter_config_path = os.path.join(self.adapter_path, "adapter_config.json")
        if os.path.exists(adapter_config_path):
            with open(adapter_config_path) as f:
                adapter_cfg = json.load(f)
            base_model_name = adapter_cfg.get("base_model_name_or_path", "BioMistral/BioMistral-7B")
        else:
            base_model_name = "BioMistral/BioMistral-7B"

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype="bfloat16",
            bnb_4bit_use_double_quant=True,
        )

        base_model = AutoModelForCausalLM.from_pretrained(
            base_model_name,
            quantization_config=bnb_config,
            device_map="auto",
            trust_remote_code=True,
        )

        self._model = PeftModel.from_pretrained(base_model, self.adapter_path)
        self._tokenizer = AutoTokenizer.from_pretrained(self.adapter_path, trust_remote_code=True)
        if self._tokenizer.pad_token is None:
            self._tokenizer.pad_token = self._tokenizer.eos_token

        logger.info("Loaded local SLM from %s", self.adapter_path)

    async def classify_gene(self, gene: str, target: str) -> dict:
        """Classify a gene using the local SLM adapter."""
        self._ensure_loaded()

        prompt = (
            f"### Instruction:\n"
            f"Classify the following gene's relevance to microsatellite instability (MSI) "
            f"in colorectal cancer. Return a JSON object with fields: gene, pathway, "
            f"mechanism, confidence, and msi_relevant (boolean).\n\n"
            f"### Input:\nGene: {gene}\nContext: {target}_classification\n\n"
            f"### Response:\n"
        )

        import torch

        inputs = self._tokenizer(prompt, return_tensors="pt").to(self._model.device)
        with torch.no_grad():
            outputs = self._model.generate(
                **inputs,
                max_new_tokens=256,
                temperature=0.1,
                do_sample=True,
                pad_token_id=self._tokenizer.pad_token_id,
            )

        response_text = self._tokenizer.decode(
            outputs[0][inputs["input_ids"].shape[1] :],
            skip_special_tokens=True,
        ).strip()

        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            return {
                "gene": gene,
                "pathway": "parse_error",
                "mechanism": response_text[:200],
                "confidence": 0.0,
                "msi_relevant": False,
                "raw_output": response_text,
            }


class VertexGenomicsExplainer:
    """Uses Vertex AI Endpoint for inference."""

    def __init__(self, endpoint_name: str) -> None:
        self.endpoint_name = endpoint_name
        self._endpoint = None

    def _ensure_endpoint(self) -> None:
        if self._endpoint is not None:
            return

        from google.cloud import aiplatform

        self._endpoint = aiplatform.Endpoint(self.endpoint_name)
        logger.info("Connected to Vertex AI endpoint: %s", self.endpoint_name)

    async def classify_gene(self, gene: str, target: str) -> dict:
        """Classify a gene using the Vertex AI endpoint."""
        self._ensure_endpoint()

        prompt = (
            f"Classify the following gene's relevance to microsatellite instability (MSI) "
            f"in colorectal cancer. Return a JSON object with fields: gene, pathway, "
            f"mechanism, confidence, and msi_relevant (boolean).\n"
            f"Gene: {gene}\nContext: {target}_classification"
        )

        response = self._endpoint.predict(instances=[{"prompt": prompt}])
        prediction = response.predictions[0]

        if isinstance(prediction, str):
            try:
                return json.loads(prediction)
            except json.JSONDecodeError:
                return {
                    "gene": gene,
                    "pathway": "parse_error",
                    "mechanism": prediction[:200],
                    "confidence": 0.0,
                    "msi_relevant": False,
                }
        return prediction


def get_explainer(config: Any = None) -> LocalGenomicsExplainer | VertexGenomicsExplainer:
    """Factory based on config settings.

    Uses Vertex AI endpoint if slm_endpoint_name is set, otherwise local adapter.
    """
    if config is None:
        from core.config import get_settings

        config = get_settings()

    endpoint_name = getattr(config, "slm_endpoint_name", None)
    adapter_path = getattr(config, "slm_adapter_path", None)

    if endpoint_name:
        return VertexGenomicsExplainer(endpoint_name=endpoint_name)

    if adapter_path:
        return LocalGenomicsExplainer(adapter_path=adapter_path)

    raise ValueError("No SLM configuration found. Set either slm_endpoint_name or slm_adapter_path.")
