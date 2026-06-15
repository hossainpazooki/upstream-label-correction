"""Global configuration settings for CLUE."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "CLUE"
    environment: str = "local"
    debug: bool = False

    # Database (PostgreSQL + TimescaleDB)
    database_url: str = "postgresql://postgres:postgres@localhost:5432/precision_genomics"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Anthropic (LLM)
    anthropic_api_key: str | None = None

    # Data paths
    data_dir: str = "data"
    raw_data_dir: str = "data/raw"

    # ML settings
    random_state: int = 42
    cv_folds: int = 10
    n_estimators: int = 500

    # Auth
    require_auth: bool = False
    api_keys: str | None = None

    # Feature flags
    enable_feature_store: bool = True

    # SLM (Small Language Model) settings
    slm_adapter_path: str | None = None
    slm_base_model: str = "BioMistral/BioMistral-7B"
    slm_endpoint_name: str | None = None
    enable_slm_routing: bool = False

    # DSPy prompt optimization
    dspy_prompts_path: str | None = None

    # GPU-accelerated training
    enable_gpu_training: bool = False
    gpu_training_image: str | None = None

    # GCP settings
    gcp_project_id: str | None = None
    gcp_region: str = "us-central1"
    gcs_data_bucket: str | None = None
    gcs_model_bucket: str | None = None
    vertex_ai_staging_bucket: str | None = None
    vertex_ai_experiment_name: str | None = None
    cloud_sql_instance: str | None = None
    use_secret_manager: bool = False
    persist_models: bool = False
    register_vertex_models: bool = False


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    settings = Settings()
    if settings.use_secret_manager and settings.gcp_project_id:
        from core.secrets import populate_secrets

        populate_secrets(settings)
    return settings
