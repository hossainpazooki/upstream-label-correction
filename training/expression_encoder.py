"""Gene expression encoder with contrastive learning for multi-omics."""

from __future__ import annotations

import io
import logging
from typing import TYPE_CHECKING

import numpy as np

try:
    import torch
    import torch.nn as nn

    _TORCH_AVAILABLE = True
except ImportError:
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    _TORCH_AVAILABLE = False

if TYPE_CHECKING:
    from core.storage import StorageBackend

logger = logging.getLogger(__name__)


if _TORCH_AVAILABLE:

    class GeneExpressionEncoder(nn.Module):
        """Transformer-based gene expression encoder with contrastive projection head.

        Encodes gene expression profiles (gene_id, value, modality) into
        fixed-size embeddings suitable for contrastive learning across
        proteomics and RNA-Seq modalities.
        """

        def __init__(
            self,
            n_genes: int = 20_000,
            d_model: int = 256,
            n_heads: int = 8,
            n_layers: int = 4,
            n_modalities: int = 2,
            proj_dim: int = 128,
            dropout: float = 0.1,
        ) -> None:
            super().__init__()
            self.d_model = d_model

            # Gene embedding
            self.gene_embedding = nn.Embedding(n_genes, d_model)

            # Value encoder: scalar expression value -> d_model
            self.value_encoder = nn.Linear(1, d_model)

            # Modality embedding (0=proteomics, 1=rnaseq)
            self.modality_embedding = nn.Embedding(n_modalities, d_model)

            # CLS token
            self.cls_token = nn.Parameter(torch.randn(1, 1, d_model))

            # Transformer encoder
            encoder_layer = nn.TransformerEncoderLayer(
                d_model=d_model,
                nhead=n_heads,
                dim_feedforward=d_model * 4,
                dropout=dropout,
                batch_first=True,
            )
            self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=n_layers)

            # Projection head (MLP)
            self.projection = nn.Sequential(
                nn.Linear(d_model, d_model),
                nn.ReLU(),
                nn.Linear(d_model, proj_dim),
            )

        def forward(
            self,
            gene_ids: torch.Tensor,
            values: torch.Tensor,
            modality_id: int = 0,
        ) -> torch.Tensor:
            """Encode gene expression profiles.

            Parameters
            ----------
            gene_ids : torch.Tensor
                Gene indices, shape (batch, seq_len).
            values : torch.Tensor
                Expression values, shape (batch, seq_len).
            modality_id : int
                0 for proteomics, 1 for RNA-Seq.

            Returns
            -------
            torch.Tensor
                Projected embeddings, shape (batch, proj_dim).
            """
            batch_size = gene_ids.size(0)

            # Embed genes + values + modality
            gene_emb = self.gene_embedding(gene_ids)  # (B, S, D)
            val_emb = self.value_encoder(values.unsqueeze(-1))  # (B, S, D)
            mod_emb = self.modality_embedding(
                torch.full((batch_size, gene_ids.size(1)), modality_id, device=gene_ids.device)
            )  # (B, S, D)

            x = gene_emb + val_emb + mod_emb  # (B, S, D)

            # Prepend CLS token
            cls = self.cls_token.expand(batch_size, -1, -1)  # (B, 1, D)
            x = torch.cat([cls, x], dim=1)  # (B, S+1, D)

            # Transformer encode
            x = self.transformer(x)  # (B, S+1, D)

            # CLS output -> projection
            cls_out = x[:, 0, :]  # (B, D)
            return self.projection(cls_out)  # (B, proj_dim)

    class NTXentLoss(nn.Module):
        """NT-Xent (Normalized Temperature-scaled Cross Entropy) loss.

        Used for contrastive learning between paired proteomics and RNA-Seq
        embeddings of the same samples.
        """

        def __init__(self, temperature: float = 0.07) -> None:
            super().__init__()
            self.temperature = temperature

        def forward(self, z_proteomics: torch.Tensor, z_rnaseq: torch.Tensor) -> torch.Tensor:
            """Compute NT-Xent loss for paired embeddings.

            Parameters
            ----------
            z_proteomics : torch.Tensor
                Proteomics embeddings, shape (batch, proj_dim).
            z_rnaseq : torch.Tensor
                RNA-Seq embeddings, shape (batch, proj_dim).

            Returns
            -------
            torch.Tensor
                Scalar loss.
            """
            # L2-normalize
            z_p = nn.functional.normalize(z_proteomics, dim=1)
            z_r = nn.functional.normalize(z_rnaseq, dim=1)

            batch_size = z_p.size(0)

            # Concatenate: [proteomics; rnaseq]
            z = torch.cat([z_p, z_r], dim=0)  # (2B, D)

            # Similarity matrix
            sim = torch.mm(z, z.t()) / self.temperature  # (2B, 2B)

            # Mask out self-similarity
            mask = torch.eye(2 * batch_size, device=sim.device, dtype=torch.bool)
            sim.masked_fill_(mask, float("-inf"))

            # Positive pairs: (i, i+B) and (i+B, i)
            labels = torch.cat(
                [torch.arange(batch_size, 2 * batch_size), torch.arange(batch_size)],
                dim=0,
            ).to(sim.device)

            return nn.functional.cross_entropy(sim, labels)

    class PairedOmicsDataset(torch.utils.data.Dataset):
        """Dataset for paired proteomics/RNA-Seq samples.

        Loads numpy arrays from local files or GCS via StorageBackend.
        """

        def __init__(
            self,
            proteomics_path: str,
            rnaseq_path: str,
            gene_indices_path: str | None = None,
            storage: StorageBackend | None = None,
        ) -> None:
            self.storage = storage

            self.proteomics = self._load_array(proteomics_path)
            self.rnaseq = self._load_array(rnaseq_path)

            if gene_indices_path:
                self.gene_indices = self._load_array(gene_indices_path).astype(np.int64)
            else:
                n_genes = self.proteomics.shape[1]
                self.gene_indices = np.arange(n_genes, dtype=np.int64)

            if self.proteomics.shape[0] != self.rnaseq.shape[0]:
                raise ValueError(
                    f"Sample count mismatch: proteomics={self.proteomics.shape[0]}, rnaseq={self.rnaseq.shape[0]}"
                )

        def _load_array(self, path: str) -> np.ndarray:
            if self.storage is not None:
                data = self.storage.read_bytes(path)
                return np.load(io.BytesIO(data))
            return np.load(path)

        def __len__(self) -> int:
            return self.proteomics.shape[0]

        def __getitem__(self, idx: int) -> dict:
            return {
                "gene_ids": torch.from_numpy(self.gene_indices),
                "proteomics_values": torch.from_numpy(self.proteomics[idx]).float(),
                "rnaseq_values": torch.from_numpy(self.rnaseq[idx]).float(),
            }
