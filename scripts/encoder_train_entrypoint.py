"""Vertex AI container entrypoint for expression encoder training.

Usage:
    python -m scripts.encoder_train_entrypoint \
        --dataset-uri gs://bucket/data/ \
        --config '{"n_epochs": 50, "batch_size": 32}' \
        --num-gpus 2
"""

from __future__ import annotations

import argparse
import json
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Vertex AI expression encoder training entrypoint")
    parser.add_argument("--dataset-uri", required=True, help="GCS URI of training data directory")
    parser.add_argument("--config", default="{}", help="JSON config overrides")
    parser.add_argument("--num-gpus", type=int, default=2, help="Number of GPUs for DDP")
    args = parser.parse_args()

    config = json.loads(args.config)
    dataset_uri = args.dataset_uri

    logger.info("Starting encoder training with dataset=%s num_gpus=%d", dataset_uri, args.num_gpus)

    # Parse bucket and prefix from GCS URI
    parts = dataset_uri.replace("gs://", "").split("/", 1)
    bucket_name = parts[0]
    blob_prefix = parts[1].rstrip("/") if len(parts) > 1 else ""

    # Set paths relative to bucket
    config.setdefault("bucket_name", bucket_name)
    config.setdefault("proteomics_path", f"{blob_prefix}/proteomics.npy")
    config.setdefault("rnaseq_path", f"{blob_prefix}/rnaseq.npy")

    gene_indices_path = f"{blob_prefix}/gene_indices.npy"
    config.setdefault("gene_indices_path", gene_indices_path)

    # Checkpoint dir from Vertex AI environment or config
    model_dir = os.environ.get("AIP_MODEL_DIR")
    if model_dir:
        config.setdefault("checkpoint_dir", model_dir)

    # Launch DDP training
    import sys

    from training.train_encoder_ddp import main as ddp_main

    sys.argv = [
        "encoder_train_entrypoint",
        "--config",
        json.dumps(config),
        "--num-gpus",
        str(args.num_gpus),
    ]
    ddp_main()

    logger.info("Encoder training entrypoint finished successfully")


if __name__ == "__main__":
    main()
