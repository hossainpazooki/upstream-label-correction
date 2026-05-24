"""Convenience functions for intent lifecycle operations.

Thin wrappers around models.py persistence and controller instantiation.
"""

from __future__ import annotations

import uuid
from typing import Any

from intents.models import Intent, get_intent_record


async def create_intent(
    intent_type: str,
    params: dict[str, Any] | None = None,
    requested_by: str = "agent",
) -> Intent:
    """Create a new intent record in the database and return it."""
    from intents.types import INTENT_SPECS

    if intent_type not in INTENT_SPECS:
        raise ValueError(f"Unknown intent_type '{intent_type}'. Valid: {', '.join(INTENT_SPECS)}")

    intent_id = f"{intent_type}-{uuid.uuid4().hex[:12]}"

    from core.database import get_session

    async with get_session() as session:
        intent = Intent(
            intent_id=intent_id,
            intent_type=intent_type,
            params=params or {},
            requested_by=requested_by,
        )
        session.add(intent)
        await session.commit()
        await session.refresh(intent)
        return intent


async def get_intent(intent_id: str) -> dict | None:
    """Load intent as a dict.  Delegates to models.get_intent_record."""
    return await get_intent_record(intent_id)


def get_controller():
    """Build an IntentController with default resolver and assurance loop."""
    from intents.assurance import AssuranceLoop
    from intents.controller import IntentController
    from intents.infra_resolver import InfrastructureResolver

    return IntentController(
        resolver=InfrastructureResolver(),
        assurance=AssuranceLoop(),
    )
