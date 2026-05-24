"""Vertex AI container entrypoint for SLM fine-tuning.

Usage:
    python -m scripts.slm_train_entrypoint \
        --mode qlora \
        --base-model BioMistral/BioMistral-7B \
        --dataset-uri gs://bucket/data/slm_training.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Vertex AI SLM training entrypoint")
    parser.add_argument("--mode", choices=["qlora", "dora"], default="qlora", help="Training mode")
    parser.add_argument("--base-model", default="BioMistral/BioMistral-7B", help="Base model ID")
    parser.add_argument("--dataset-uri", required=True, help="GCS URI of training data JSON")
    args = parser.parse_args()

    logger.info("Starting SLM training: mode=%s model=%s dataset=%s", args.mode, args.base_model, args.dataset_uri)

    # Parse GCS URI
    parts = args.dataset_uri.replace("gs://", "").split("/", 1)
    bucket_name = parts[0]
    blob_path = parts[1] if len(parts) > 1 else ""

    # Download dataset from GCS
    from core.storage import GCSStorageBackend

    backend = GCSStorageBackend(bucket_name)
    data_bytes = backend.read_bytes(blob_path)

    local_data_path = "/tmp/slm_training_data.json"
    with open(local_data_path, "wb") as f:
        f.write(data_bytes)

    logger.info("Downloaded training data to %s (%d bytes)", local_data_path, len(data_bytes))

    # Load config
    from training.configs.qlora_biomistral import DoRAConfig, QLoRAConfig

    config = DoRAConfig(base_model=args.base_model) if args.mode == "dora" else QLoRAConfig(base_model=args.base_model)

    # Run training
    from training.finetune_slm import load_quantized_model, prepare_datasets, train

    output_dir = os.environ.get("AIP_MODEL_DIR", "/tmp/slm_output")
    model, tokenizer = load_quantized_model(config)
    train_ds, val_ds, test_ds = prepare_datasets(local_data_path)
    metrics = train(model, tokenizer, train_ds, val_ds, config, output_dir)

    logger.info("SLM training complete. Metrics: %s", json.dumps(metrics))


if __name__ == "__main__":
    main()
