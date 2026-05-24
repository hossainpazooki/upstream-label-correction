"""Intent status enum and shared schema definitions."""

from __future__ import annotations

from enum import StrEnum


class IntentStatus(StrEnum):
    """Lifecycle states for an intent.

    State machine::

        DECLARED -> RESOLVING -> ACTIVE -> VERIFYING -> ACHIEVED
                      |            |          |
                      v            v          v
                   BLOCKED      FAILED     FAILED
                      |
                      v
                   RESOLVING (retry)

        Any non-terminal -> CANCELLED
    """

    DECLARED = "declared"
    RESOLVING = "resolving"
    BLOCKED = "blocked"
    ACTIVE = "active"
    VERIFYING = "verifying"
    ACHIEVED = "achieved"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Terminal states — no further transitions allowed.
TERMINAL_STATES: frozenset[IntentStatus] = frozenset(
    {
        IntentStatus.ACHIEVED,
        IntentStatus.FAILED,
        IntentStatus.CANCELLED,
    }
)

# Valid state transitions: from_state -> set of allowed to_states.
VALID_TRANSITIONS: dict[IntentStatus, frozenset[IntentStatus]] = {
    IntentStatus.DECLARED: frozenset({IntentStatus.RESOLVING, IntentStatus.CANCELLED}),
    IntentStatus.RESOLVING: frozenset(
        {IntentStatus.ACTIVE, IntentStatus.BLOCKED, IntentStatus.FAILED, IntentStatus.CANCELLED}
    ),
    IntentStatus.BLOCKED: frozenset({IntentStatus.RESOLVING, IntentStatus.CANCELLED}),
    IntentStatus.ACTIVE: frozenset({IntentStatus.VERIFYING, IntentStatus.FAILED, IntentStatus.CANCELLED}),
    IntentStatus.VERIFYING: frozenset({IntentStatus.ACHIEVED, IntentStatus.FAILED, IntentStatus.CANCELLED}),
}
