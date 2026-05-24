"""Intent controller — implements the observe-decide-act-verify loop.

Not a long-running process.  Called per-intent via process() which is
idempotent — safe to call repeatedly, advancing the intent through
whatever state transition is currently possible.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from intents.models import Intent, emit_event, get_intent_record, update_intent
from intents.schemas import VALID_TRANSITIONS, IntentStatus
from intents.types import INTENT_SPECS, TrainingIntentSpec

if TYPE_CHECKING:
    from intents.assurance import AssuranceLoop
    from intents.infra_resolver import InfrastructureResolver

logger = logging.getLogger(__name__)


class IntentController:
    """Orchestrate the observe-decide-act-verify loop for a single intent."""

    def __init__(
        self,
        resolver: InfrastructureResolver,
        assurance: AssuranceLoop,
    ) -> None:
        self._resolver = resolver
        self._assurance = assurance

    async def process(self, intent_id: str) -> dict | None:
        """Drive the intent through its lifecycle.  Idempotent.

        Returns the intent dict after processing, or None if not found.
        """
        intent = await self._load(intent_id)
        if intent is None:
            logger.warning("Intent %s not found", intent_id)
            return None

        status = intent.status

        # DECLARED → RESOLVING: observe + decide
        if status == IntentStatus.DECLARED:
            await self._begin_resolution(intent)
            # Reload after transition.
            intent = await self._load(intent_id)
            status = intent.status

        # RESOLVING → ACTIVE: provision infra + trigger workflows
        if status == IntentStatus.RESOLVING:
            await self._resolve_and_activate(intent)
            intent = await self._load(intent_id)
            status = intent.status

        # ACTIVE → VERIFYING: check child workflows
        if status == IntentStatus.ACTIVE:
            await self._check_workflows(intent)
            intent = await self._load(intent_id)
            status = intent.status

        # VERIFYING → ACHIEVED/FAILED: run assurance loop
        if status == IntentStatus.VERIFYING:
            await self._verify(intent)
            intent = await self._load(intent_id)

        return intent

    async def cancel(self, intent_id: str) -> dict | None:
        """Cancel an intent.  Only works for non-terminal states."""
        intent = await self._load(intent_id)
        if intent is None:
            return None
        if intent.status in ("achieved", "failed", "cancelled"):
            return intent
        await self._transition(intent, IntentStatus.CANCELLED)
        return await self._load(intent_id)

    # ------------------------------------------------------------------
    # Lifecycle phases
    # ------------------------------------------------------------------

    async def _begin_resolution(self, intent: dict) -> None:
        """DECLARED → RESOLVING: validate params and begin infra resolution."""
        intent_type = intent["intent_type"]
        spec = INTENT_SPECS.get(intent_type)
        if spec is None:
            await update_intent(
                intent["intent_id"],
                status=IntentStatus.FAILED,
                error=f"Unknown intent type: {intent_type}",
            )
            return

        await self._transition(intent, IntentStatus.RESOLVING)

    async def _resolve_and_activate(self, intent: dict) -> None:
        """RESOLVING → ACTIVE: provision infra, then trigger child workflows."""
        spec = INTENT_SPECS[intent["intent_type"]]

        # Resolve infrastructure requirements.
        try:
            infra_state = await self._resolver.resolve(
                Intent(**self._to_model_kwargs(intent)),
                spec.required_infra,
            )
        except Exception as exc:
            logger.exception("Infra resolution failed for %s", intent["intent_id"])
            await update_intent(
                intent["intent_id"],
                status=IntentStatus.BLOCKED,
                error=str(exc),
            )
            return

        if not self._resolver.all_resolved(infra_state):
            await update_intent(
                intent["intent_id"],
                status=IntentStatus.BLOCKED,
                infra_state=infra_state,
                error="One or more infra requirements not met",
            )
            return

        # Infra ready — trigger child workflows.
        workflow_ids = await self._trigger_workflows(intent, spec)

        await update_intent(
            intent["intent_id"],
            status=IntentStatus.ACTIVE,
            infra_state=infra_state,
            workflow_ids=workflow_ids,
        )

    async def _check_workflows(self, intent: dict) -> None:
        """ACTIVE → VERIFYING: poll child workflows for completion."""
        workflow_ids = intent.get("workflow_ids", [])
        if not workflow_ids:
            # No workflows to check — go straight to verifying.
            await self._transition(intent, IntentStatus.VERIFYING)
            return

        all_done = True
        any_failed = False

        for wf_id in workflow_ids:
            progress = await self._get_workflow_progress(wf_id)
            if progress is None:
                continue
            wf_status = progress.get("status", "pending")
            if wf_status in ("pending", "running"):
                all_done = False
            elif wf_status == "failed":
                any_failed = True

        if any_failed:
            await update_intent(
                intent["intent_id"],
                status=IntentStatus.FAILED,
                error="One or more child workflows failed",
            )
            return

        if all_done:
            await self._transition(intent, IntentStatus.VERIFYING)

    async def _verify(self, intent: dict) -> None:
        """VERIFYING → ACHIEVED/FAILED: run eval assurance loop."""
        spec = INTENT_SPECS[intent["intent_type"]]

        if not spec.eval_criteria:
            # No eval criteria — intent is achieved by completion.
            await self._transition(intent, IntentStatus.ACHIEVED)
            # For training intents, chain to model deployment.
            if isinstance(spec, TrainingIntentSpec) and spec.triggers_deploy:
                await self._trigger_deploy(intent)
            return

        intent_model = Intent(**self._to_model_kwargs(intent))
        eval_results = await self._assurance.evaluate(intent_model, spec.eval_criteria)

        # Down-convert at the persistence boundary -- the on-disk shape that
        # downstream readers (e.g. AssuranceLoop._extract_genes) expect.
        persisted = {
            name: {
                "score": r.score,
                "threshold": r.threshold,
                "passed": r.passed,
                "details": r.details,
            }
            for name, r in eval_results.items()
        }
        await update_intent(
            intent["intent_id"],
            eval_results=persisted,
        )

        if self._assurance.all_passed(eval_results):
            await self._transition(intent, IntentStatus.ACHIEVED)
        else:
            failed_evals = [name for name, r in eval_results.items() if not r.passed]
            await update_intent(
                intent["intent_id"],
                status=IntentStatus.FAILED,
                error=f"Eval criteria not met: {', '.join(failed_evals)}",
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _load(self, intent_id: str) -> dict | None:
        """Load intent from the database."""
        return await get_intent_record(intent_id)

    async def _transition(self, intent: dict, to_status: IntentStatus) -> None:
        """Execute a state transition with validation and event emission."""
        from_status = intent.get("status", "declared")
        valid = VALID_TRANSITIONS.get(IntentStatus(from_status), frozenset())
        if to_status not in valid and to_status != IntentStatus.CANCELLED:
            logger.error(
                "Invalid transition %s → %s for intent %s",
                from_status,
                to_status,
                intent["intent_id"],
            )
            return

        await update_intent(intent["intent_id"], status=to_status)

    async def _get_workflow_progress(self, workflow_id: str) -> dict | None:
        """Get workflow progress via the intent-controller HTTP API."""
        try:
            import httpx

            async with httpx.AsyncClient(base_url="http://localhost:8090") as client:
                resp = await client.get(f"/api/v1/workflows/{workflow_id}")
                if resp.status_code == 200:
                    return resp.json()
                return None
        except Exception:
            logger.warning("Failed to get progress for workflow %s", workflow_id)
            return None

    async def _trigger_workflows(self, intent: dict, spec) -> list[str]:
        """Start child workflows based on intent type and return their IDs."""
        import httpx

        params = intent.get("params", {})
        workflow_ids: list[str] = []
        intent_type = intent["intent_type"]

        if intent_type == "training":
            # Training jobs are provisioned by the infra resolver.
            infra_state = intent.get("infra_state", {})
            job_info = infra_state.get("vertex_ai_job", {})
            job_name = job_info.get("job", {}).get("job_name", f"train-{uuid.uuid4().hex[:8]}")
            workflow_ids.append(job_name)

            await emit_event(
                intent["intent_id"],
                event_type="workflow_started",
                payload={"workflow_id": job_name, "job_info": job_info},
            )
        else:
            # Delegate to Go intent-controller for analysis/validation workflows.
            try:
                async with httpx.AsyncClient(base_url="http://localhost:8090") as client:
                    resp = await client.post(
                        "/api/v1/workflows",
                        json={
                            "intent_id": intent["intent_id"],
                            "intent_type": intent_type,
                            "params": params,
                        },
                    )
                    result = resp.json()
                    wf_id = result.get("workflow_id", f"wf-{uuid.uuid4().hex[:12]}")
                    workflow_ids.append(wf_id)
            except Exception:
                logger.exception("Failed to trigger workflow via intent-controller")
                wf_id = f"wf-{uuid.uuid4().hex[:12]}"
                workflow_ids.append(wf_id)

            await emit_event(
                intent["intent_id"],
                event_type="workflow_started",
                payload={"workflow_id": wf_id, "type": intent_type},
            )

        return workflow_ids

    async def _trigger_deploy(self, intent: dict) -> None:
        """Chain training intent success to model deployment."""
        try:
            from infra.automation.deploy_on_model_retrain import deploy_model_update

            params = intent.get("params", {})
            image_tag = params.get("image_tag", "latest")
            stack_name = intent.get("infra_state", {}).get("stack_name", "dev")

            await deploy_model_update(
                stack_name=stack_name,
                image_tag=image_tag,
            )

            await emit_event(
                intent["intent_id"],
                event_type="infra_update",
                payload={"action": "model_deployed", "image_tag": image_tag},
            )
        except Exception as exc:
            logger.exception("Post-training deploy failed for %s", intent["intent_id"])
            await emit_event(
                intent["intent_id"],
                event_type="error",
                payload={"action": "deploy_failed", "error": str(exc)},
            )

    @staticmethod
    def _to_model_kwargs(intent_dict: dict) -> dict:
        """Convert an intent dict (from get_intent_record) to Intent constructor kwargs."""
        from datetime import datetime

        def _parse_dt(v):
            if v is None:
                return None
            if isinstance(v, datetime):
                return v
            return datetime.fromisoformat(v)

        return {
            "intent_id": intent_dict["intent_id"],
            "intent_type": intent_dict["intent_type"],
            "status": intent_dict["status"],
            "params": intent_dict.get("params", {}),
            "infra_state": intent_dict.get("infra_state", {}),
            "workflow_ids": intent_dict.get("workflow_ids", []),
            "eval_results": intent_dict.get("eval_results", {}),
            "created_at": _parse_dt(intent_dict.get("created_at")),
            "error": intent_dict.get("error"),
            "requested_by": intent_dict.get("requested_by", "agent"),
        }
