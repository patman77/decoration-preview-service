"""FastAPI application entry point.

Configures the application with:
- CORS middleware for cross-origin requests
- API key authentication
- Custom exception handlers
- Health check endpoint
- OpenAPI documentation
"""

import logging
import os
import sys
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger, setup_logging
from backend.app.models.schemas import HealthResponse, ServiceInfoResponse

# Set up a bootstrap logger immediately so any import errors are visible
# in CloudWatch before the full logging configuration runs.
_bootstrap_logger = logging.getLogger("decoration_preview.bootstrap")
_bootstrap_handler = logging.StreamHandler(sys.stdout)
_bootstrap_handler.setFormatter(
    logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
)
_bootstrap_logger.addHandler(_bootstrap_handler)
_bootstrap_logger.setLevel(logging.INFO)

# Defer heavy / side-effect-laden imports so that a failure in one
# sub-module does not prevent the health-check endpoint from loading.
_api_router = None
_exception_handlers_loaded = False

try:
    from backend.app.api.routes import router as api_router

    _api_router = api_router
    _bootstrap_logger.info("API routes imported successfully")
except Exception:
    _bootstrap_logger.error(
        "Failed to import API routes – the /health endpoint will still work "
        "but all /api/v1/* routes will be unavailable:\n%s",
        traceback.format_exc(),
    )

try:
    from backend.app.core.exceptions import (
        ElementNotFoundError,
        FileValidationError,
        RenderJobNotFoundError,
        element_not_found_handler,
        file_validation_handler,
        generic_exception_handler,
        render_job_not_found_handler,
    )

    _exception_handlers_loaded = True
except Exception:
    _bootstrap_logger.error(
        "Failed to import exception handlers:\n%s", traceback.format_exc()
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup/shutdown events."""
    # Startup
    logger = setup_logging()
    settings = get_settings()
    logger.info("Decoration Preview Service starting up...")
    logger.info("Environment: %s", settings.environment)
    logger.info("Python: %s", sys.version)
    logger.info("Working directory: %s", os.getcwd())
    logger.info("API routes loaded: %s", _api_router is not None)
    logger.info("Exception handlers loaded: %s", _exception_handlers_loaded)

    # Log environment variables (redact sensitive values)
    for key in sorted(os.environ):
        if any(s in key.upper() for s in ("KEY", "SECRET", "PASSWORD", "TOKEN")):
            logger.info("  env %s = [REDACTED]", key)
        elif key.startswith(("AWS_", "ENVIRONMENT", "LOG_LEVEL", "ARTWORK_", "ELEMENTS_", "RENDERS_", "JOBS_", "RENDER_QUEUE")):
            logger.info("  env %s = %s", key, os.environ[key])
    yield
    # Shutdown
    logger.info("Decoration Preview Service shutting down...")


def create_app() -> FastAPI:
    """Application factory.

    Creates and configures the FastAPI application instance.
    Uses the factory pattern for testability.
    """
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description=(
            "API service for previewing 2D decorations on 3D toy elements. "
            "Upload artwork files and receive rendered preview images showing "
            "how decorations will appear on physical elements."
        ),
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    # Exception handlers (only if the import succeeded)
    if _exception_handlers_loaded:
        app.add_exception_handler(RenderJobNotFoundError, render_job_not_found_handler)
        app.add_exception_handler(FileValidationError, file_validation_handler)
        app.add_exception_handler(ElementNotFoundError, element_not_found_handler)
        app.add_exception_handler(Exception, generic_exception_handler)

    # Include API routes (only if the import succeeded)
    if _api_router is not None:
        app.include_router(_api_router)
    else:
        _bootstrap_logger.warning(
            "API routes not loaded – only /health and / endpoints are available"
        )

    # Root endpoint (no auth required)
    @app.get(
        "/",
        response_model=ServiceInfoResponse,
        tags=["Service Info"],
        summary="Service information",
        description="Returns basic service information and navigation links.",
    )
    async def root() -> ServiceInfoResponse:
        """Root endpoint returning service metadata and useful links."""
        return ServiceInfoResponse(
            service=settings.app_name,
            version=settings.app_version,
            description=(
                "API service for previewing 2D decorations on 3D toy elements. "
                "Upload artwork files and receive rendered preview images."
            ),
            docs_url="/docs",
            health_url="/health",
            api_base_url=settings.api_prefix,
        )

    # Health check (no auth required)
    @app.get(
        "/health",
        response_model=HealthResponse,
        tags=["Health"],
        summary="Service health check",
    )
    async def health_check() -> HealthResponse:
        """Check service health status."""
        return HealthResponse(
            status="healthy",
            version=settings.app_version,
            environment=settings.environment,
        )

    # Static files & favicon
    static_dir = Path(__file__).parent / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    favicon_path = static_dir / "favicon.ico"

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        """Serve the favicon."""
        if favicon_path.is_file():
            return FileResponse(
                str(favicon_path),
                media_type="image/x-icon",
            )
        from fastapi.responses import Response

        return Response(status_code=204)

    return app


# Application instance — wrapped so that even a catastrophic error during
# factory execution still produces a running app with a /health endpoint
# that returns 503, giving operators CloudWatch visibility.
try:
    app = create_app()
    _bootstrap_logger.info("Application created successfully")
except Exception:
    _bootstrap_logger.critical(
        "FATAL: create_app() failed – creating minimal fallback app:\n%s",
        traceback.format_exc(),
    )

    # Minimal fallback app that only serves /health so the failure is
    # visible in ECS task logs and doesn't trigger an immediate OOM-like
    # silent exit.
    app = FastAPI(title="Decoration Preview Service (DEGRADED)")

    @app.get("/health")
    async def _fallback_health():
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "version": "unknown",
                "environment": os.environ.get("ENVIRONMENT", "unknown"),
                "error": "Application failed to initialise – check logs",
            },
        )

    @app.get("/")
    async def _fallback_root():
        return {"status": "degraded", "error": "Application failed to initialise"}
