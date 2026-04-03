"""FastAPI application entry point.

Configures the application with:
- CORS middleware for cross-origin requests
- API key authentication
- Custom exception handlers
- Health check endpoint
- OpenAPI documentation
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes import router as api_router
from backend.app.core.config import get_settings
from backend.app.core.exceptions import (
    ElementNotFoundError,
    FileValidationError,
    RenderJobNotFoundError,
    element_not_found_handler,
    file_validation_handler,
    generic_exception_handler,
    render_job_not_found_handler,
)
from backend.app.core.logging import get_logger, setup_logging
from backend.app.models.schemas import HealthResponse


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup/shutdown events."""
    # Startup
    logger = setup_logging()
    logger.info("Decoration Preview Service starting up...")
    logger.info("Environment: %s", get_settings().environment)
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

    # Exception handlers
    app.add_exception_handler(RenderJobNotFoundError, render_job_not_found_handler)
    app.add_exception_handler(FileValidationError, file_validation_handler)
    app.add_exception_handler(ElementNotFoundError, element_not_found_handler)
    app.add_exception_handler(Exception, generic_exception_handler)

    # Include API routes
    app.include_router(api_router)

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


# Application instance
app = create_app()
