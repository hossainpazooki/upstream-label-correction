"""QLoRA and DoRA configuration for BioMistral fine-tuning."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class QLoRAConfig:
    """QLoRA configuration for 4-bit fine-tuning of BioMistral-7B."""

    # LoRA hyperparameters
    r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    target_modules: list[str] = field(
        default_factory=lambda: [
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ]
    )
    use_dora: bool = False

    # BitsAndBytes 4-bit quantization config
    bnb_config: dict = field(
        default_factory=lambda: {
            "load_in_4bit": True,
            "bnb_4bit_quant_type": "nf4",
            "bnb_4bit_compute_dtype": "bfloat16",
            "bnb_4bit_use_double_quant": True,
        }
    )

    # Training arguments
    num_train_epochs: int = 3
    per_device_train_batch_size: int = 4
    gradient_accumulation_steps: int = 4
    learning_rate: float = 2e-4
    lr_scheduler_type: str = "cosine"
    warmup_ratio: float = 0.03
    weight_decay: float = 0.001
    max_seq_length: int = 512
    report_to: str = "tensorboard"
    logging_steps: int = 10
    save_strategy: str = "epoch"
    fp16: bool = False
    bf16: bool = True

    # Base model
    base_model: str = "BioMistral/BioMistral-7B"

    def to_lora_config_kwargs(self) -> dict:
        """Return kwargs for peft.LoraConfig."""
        return {
            "r": self.r,
            "lora_alpha": self.lora_alpha,
            "lora_dropout": self.lora_dropout,
            "target_modules": self.target_modules,
            "bias": "none",
            "task_type": "CAUSAL_LM",
            "use_dora": self.use_dora,
        }

    def to_training_args_kwargs(self, output_dir: str) -> dict:
        """Return kwargs for transformers.TrainingArguments."""
        return {
            "output_dir": output_dir,
            "num_train_epochs": self.num_train_epochs,
            "per_device_train_batch_size": self.per_device_train_batch_size,
            "gradient_accumulation_steps": self.gradient_accumulation_steps,
            "learning_rate": self.learning_rate,
            "lr_scheduler_type": self.lr_scheduler_type,
            "warmup_ratio": self.warmup_ratio,
            "weight_decay": self.weight_decay,
            "report_to": self.report_to,
            "logging_steps": self.logging_steps,
            "save_strategy": self.save_strategy,
            "fp16": self.fp16,
            "bf16": self.bf16,
        }


@dataclass
class DoRAConfig(QLoRAConfig):
    """DoRA (Weight-Decomposed Low-Rank Adaptation) configuration."""

    use_dora: bool = True
