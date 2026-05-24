"""Fine-tune BioMistral-7B with QLoRA/DoRA for genomics explanation."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.storage import StorageBackend

logger = logging.getLogger(__name__)


def load_quantized_model(config) -> tuple:
    """Load base model with 4-bit quantization using BitsAndBytes.

    Returns (model, tokenizer) tuple.
    """
    try:
        import torch  # noqa: F401
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    except ImportError as exc:
        raise ImportError("Fine-tuning requires: pip install peft transformers bitsandbytes torch") from exc

    bnb_config = BitsAndBytesConfig(**config.bnb_config)

    model = AutoModelForCausalLM.from_pretrained(
        config.base_model,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(config.base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = prepare_model_for_kbit_training(model)

    lora_config = LoraConfig(**config.to_lora_config_kwargs())
    model = get_peft_model(model, lora_config)

    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total_params = sum(p.numel() for p in model.parameters())
    logger.info(
        "Trainable params: %d / %d (%.2f%%)",
        trainable_params,
        total_params,
        100 * trainable_params / total_params,
    )

    return model, tokenizer


def prepare_datasets(data_path: str, storage: StorageBackend | None = None) -> tuple:
    """Load and prepare train/val/test datasets from JSON.

    Returns (train_ds, val_ds, test_ds) tuple of lists.
    """
    if storage is not None:
        raw = storage.read_bytes(data_path)
        data = json.loads(raw)
    else:
        with open(data_path) as f:
            data = json.load(f)

    from training.format_utils import format_alpaca

    def format_examples(examples: list[dict]) -> list[dict]:
        formatted = []
        for ex in examples:
            text = format_alpaca(ex["instruction"], ex["input"], ex["output"])
            formatted.append({"text": text})
        return formatted

    train_ds = format_examples(data.get("train", []))
    val_ds = format_examples(data.get("val", []))
    test_ds = format_examples(data.get("test", []))

    logger.info("Datasets: train=%d, val=%d, test=%d", len(train_ds), len(val_ds), len(test_ds))
    return train_ds, val_ds, test_ds


def train(model, tokenizer, train_ds: list, val_ds: list, config, output_dir: str) -> dict:
    """Train using SFTTrainer, save adapter, upload to GCS, log to ExperimentTracker.

    Returns a dict with training metrics.
    """
    try:
        from datasets import Dataset
        from transformers import TrainingArguments
        from trl import SFTTrainer
    except ImportError as exc:
        raise ImportError("Training requires: pip install trl datasets transformers") from exc

    train_dataset = Dataset.from_list(train_ds)
    val_dataset = Dataset.from_list(val_ds) if val_ds else None

    training_args = TrainingArguments(**config.to_training_args_kwargs(output_dir))

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        args=training_args,
        max_seq_length=config.max_seq_length,
    )

    train_result = trainer.train()

    # Save adapter
    adapter_path = Path(output_dir) / "adapter"
    model.save_pretrained(str(adapter_path))
    tokenizer.save_pretrained(str(adapter_path))
    logger.info("Saved adapter to %s", adapter_path)

    metrics = {
        "train_loss": train_result.training_loss,
        "train_runtime": train_result.metrics.get("train_runtime", 0),
        "train_samples_per_second": train_result.metrics.get("train_samples_per_second", 0),
    }

    if val_dataset is not None:
        eval_metrics = trainer.evaluate()
        metrics["eval_loss"] = eval_metrics.get("eval_loss", 0)

    # Log to ExperimentTracker
    from core.experiment_tracker import ExperimentTracker

    tracker = ExperimentTracker()
    tracker.start_run(f"slm-finetune-{config.base_model.split('/')[-1]}")
    tracker.log_params(
        {
            "base_model": config.base_model,
            "r": config.r,
            "lora_alpha": config.lora_alpha,
            "use_dora": config.use_dora,
            "epochs": config.num_train_epochs,
            "batch_size": config.per_device_train_batch_size,
            "learning_rate": config.learning_rate,
        }
    )
    tracker.log_metrics(metrics)
    tracker.end_run()

    # Upload to GCS if configured
    import os

    gcs_bucket = os.environ.get("AIP_MODEL_DIR") or os.environ.get("GCS_MODEL_BUCKET")
    if gcs_bucket:
        import io
        import tarfile

        from core.model_registry import save_to_gcs

        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            tar.add(str(adapter_path), arcname="adapter")
        buf.seek(0)

        save_to_gcs(
            buf.read(),
            gcs_bucket.replace("gs://", "").split("/")[0],
            f"slm-adapters/{config.base_model.split('/')[-1]}/adapter.tar.gz",
        )

    return metrics


def main() -> None:
    """Argparse CLI entrypoint for SLM fine-tuning."""
    parser = argparse.ArgumentParser(description="Fine-tune BioMistral SLM")
    parser.add_argument("--mode", choices=["qlora", "dora"], default="qlora", help="Training mode")
    parser.add_argument("--base-model", default="BioMistral/BioMistral-7B", help="Base model ID")
    parser.add_argument("--data-path", required=True, help="Path to training data JSON")
    parser.add_argument("--output-dir", default="outputs/slm", help="Output directory")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    from training.configs.qlora_biomistral import DoRAConfig, QLoRAConfig

    config = DoRAConfig(base_model=args.base_model) if args.mode == "dora" else QLoRAConfig(base_model=args.base_model)

    model, tokenizer = load_quantized_model(config)
    train_ds, val_ds, test_ds = prepare_datasets(args.data_path)
    metrics = train(model, tokenizer, train_ds, val_ds, config, args.output_dir)

    logger.info("Training complete. Metrics: %s", metrics)


if __name__ == "__main__":
    main()
