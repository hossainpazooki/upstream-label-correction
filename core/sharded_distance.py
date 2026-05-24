"""Sharded distance computation for large-scale cross-omics matching."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor

import numpy as np


def _compute_shard(args: tuple) -> np.ndarray:
    """Worker function for computing a distance shard.

    Parameters
    ----------
    args : tuple
        (proteomics_shard, rnaseq, gene_indices, seed) where each shard is a
        subset of proteomics samples.

    Returns
    -------
    np.ndarray
        Distance sub-matrix of shape (shard_size, n_rnaseq_samples).
    """
    pro_shard, rnaseq, gene_indices, _seed = args

    # Select gene subset
    pro_sub = pro_shard[:, gene_indices]
    rna_sub = rnaseq[:, gene_indices]

    # Compute pairwise Euclidean distance
    # (n_pro, 1, n_genes) - (1, n_rna, n_genes)
    diff = pro_sub[:, np.newaxis, :] - rna_sub[np.newaxis, :, :]
    distances = np.sqrt(np.sum(diff**2, axis=2))

    return distances


class ShardedDistanceComputer:
    """Computes distance matrices in parallel shards for scalability."""

    def __init__(self, n_workers: int = 4) -> None:
        self.n_workers = n_workers

    def compute_sharded(
        self,
        proteomics: np.ndarray,
        rnaseq: np.ndarray,
        gene_indices: np.ndarray,
        n_iterations: int,
        gene_fraction: float,
        rng: np.random.Generator,
    ) -> np.ndarray:
        """Compute distance matrix using sharded parallel computation.

        Splits proteomics samples into shards, computes distance sub-matrices
        in parallel using ProcessPoolExecutor, then concatenates results.
        Repeats over multiple iterations with random gene subsets and averages.

        Parameters
        ----------
        proteomics : np.ndarray
            Proteomics expression matrix, shape (n_pro, n_genes).
        rnaseq : np.ndarray
            RNA-Seq expression matrix, shape (n_rna, n_genes).
        gene_indices : np.ndarray
            Full set of gene indices to sample from.
        n_iterations : int
            Number of random gene-subset iterations to average.
        gene_fraction : float
            Fraction of genes to use per iteration.
        rng : np.random.Generator
            Random number generator for reproducibility.

        Returns
        -------
        np.ndarray
            Averaged distance matrix of shape (n_pro, n_rna).
        """
        n_pro = proteomics.shape[0]
        n_genes_select = max(1, int(len(gene_indices) * gene_fraction))

        accumulated = np.zeros((n_pro, rnaseq.shape[0]), dtype=np.float64)

        for _iteration in range(n_iterations):
            # Random gene subset
            selected = rng.choice(gene_indices, size=n_genes_select, replace=False)

            # Split proteomics into shards
            shard_size = max(1, n_pro // self.n_workers)
            shards = []
            for start in range(0, n_pro, shard_size):
                end = min(start + shard_size, n_pro)
                seed = rng.integers(0, 2**31)
                shards.append((proteomics[start:end], rnaseq, selected, seed))

            # Compute in parallel
            with ProcessPoolExecutor(max_workers=self.n_workers) as executor:
                results = list(executor.map(_compute_shard, shards))

            accumulated += np.vstack(results)

        return accumulated / n_iterations
