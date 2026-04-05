"""Minimal FastAPI application - Basic version for deployment testing.

This stripped-down version ensures the container starts successfully.
Once confirmed working, we can incrementally add features.
"""

import logging
import os
import sys
import time
from datetime import datetime, timezone

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------------
# Logging – immediate stdout so CloudWatch picks it up
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Startup time tracking
START_TIME = time.time()

# ---------------------------------------------------------------------------
# Create FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Decoration Preview Service",
    description="Cloud-native API for rendering 2D artwork onto 3D elements",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Log startup
logger.info("=" * 60)
logger.info("Decoration Preview Service starting (minimal version)...")
logger.info("Python %s", sys.version)
logger.info("PID %s | CWD %s", os.getpid(), os.getcwd())
logger.info("=" * 60)

# ---------------------------------------------------------------------------
# CORS Middleware
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
            "version": "1.0.0",
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
            "version": "1.0.0",
            "description": "Cloud-native API for rendering 2D artwork onto 3D elements",
            "documentation": "/docs",
            "health_check": "/health",
            "status": "minimal deployment - testing basic functionality",
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
