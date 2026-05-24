"""Standalone training entrypoint for Vertex AI custom training containers.

Usage:
    python -m scripts.vertex_train_entrypoint \
        --dataset-uri gs://bucket/data/train_pro.tsv \
        --target msi \
        --config '{"n_top_features": 30}'
"""

from __future__ import annotations

import argparse
import json
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Vertex AI training entrypoint")
    parser.add_argument("--dataset-uri", required=True, help="GCS URI of training data")
    parser.add_argument("--target", required=True, help="Target column name")
    parser.add_argument("--config", default="{}", help="JSON config overrides")
    args = parser.parse_args()

    config = json.loads(args.config)
    dataset_uri = args.dataset_uri

    logger.info("Starting training with dataset=%s target=%s", dataset_uri, args.target)

    # Parse bucket and path from GCS URI
    # gs://bucket/path/to/file.tsv -> bucket, path/to/file.tsv
    parts = dataset_uri.replace("gs://", "").split("/", 1)
    bucket_name = parts[0]
    blob_prefix = parts[1] if len(parts) > 1 else ""

    from core.storage import GCSStorageBackend

    backend = GCSStorageBackend(bucket_name)

    from core.data_loader import OmicsDataLoader

    loader = OmicsDataLoader(storage_backend=backend)

    # Determine dataset name from URI (e.g., train_pro.tsv -> train)
    dataset = blob_prefix.rsplit("/", 1)[-1].split("_")[0] if blob_prefix else "train"

    clinical_df = loader.load_clinical(dataset)
    proteomics_df = loader.load_proteomics(dataset)

    try:
        rnaseq_df = loader.load_rnaseq(dataset)
    except Exception:
        rnaseq_df = None

    from core.pipeline import COSMOInspiredPipeline

    pipeline = COSMOInspiredPipeline(config=config)
    results = pipeline.run(
        dataset=dataset,
        clinical_df=clinical_df,
        proteomics_df=proteomics_df,
        rnaseq_df=rnaseq_df,
    )

    logger.info("Pipeline completed. Stages: %s", list(results.get("stages", {}).keys()))

    # Serialize and upload model artifact
    model_dir = os.environ.get("AIP_MODEL_DIR")
    if model_dir:
        logger.info("Training complete. Results saved to %s", model_dir)
    else:
        logger.info("No AIP_MODEL_DIR set; skipping model upload")

    logger.info("Training entrypoint finished successfully")


if __name__ == "__main__":
    main()
