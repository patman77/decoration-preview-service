"""FastAPI application for Decoration Preview Service.

This is the full-featured version with all API endpoints restored.
"""

import logging
import os
import sys
import time
from datetime import datetime, timezone

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
from backend.app.core.logging import setup_logging

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Initialize structured logging
setup_logging()

# Startup time tracking
START_TIME = time.time()

# ---------------------------------------------------------------------------
# Create FastAPI application
# ---------------------------------------------------------------------------
settings = get_settings()

app = FastAPI(
    title="Decoration Preview Service",
    description="Cloud-native API for rendering 2D artwork onto 3D elements",
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Log startup
logger.info("=" * 60)
logger.info("Decoration Preview Service starting (full version)...")
logger.info("Python %s", sys.version)
logger.info("PID %s | CWD %s", os.getpid(), os.getcwd())
logger.info("Environment: %s", settings.environment)
logger.info("=" * 60)

# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------
app.add_exception_handler(RenderJobNotFoundError, render_job_not_found_handler)
app.add_exception_handler(FileValidationError, file_validation_handler)
app.add_exception_handler(ElementNotFoundError, element_not_found_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# ---------------------------------------------------------------------------
# CORS Middleware
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins + ["*"],  # Allow all during development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Include API router
# ---------------------------------------------------------------------------
app.include_router(api_router)


# ---------------------------------------------------------------------------
# Health check endpoint
# ---------------------------------------------------------------------------
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for load balancers and container orchestration."""
    uptime = int(time.time() - START_TIME)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "healthy",
            "service": "decoration-preview-api",
            "version": settings.app_version,
            "environment": settings.environment,
            "uptime_seconds": uptime,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with service information."""
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "service": "decoration-preview-api",
            "version": settings.app_version,
            "description": "Cloud-native API for rendering 2D artwork onto 3D elements",
            "documentation": "/docs",
            "health_check": "/health",
            "api_base_url": settings.api_prefix,
            "endpoints": {
                "render": f"{settings.api_prefix}/render",
                "elements": f"{settings.api_prefix}/elements",
            },
        },
    )


# ---------------------------------------------------------------------------
# Request logging middleware
# ---------------------------------------------------------------------------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests."""
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    logger.info(
        "%s %s - %d (%.3fs)",
        request.method,
        request.url.path,
        response.status_code,
        duration,
    )
    return response
