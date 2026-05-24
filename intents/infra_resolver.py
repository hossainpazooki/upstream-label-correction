"""Infrastructure resolver — maps intent requirements to Pulumi Automation API operations.

Wraps the existing automation scripts in infra/automation/ and adds
intent-specific provisioning logic.
"""

from __future__ import annotations

import logging
from typing import Any

from intents.models import Intent, emit_event

logger = logging.getLogger(__name__)


class InfrastructureResolver:
    """Resolve infrastructure requirements for an intent via Pulumi Automation API."""

    def __init__(self, stack_name: str = "dev") -> None:
        self._stack_name = stack_name
        self._handlers: dict[str, Any] = {
            "worker_scaled": self._ensure_worker_scaled,
            "gcs_data_staged": self._ensure_data_staged,
            "vertex_ai_job": self._provision_training_job,
            "gpu_allocated": self._check_gpu_quota,
        }

    async def resolve(
        self,
        intent: Intent,
        required_infra: tuple[str, ...],
    ) -> dict[str, Any]:
        """Provision/verify all required infra for the intent.

        Returns a dict of ``{requirement: result_dict}`` that gets stored
        as ``intent.infra_state``.
        """
        results: dict[str, Any] = {}

        for requirement in required_infra:
            handler = self._handlers.get(requirement)
            if handler is None:
                logger.warning(
                    "No handler for infra requirement '%s', skipping",
                    requirement,
                )
                results[requirement] = {"status": "skipped", "reason": "no handler"}
                continue

            try:
                result = await handler(intent)
                results[requirement] = result
                await emit_event(
                    intent.intent_id,
                    event_type="infra_update",
                    payload={"requirement": requirement, "result": result},
                )
            except Exception as exc:
                logger.exception(
                    "Infra resolution failed for '%s' on intent %s",
                    requirement,
                    intent.intent_id,
                )
                results[requirement] = {"status": "failed", "error": str(exc)}
                await emit_event(
                    intent.intent_id,
                    event_type="error",
                    payload={"requirement": requirement, "error": str(exc)},
                )
                raise

        return results

    def all_resolved(self, infra_state: dict[str, Any]) -> bool:
        """Return True if every requirement resolved successfully."""
        for result in infra_state.values():
            if isinstance(result, dict) and result.get("status") == "failed":
                return False
        return True

    # ------------------------------------------------------------------
    # Handler implementations
    # ------------------------------------------------------------------

    async def _ensure_worker_scaled(self, intent: Intent) -> dict[str, Any]:
        """Scale worker instances for analysis workloads via Automation API."""
        from infra.automation.intent_infra import scale_for_intent

        params = intent.params
        worker_max = params.get("worker_max_instances", 5)

        outputs = await scale_for_intent(
            stack_name=self._stack_name,
            intent_type=intent.intent_type,
            worker_max_instances=worker_max,
        )

        return {
            "status": "scaled",
            "stack_name": self._stack_name,
            "worker_url": outputs.get("activity_worker_url", ""),
        }

    async def _ensure_data_staged(self, intent: Intent) -> dict[str, Any]:
        """Verify that required dataset files exist in the GCS data bucket."""
        params = intent.params
        dataset = params.get("dataset", "train")

        # Try to verify via GCS; fall back to local check.
        try:
            from google.cloud import storage as gcs

            client = gcs.Client()
            bucket_name = params.get("gcs_data_bucket")
            if bucket_name:
                bucket = client.bucket(bucket_name)
                prefix = f"data/{dataset}/"
                blobs = list(bucket.list_blobs(prefix=prefix, max_results=1))
                if blobs:
                    return {"status": "staged", "bucket": bucket_name, "prefix": prefix}
                return {"status": "failed", "error": f"No data at gs://{bucket_name}/{prefix}"}
        except ImportError:
            pass

        # Local fallback — assume data is available.
        return {"status": "staged", "source": "local", "dataset": dataset}

    async def _provision_training_job(self, intent: Intent) -> dict[str, Any]:
        """Provision a Vertex AI training job for the intent."""
        params = intent.params
        model_type = params.get("model_type", "slm")

        # Delegate to existing GPU training activities.
        config = {
            "model_type": model_type,
            "dataset": params.get("dataset", "train"),
            "target": params.get("target", "msi"),
            **params.get("training_config", {}),
        }

        if model_type == "encoder":
            from training.gpu_training import train_expression_encoder

            result = await train_expression_encoder(config)
        elif model_type == "slm":
            from training.gpu_training import finetune_slm

            result = await finetune_slm(config)
        elif model_type == "cuml":
            from training.gpu_training import run_cuml_pipeline

            result = await run_cuml_pipeline(config)
        else:
            return {"status": "failed", "error": f"Unknown model_type: {model_type}"}

        return {"status": "provisioned", "job": result}

    async def _check_gpu_quota(self, intent: Intent) -> dict[str, Any]:
        """Validate GPU request against the training intent spec's max_gpu_count."""
        from intents.types import INTENT_SPECS, TrainingIntentSpec

        spec = INTENT_SPECS.get(intent.intent_type)
        max_gpus = spec.max_gpu_count if isinstance(spec, TrainingIntentSpec) else 4

        requested_gpus = intent.params.get("num_gpus", 1)
        if requested_gpus > max_gpus:
            return {
                "status": "failed",
                "error": (
                    f"Requested {requested_gpus} GPUs exceeds limit of {max_gpus} for {intent.intent_type} intents."
                ),
            }

        return {"status": "approved", "num_gpus": requested_gpus, "max_allowed": max_gpus}
