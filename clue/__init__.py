"""CLUE — Closed-Loop Upstream Error-correction.

The orchestration layer that closes the loop: generate → measure → improve →
regenerate. See :mod:`clue.loop`.
"""

from clue.loop import CLUELoop, LoopResult, RoundResult, tune_decision_threshold

__all__ = ["CLUELoop", "LoopResult", "RoundResult", "tune_decision_threshold"]
