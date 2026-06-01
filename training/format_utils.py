"""Formatting and splitting utilities for SLM training data."""

from __future__ import annotations

import random


def format_alpaca(instruction: str, input_text: str, output_json: str) -> str:
    """Format as Alpaca-style instruction prompt.

    Returns a string in the standard Alpaca template used for instruction tuning.
    """
    return f"### Instruction:\n{instruction}\n\n### Input:\n{input_text}\n\n### Response:\n{output_json}"


def split_dataset(
    examples: list[dict],
    train_frac: float = 0.8,
    val_frac: float = 0.1,
    seed: int = 42,
) -> tuple[list, list, list]:
    """Split examples into train/val/test sets.

    Parameters
    ----------
    examples : list[dict]
        Full list of examples to split.
    train_frac : float
        Fraction for training set (default 0.8).
    val_frac : float
        Fraction for validation set (default 0.1).
    seed : int
        Random seed for reproducibility.

    Returns
    -------
    tuple[list, list, list]
        (train, val, test) splits.
    """
    # Deterministic seeded data-split shuffle for reproducibility, not crypto.
    rng = random.Random(seed)  # noqa: S311
    shuffled = list(examples)
    rng.shuffle(shuffled)

    n = len(shuffled)
    train_end = int(n * train_frac)
    val_end = train_end + int(n * val_frac)

    return shuffled[:train_end], shuffled[train_end:val_end], shuffled[val_end:]
