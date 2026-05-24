"""Tests for sharded distance computation."""

from __future__ import annotations

import numpy as np

from core.sharded_distance import ShardedDistanceComputer, _compute_shard


class TestComputeShard:
    def test_output_shape(self):
        pro = np.random.randn(5, 10)
        rna = np.random.randn(3, 10)
        indices = np.arange(10)
        result = _compute_shard((pro, rna, indices, 42))
        assert result.shape == (5, 3)

    def test_distances_non_negative(self):
        pro = np.random.randn(4, 8)
        rna = np.random.randn(6, 8)
        indices = np.arange(8)
        result = _compute_shard((pro, rna, indices, 0))
        assert np.all(result >= 0)

    def test_self_distance_zero(self):
        data = np.random.randn(3, 5)
        indices = np.arange(5)
        result = _compute_shard((data, data, indices, 0))
        np.testing.assert_allclose(np.diag(result), 0.0, atol=1e-10)


class TestShardedDistanceComputer:
    def test_equivalence_with_direct_computation(self):
        """Sharded result should match non-sharded Euclidean distance."""
        rng = np.random.default_rng(42)
        n_pro, n_rna, n_genes = 6, 4, 10
        pro = rng.standard_normal((n_pro, n_genes))
        rna = rng.standard_normal((n_rna, n_genes))
        gene_indices = np.arange(n_genes)

        # Direct computation (single iteration, all genes)
        diff = pro[:, np.newaxis, :] - rna[np.newaxis, :, :]
        expected = np.sqrt(np.sum(diff**2, axis=2))

        computer = ShardedDistanceComputer(n_workers=2)
        result = computer.compute_sharded(
            pro,
            rna,
            gene_indices,
            n_iterations=1,
            gene_fraction=1.0,
            rng=np.random.default_rng(42),
        )

        np.testing.assert_allclose(result, expected, atol=1e-10)

    def test_output_shape(self):
        rng = np.random.default_rng(0)
        pro = rng.standard_normal((8, 20))
        rna = rng.standard_normal((5, 20))

        computer = ShardedDistanceComputer(n_workers=2)
        result = computer.compute_sharded(
            pro,
            rna,
            np.arange(20),
            n_iterations=3,
            gene_fraction=0.5,
            rng=rng,
        )
        assert result.shape == (8, 5)

    def test_multiple_iterations_averages(self):
        """Multiple iterations with full gene set should equal single iteration."""
        rng = np.random.default_rng(99)
        pro = rng.standard_normal((4, 6))
        rna = rng.standard_normal((3, 6))

        computer = ShardedDistanceComputer(n_workers=1)
        # With gene_fraction=1.0, every iteration uses all genes -> same distances
        result = computer.compute_sharded(
            pro,
            rna,
            np.arange(6),
            n_iterations=5,
            gene_fraction=1.0,
            rng=np.random.default_rng(0),
        )

        diff = pro[:, np.newaxis, :] - rna[np.newaxis, :, :]
        expected = np.sqrt(np.sum(diff**2, axis=2))
        np.testing.assert_allclose(result, expected, atol=1e-10)
