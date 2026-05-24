"""CLI for compiling DSPy modules.

Usage: python -m scripts.compile_dspy --module biomarker_discovery --strategy mipro
"""

from __future__ import annotations

import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MODULE_MAP = {
    "biomarker_discovery": ("dspy_modules.biomarker_discovery", "BiomarkerDiscoveryModule"),
    "sample_qc": ("dspy_modules.sample_qc", "SampleQCModule"),
    "feature_interpret": ("dspy_modules.feature_interpret", "FeatureInterpretModule"),
    "regulatory_report": ("dspy_modules.regulatory_report", "RegulatoryReportModule"),
}


def main():
    parser = argparse.ArgumentParser(description="Compile DSPy modules")
    parser.add_argument("--module", required=True, choices=list(MODULE_MAP.keys()))
    parser.add_argument("--strategy", default="mipro", choices=["mipro", "bootstrap"])
    parser.add_argument("--training-data", default=None, help="Path to training examples JSON")
    parser.add_argument("--bucket", default=None, help="GCS bucket for saving compiled module")
    args = parser.parse_args()

    try:
        import dspy  # noqa: F401
    except ImportError:
        logger.error("dspy is not installed. Install with: pip install dspy")
        sys.exit(1)

    from importlib import import_module as imp

    from core.storage import get_storage_backend
    from dspy_modules.compile import compile_module, load_training_examples, save_optimized_module
    from dspy_modules.metrics import composite_metric

    mod_path, class_name = MODULE_MAP[args.module]
    mod = imp(mod_path)
    module_class = getattr(mod, class_name)
    module = module_class()

    storage = get_storage_backend(bucket_name=args.bucket)
    trainset = load_training_examples(storage=storage if args.bucket else None, path=args.training_data)

    if not trainset:
        logger.error("No training examples found. Provide --training-data or populate the default path.")
        sys.exit(1)

    logger.info("Compiling %s with strategy=%s, %d examples", args.module, args.strategy, len(trainset))
    compiled = compile_module(module, trainset, composite_metric, strategy=args.strategy)

    if args.bucket:
        path = save_optimized_module(compiled, args.module, storage)
        logger.info("Saved compiled module to %s", path)
    else:
        logger.info("No --bucket specified, compiled module not saved to storage")

    logger.info("Compilation complete")


if __name__ == "__main__":
    main()
