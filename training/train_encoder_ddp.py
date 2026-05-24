"""Distributed Data Parallel training for the gene expression encoder."""

from __future__ import annotations

import argparse
import json
import logging
import os

try:
    import torch
    import torch.distributed as dist
    import torch.multiprocessing as mp
    from torch.nn.parallel import DistributedDataParallel as DDP
    from torch.utils.data import DataLoader
    from torch.utils.data.distributed import DistributedSampler

    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False

logger = logging.getLogger(__name__)


def setup_ddp(rank: int, world_size: int) -> None:
    """Initialize the distributed process group."""
    os.environ.setdefault("MASTER_ADDR", "localhost")
    os.environ.setdefault("MASTER_PORT", "12355")
    dist.init_process_group("nccl", rank=rank, world_size=world_size)
    torch.cuda.set_device(rank)


def cleanup_ddp() -> None:
    """Destroy the distributed process group."""
    dist.destroy_process_group()


def train_one_epoch(
    model: torch.nn.Module,
    dataloader: DataLoader,
    optimizer: torch.optim.Optimizer,
    loss_fn: torch.nn.Module,
    rank: int,
) -> float:
    """Train for one epoch, returning average loss."""
    model.train()
    total_loss = 0.0
    n_batches = 0

    for batch in dataloader:
        gene_ids = batch["gene_ids"].to(rank)
        pro_vals = batch["proteomics_values"].to(rank)
        rna_vals = batch["rnaseq_values"].to(rank)

        z_pro = model(gene_ids, pro_vals, modality_id=0)
        z_rna = model(gene_ids, rna_vals, modality_id=1)

        loss = loss_fn(z_pro, z_rna)

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        total_loss += loss.item()
        n_batches += 1

    return total_loss / max(n_batches, 1)


def train_ddp(rank: int, world_size: int, config: dict) -> None:
    """Full DDP training loop with GCS checkpoint saving (rank 0 only)."""
    setup_ddp(rank, world_size)

    from training.expression_encoder import (
        GeneExpressionEncoder,
        NTXentLoss,
        PairedOmicsDataset,
    )

    # Dataset
    storage = None
    bucket_name = config.get("bucket_name")
    if bucket_name:
        from core.storage import GCSStorageBackend

        storage = GCSStorageBackend(bucket_name)

    dataset = PairedOmicsDataset(
        proteomics_path=config["proteomics_path"],
        rnaseq_path=config["rnaseq_path"],
        gene_indices_path=config.get("gene_indices_path"),
        storage=storage,
    )

    sampler = DistributedSampler(dataset, num_replicas=world_size, rank=rank)
    dataloader = DataLoader(
        dataset,
        batch_size=config.get("batch_size", 32),
        sampler=sampler,
        num_workers=config.get("num_workers", 2),
        pin_memory=True,
    )

    # Model
    model = GeneExpressionEncoder(
        n_genes=config.get("n_genes", 20_000),
        d_model=config.get("d_model", 256),
        n_heads=config.get("n_heads", 8),
        n_layers=config.get("n_layers", 4),
        proj_dim=config.get("proj_dim", 128),
    ).to(rank)

    model = DDP(model, device_ids=[rank])

    optimizer = torch.optim.AdamW(model.parameters(), lr=config.get("lr", 1e-4))
    loss_fn = NTXentLoss(temperature=config.get("temperature", 0.07)).to(rank)

    n_epochs = config.get("n_epochs", 50)

    for epoch in range(n_epochs):
        sampler.set_epoch(epoch)
        avg_loss = train_one_epoch(model, dataloader, optimizer, loss_fn, rank)

        if rank == 0:
            logger.info("Epoch %d/%d - loss: %.4f", epoch + 1, n_epochs, avg_loss)

            # Save checkpoint periodically
            if (epoch + 1) % config.get("checkpoint_every", 10) == 0:
                _save_checkpoint(model, optimizer, epoch, avg_loss, config)

    # Save final checkpoint
    if rank == 0:
        _save_checkpoint(model, optimizer, n_epochs - 1, avg_loss, config)
        logger.info("Training complete")

    cleanup_ddp()


def _save_checkpoint(
    model: torch.nn.Module,
    optimizer: torch.optim.Optimizer,
    epoch: int,
    loss: float,
    config: dict,
) -> None:
    """Save checkpoint to local disk or GCS."""
    import io

    state = {
        "epoch": epoch,
        "model_state_dict": model.module.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "loss": loss,
    }

    buffer = io.BytesIO()
    torch.save(state, buffer)
    checkpoint_bytes = buffer.getvalue()

    checkpoint_dir = config.get("checkpoint_dir", "checkpoints")
    filename = f"encoder_epoch_{epoch + 1}.pt"

    bucket_name = config.get("bucket_name")
    if bucket_name:
        from core.storage import GCSStorageBackend

        backend = GCSStorageBackend(bucket_name)
        backend.write_bytes(f"{checkpoint_dir}/{filename}", checkpoint_bytes)
        logger.info("Saved checkpoint to gs://%s/%s/%s", bucket_name, checkpoint_dir, filename)
    else:
        import pathlib

        out_dir = pathlib.Path(checkpoint_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / filename).write_bytes(checkpoint_bytes)
        logger.info("Saved checkpoint to %s/%s", checkpoint_dir, filename)


def main() -> None:
    """CLI entrypoint: parse args and launch DDP training via mp.spawn."""
    if not _TORCH_AVAILABLE:
        raise ImportError("PyTorch is required for DDP training")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="DDP expression encoder training")
    parser.add_argument("--config", required=True, help="JSON config string or path")
    parser.add_argument("--num-gpus", type=int, default=2, help="Number of GPUs")
    args = parser.parse_args()

    # Load config
    if os.path.isfile(args.config):
        with open(args.config) as f:
            config = json.load(f)
    else:
        config = json.loads(args.config)

    world_size = args.num_gpus
    mp.spawn(train_ddp, args=(world_size, config), nprocs=world_size, join=True)


if __name__ == "__main__":
    main()
