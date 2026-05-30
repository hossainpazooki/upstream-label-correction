
"""Intent type specifications — frozen configuration for each intent type.

Follows the @dataclass(frozen=True) pattern from infra/config.py.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnalysisIntentSpec:
    """Spec for biomarker discovery / sample QC analysis intents.

    Maps to the 4-stage COSMO pipeline in core/pipeline.py.
    """

    intent_type: str = "analysis"
    required_infra: tuple[str, ...] = ("worker_scaled", "gcs_data_staged")
    eval_criteria: tuple[tuple[str, float], ...] = (
        ("biological_validity", 0.60),
        ("reproducibility", 0.85),
    )
    # Must pass ValidationIntent before proceeding past this pipeline stage.
    validation_gate_stage: int = 2


@dataclass(frozen=True)
class TrainingIntentSpec:
    """Spec for model fine-tuning intents (BioMistral, expression encoder).

    Maps to scripts/vertex_train_entrypoint.py and training/.
    On success, chains to deploy_on_model_retrain.deploy_model_update().
    """

    intent_type: str = "training"
    required_infra: tuple[str, ...] = ("vertex_ai_job", "gpu_allocated")
    # Training success = job completion; no eval criteria.
    eval_criteria: tuple[tuple[str, float], ...] = ()
    max_gpu_count: int = 4
    triggers_deploy: bool = True


@dataclass(frozen=True)
class ValidationIntentSpec:
    """Spec for cross-omics concordance validation intents.

    Maps to Stage 4 dual-path validation.  Acts as a gate for
    AnalysisIntent — no analysis proceeds past stage 2 without
    a passing ValidationIntent.  Its eval gate covers citation
    hallucination and adversarial robustness of the SLM.
    """

    intent_type: str = "validation"
    required_infra: tuple[str, ...] = ()
    eval_criteria: tuple[tuple[str, float], ...] = (
        ("hallucination_detection", 0.90),
        ("adversarial_robustness", 1.0),
    )


INTENT_SPECS: dict[str, AnalysisIntentSpec | TrainingIntentSpec | ValidationIntentSpec] = {
    "analysis": AnalysisIntentSpec(),
    "training": TrainingIntentSpec(),
    "validation": ValidationIntentSpec(),
}
