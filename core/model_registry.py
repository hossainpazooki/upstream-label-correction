"""Model serialization, GCS persistence, and Vertex AI Model Registry integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.classifier import EnsembleMismatchClassifier

logger = logging.getLogger(__name__)


def serialize_model(classifier: EnsembleMismatchClassifier, metadata: dict | None = None) -> bytes:
    """Serialize a trained classifier to bytes using joblib."""
    import io

    import joblib

    buffer = io.BytesIO()
    joblib.dump({"classifier": classifier, "metadata": metadata or {}}, buffer)
    return buffer.getvalue()


def deserialize_model(data: bytes) -> EnsembleMismatchClassifier:
    """Deserialize a classifier from bytes."""
    import io

    import joblib

    buffer = io.BytesIO(data)
    payload = joblib.load(buffer)
    return payload["classifier"]


def save_to_gcs(artifact: bytes, bucket: str, path: str) -> str:
    """Upload a serialized model artifact to GCS. Returns the gs:// URI."""
    from google.cloud.storage import Client

    client = Client()
    blob = client.bucket(bucket).blob(path)
    blob.upload_from_string(artifact, content_type="application/octet-stream")
    uri = f"gs://{bucket}/{path}"
    logger.info("Saved model artifact to %s", uri)
    return uri


def load_from_gcs(bucket: str, path: str) -> bytes:
    """Download a serialized model artifact from GCS."""
    from google.cloud.storage import Client

    client = Client()
    blob = client.bucket(bucket).blob(path)
    return blob.download_as_bytes()


def register_with_vertex(
    artifact_uri: str,
    display_name: str,
    labels: dict[str, str] | None = None,
    project: str | None = None,
    location: str = "us-central1",
) -> Any:
    """Register a model in Vertex AI Model Registry.

    Uses the pre-built scikit-learn serving container.
    """
    from google.cloud import aiplatform

    aiplatform.init(project=project, location=location)

    model = aiplatform.Model.upload(
        display_name=display_name,
        artifact_uri=artifact_uri,
        serving_container_image_uri=("us-docker.pkg.dev/vertex-ai/prediction/sklearn-cpu.1-3:latest"),
        labels=labels or {},
    )
    logger.info("Registered model %s in Vertex AI: %s", display_name, model.resource_name)
    return model
