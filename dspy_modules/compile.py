"""DSPy module compilation pipeline."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.storage import StorageBackend

try:
    import dspy

    _DSPY_AVAILABLE = True
except ImportError:
    dspy = None
    _DSPY_AVAILABLE = False

logger = logging.getLogger(__name__)

_DEFAULT_TRAINING_PATH = Path(__file__).parent.parent / "data" / "dspy_training_examples.json"


def load_training_examples(storage: StorageBackend | None = None, path: str | None = None) -> list:
    """Load training examples from storage or local path."""
    if storage is not None and path:
        data_bytes = storage.read_bytes(path)
        examples_data = json.loads(data_bytes)
    else:
        local_path = Path(path) if path else _DEFAULT_TRAINING_PATH
        if not local_path.exists():
            logger.warning("Training examples not found at %s, returning empty list", local_path)
            return []
        with open(local_path) as f:
            examples_data = json.load(f)

    if not _DSPY_AVAILABLE:
        return examples_data

    return [dspy.Example(**ex).with_inputs(*ex.get("_input_keys", [])) for ex in examples_data]


def compile_module(module, trainset, metric, strategy: str = "mipro"):
    """Compile a DSPy module with the given strategy."""
    if not _DSPY_AVAILABLE:
        raise RuntimeError("dspy is not installed")

    if strategy == "mipro":
        optimizer = dspy.MIPROv2(metric=metric, auto="light")
    elif strategy == "bootstrap":
        optimizer = dspy.BootstrapFewShot(metric=metric)
    else:
        raise ValueError(f"Unknown compilation strategy: {strategy}")

    compiled = optimizer.compile(module, trainset=trainset)
    logger.info("Compiled module with strategy=%s, trainset_size=%d", strategy, len(trainset))
    return compiled


def save_optimized_module(module, name: str, storage: StorageBackend) -> str:
    """Save compiled module to storage with versioning."""
    if not _DSPY_AVAILABLE:
        raise RuntimeError("dspy is not installed")

    import datetime
    import tempfile

    timestamp = datetime.datetime.now(tz=datetime.UTC).strftime("%Y%m%dT%H%M%S")
    path = f"dspy_modules/{name}/{timestamp}.json"

    tmp_file = Path(tempfile.gettempdir()) / f"dspy_{name}_{timestamp}"
    module.save(str(tmp_file))
    data = tmp_file.read_bytes()
    storage.write_bytes(path, data)
    logger.info("Saved optimized module %s to %s", name, path)
    return path


def load_optimized_module(name: str, storage: StorageBackend, module_class=None):
    """Load compiled module from storage."""
    if not _DSPY_AVAILABLE:
        raise RuntimeError("dspy is not installed")

    files = storage.list_files(f"dspy_modules/{name}/")
    if not files:
        raise FileNotFoundError(f"No optimized module found for {name}")

    latest = sorted(files)[-1]
    data = storage.read_bytes(latest)

    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        f.write(data)
        tmp_path = f.name

    if module_class is not None:
        module = module_class()
        module.load(tmp_path)
        return module

    return tmp_path
