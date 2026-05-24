"""GCP integration tests.

These tests require a deployed GCP environment and are gated by the 'gcp' marker.
Run with: pytest -m gcp
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.gcp


class _FakeClassifier:
    """Picklable stub for model serialization tests."""

    some_attr = "test"


GCP_PROJECT = os.environ.get("GCP_PROJECT_ID")
GCS_DATA_BUCKET = os.environ.get("GCS_DATA_BUCKET")
GCS_MODEL_BUCKET = os.environ.get("GCS_MODEL_BUCKET")
MCP_SSE_URL = os.environ.get("MCP_SSE_URL")
API_URL = os.environ.get("API_URL")
VERTEX_EXPERIMENT = os.environ.get("VERTEX_AI_EXPERIMENT_NAME")


@pytest.fixture
def skip_if_no_gcp():
    if not GCP_PROJECT:
        pytest.skip("GCP_PROJECT_ID not set")


class TestCloudRunHealth:
    """Verify Cloud Run services are accessible."""

    def test_api_health(self, skip_if_no_gcp):
        if not API_URL:
            pytest.skip("API_URL not set")
        import httpx

        resp = httpx.get(f"{API_URL}/health", timeout=10)
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_mcp_sse_health(self, skip_if_no_gcp):
        if not MCP_SSE_URL:
            pytest.skip("MCP_SSE_URL not set")
        import httpx

        resp = httpx.get(f"{MCP_SSE_URL}/health", timeout=10)
        assert resp.status_code == 200
        assert resp.json()["transport"] == "sse"


class TestGCSRoundTrip:
    """Verify GCS read/write operations."""

    def test_write_and_read(self, skip_if_no_gcp):
        if not GCS_DATA_BUCKET:
            pytest.skip("GCS_DATA_BUCKET not set")

        from core.storage import GCSStorageBackend

        backend = GCSStorageBackend(GCS_DATA_BUCKET)
        test_data = b"integration-test-data"
        test_path = "_test/integration_test.bin"

        backend.write_bytes(test_path, test_data)
        result = backend.read_bytes(test_path)
        assert result == test_data

        # Cleanup
        from google.cloud.storage import Client

        Client().bucket(GCS_DATA_BUCKET).blob(test_path).delete()

    def test_list_files(self, skip_if_no_gcp):
        if not GCS_DATA_BUCKET:
            pytest.skip("GCS_DATA_BUCKET not set")

        from core.storage import GCSStorageBackend

        backend = GCSStorageBackend(GCS_DATA_BUCKET)
        files = backend.list_files("")
        assert isinstance(files, list)


class TestVertexAIExperiment:
    """Verify Vertex AI experiment tracking."""

    def test_experiment_run(self, skip_if_no_gcp):
        if not VERTEX_EXPERIMENT:
            pytest.skip("VERTEX_AI_EXPERIMENT_NAME not set")

        from core.experiment_tracker import ExperimentTracker

        tracker = ExperimentTracker(
            project=GCP_PROJECT,
            experiment_name=VERTEX_EXPERIMENT,
        )
        tracker.start_run("integration-test-run")
        tracker.log_metrics({"test_metric": 0.95})
        tracker.log_params({"test_param": "value"})
        tracker.end_run()


class TestModelRegistry:
    """Verify model serialization and GCS upload."""

    def test_serialize_roundtrip(self):
        """Test local serialization without GCP."""
        from core.model_registry import deserialize_model, serialize_model

        classifier = _FakeClassifier()
        data = serialize_model(classifier, {"test": True})
        assert isinstance(data, bytes)
        assert len(data) > 0

        loaded = deserialize_model(data)
        assert loaded.some_attr == "test"

    def test_upload_to_gcs(self, skip_if_no_gcp):
        if not GCS_MODEL_BUCKET:
            pytest.skip("GCS_MODEL_BUCKET not set")

        from core.model_registry import load_from_gcs, save_to_gcs

        test_data = b"test-model-artifact"
        test_path = "_test/model_test.bin"

        uri = save_to_gcs(test_data, GCS_MODEL_BUCKET, test_path)
        assert uri == f"gs://{GCS_MODEL_BUCKET}/{test_path}"

        result = load_from_gcs(GCS_MODEL_BUCKET, test_path)
        assert result == test_data

        # Cleanup
        from google.cloud.storage import Client

        Client().bucket(GCS_MODEL_BUCKET).blob(test_path).delete()


class TestMCPSSEConnection:
    """Verify MCP SSE transport connectivity."""

    def test_sse_endpoint_exists(self, skip_if_no_gcp):
        if not MCP_SSE_URL:
            pytest.skip("MCP_SSE_URL not set")
        import httpx

        resp = httpx.get(f"{MCP_SSE_URL}/sse", timeout=5)
        # SSE endpoint should return 200 with text/event-stream
        assert resp.status_code == 200
