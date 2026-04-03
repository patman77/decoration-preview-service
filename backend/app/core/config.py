"""Application configuration using pydantic-settings.

All configuration is loaded from environment variables with sensible defaults
for local development. In production, these are injected via ECS task definitions.
"""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    app_name: str = "Decoration Preview Service"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = "development"
    log_level: str = "INFO"

    # API
    api_prefix: str = "/api/v1"
    api_key: str = "dev-api-key-change-in-production"
    allowed_origins: list[str] = ["http://localhost:3000", "http://localhost:8080"]

    # AWS
    aws_region: str = "eu-central-1"
    aws_account_id: Optional[str] = None

    # S3 Buckets
    artwork_bucket: str = "decoration-preview-artwork"
    elements_bucket: str = "decoration-preview-elements"
    renders_bucket: str = "decoration-preview-renders"

    # DynamoDB
    jobs_table: str = "decoration-preview-jobs"

    # SQS
    render_queue_url: Optional[str] = None

    # File upload
    max_upload_size_mb: int = 50
    allowed_file_types: list[str] = [".png", ".jpg", ".jpeg", ".svg", ".tiff", ".psd"]

    # Rendering
    render_timeout_seconds: int = 300
    max_concurrent_renders: int = 10

    # CloudFront
    cdn_domain: Optional[str] = None
    presigned_url_expiry_seconds: int = 3600

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()
