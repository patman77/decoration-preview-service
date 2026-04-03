"""API route definitions.

All endpoints follow RESTful conventions with:
- Consistent URL patterns
- Proper HTTP methods and status codes
- Request validation via Pydantic models
- API key authentication
- Comprehensive OpenAPI documentation
"""

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import FileResponse

from backend.app.core.config import Settings, get_settings
from backend.app.core.exceptions import (
    ElementNotFoundError,
    FileValidationError,
    RenderJobNotFoundError,
)
from backend.app.core.logging import get_logger
from backend.app.core.security import verify_api_key
from backend.app.models.schemas import (
    ElementListResponse,
    ErrorResponse,
    OutputFormat,
    PreviewResponse,
    RenderJobResponse,
    RenderStatus,
    RenderStatusResponse,
)
from backend.app.services.element_catalog import element_exists, get_element, list_elements
from backend.app.services.file_validator import validate_upload
from backend.app.services.job_store import JobRecord, job_store
from backend.app.workers.renderer import process_render_job

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Render Operations"])


# --- Render Endpoints ---

@router.post(
    "/render",
    response_model=RenderJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a new render job",
    description="""
    Upload a 2D artwork file and specify a target element to receive
    a rendered 3D preview. The rendering is performed asynchronously;
    poll the status endpoint or provide a callback URL for notification.
    """,
    responses={
        422: {"model": ErrorResponse, "description": "Validation error"},
        401: {"model": ErrorResponse, "description": "Missing API key"},
        403: {"model": ErrorResponse, "description": "Invalid API key"},
    },
)
async def create_render_job(
    background_tasks: BackgroundTasks,
    artwork_file: UploadFile = File(
        ..., description="2D artwork file (PNG, JPEG, SVG, TIFF, PSD)"
    ),
    element_id: str = Form(
        ..., description="Target element ID", examples=["elem-minifig-torso-001"]
    ),
    output_format: OutputFormat = Form(
        default=OutputFormat.PNG, description="Output image format"
    ),
    resolution_width: int = Form(default=1024, ge=64, le=4096, description="Output width (px)"),
    resolution_height: int = Form(default=1024, ge=64, le=4096, description="Output height (px)"),
    camera_angle: str = Form(default="front", description="Camera angle for preview"),
    callback_url: Optional[str] = Form(default=None, description="Webhook callback URL"),
    api_key: str = Depends(verify_api_key),
) -> RenderJobResponse:
    """Create a new render job.

    The artwork file is validated and the render is queued for
    asynchronous processing. Returns immediately with a job ID.
    """
    # Validate element exists
    if not element_exists(element_id):
        raise ElementNotFoundError(element_id)

    # Validate uploaded file
    filename, content = await validate_upload(artwork_file)

    # Generate unique job ID
    job_id = f"job-{uuid.uuid4().hex[:12]}"

    # Create job record
    record = JobRecord(
        job_id=job_id,
        element_id=element_id,
        artwork_filename=filename,
        output_format=output_format.value,
        resolution_width=resolution_width,
        resolution_height=resolution_height,
        camera_angle=camera_angle,
        callback_url=callback_url,
    )
    job_store.create_job(record)

    # Queue rendering in background
    # In production: send message to SQS queue
    background_tasks.add_task(process_render_job, job_id, content)

    logger.info(
        "Render job created: %s (element=%s, file=%s)",
        job_id, element_id, filename,
    )

    return RenderJobResponse(
        job_id=job_id,
        status=RenderStatus.PENDING,
        element_id=element_id,
        created_at=record.created_at,
        estimated_duration_seconds=30,
        message="Render job queued successfully. Use the status endpoint to track progress.",
    )


@router.get(
    "/render/{job_id}/status",
    response_model=RenderStatusResponse,
    summary="Get render job status",
    description="Check the current status and progress of a render job.",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
    },
)
async def get_render_status(
    job_id: str,
    api_key: str = Depends(verify_api_key),
) -> RenderStatusResponse:
    """Retrieve the current status of a render job."""
    job = job_store.get_job(job_id)

    estimated_remaining = None
    if job.status == RenderStatus.PROCESSING and job.progress_percent > 0:
        elapsed = (datetime.now(timezone.utc) - job.created_at).total_seconds()
        estimated_total = elapsed / (job.progress_percent / 100)
        estimated_remaining = max(0, int(estimated_total - elapsed))

    return RenderStatusResponse(
        job_id=job.job_id,
        status=job.status,
        element_id=job.element_id,
        created_at=job.created_at,
        updated_at=job.updated_at,
        progress_percent=job.progress_percent,
        estimated_duration_seconds=estimated_remaining,
        error_message=job.error_message,
    )


@router.get(
    "/render/{job_id}/preview",
    response_model=PreviewResponse,
    summary="Get rendered preview",
    description="""
    Retrieve the rendered preview image. Only available after the
    render job has completed. Returns a pre-signed URL for downloading
    the image (in production; serves file directly in development).
    """,
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        409: {"model": ErrorResponse, "description": "Render not yet complete"},
    },
)
async def get_preview(
    job_id: str,
    api_key: str = Depends(verify_api_key),
    settings: Settings = Depends(get_settings),
) -> PreviewResponse:
    """Get the rendered preview for a completed job."""
    job = job_store.get_job(job_id)

    if job.status != RenderStatus.COMPLETED:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Render job is not complete. Current status: {job.status.value}",
        )

    # In production: generate pre-signed S3 URL
    # For demo: return local file path as URL
    base_url = "/api/v1/render"
    preview_url = f"{base_url}/{job_id}/download"
    thumbnail_url = f"{base_url}/{job_id}/download?thumbnail=true"

    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=settings.presigned_url_expiry_seconds
    )

    return PreviewResponse(
        job_id=job_id,
        preview_url=preview_url,
        thumbnail_url=thumbnail_url,
        output_format=OutputFormat(job.output_format),
        resolution_width=job.resolution_width,
        resolution_height=job.resolution_height,
        file_size_bytes=job.file_size_bytes,
        expires_at=expires_at,
    )


@router.get(
    "/render/{job_id}/download",
    summary="Download rendered image",
    description="Download the actual rendered image file.",
    responses={
        404: {"model": ErrorResponse, "description": "Job or file not found"},
    },
)
async def download_preview(
    job_id: str,
    thumbnail: bool = Query(default=False, description="Download thumbnail instead"),
    api_key: str = Depends(verify_api_key),
) -> FileResponse:
    """Download the rendered preview image file."""
    job = job_store.get_job(job_id)

    if job.status != RenderStatus.COMPLETED:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Render job is not complete. Current status: {job.status.value}",
        )

    file_path = job.thumbnail_path if thumbnail else job.preview_path
    if not file_path or not os.path.exists(file_path):
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rendered file not found.",
        )

    media_types = {
        "png": "image/png",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
    }

    return FileResponse(
        path=file_path,
        media_type=media_types.get(job.output_format, "image/png"),
        filename=f"preview_{job_id}.{job.output_format}",
    )


@router.delete(
    "/render/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancel or delete a render job",
    description="""
    Cancel a pending/processing render job, or delete a completed
    job and its associated files.
    """,
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
    },
)
async def delete_render_job(
    job_id: str,
    api_key: str = Depends(verify_api_key),
) -> None:
    """Cancel or delete a render job."""
    job = job_store.get_job(job_id)

    # If job is still processing, mark as cancelled
    if job.status in (RenderStatus.PENDING, RenderStatus.PROCESSING):
        job_store.update_status(job_id, RenderStatus.CANCELLED)
        logger.info("Job cancelled: %s", job_id)

    # Clean up rendered files
    for path in [job.preview_path, job.thumbnail_path]:
        if path and os.path.exists(path):
            os.remove(path)
            logger.info("Cleaned up file: %s", path)

    # Remove job record
    job_store.delete_job(job_id)


# --- Element Endpoints ---

@router.get(
    "/elements",
    response_model=ElementListResponse,
    summary="List available elements",
    description="List all available 3D elements that can receive decoration previews.",
)
async def list_available_elements(
    category: Optional[str] = Query(
        default=None, description="Filter by element category"
    ),
    limit: int = Query(default=50, ge=1, le=100, description="Maximum results"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    api_key: str = Depends(verify_api_key),
) -> ElementListResponse:
    """List available 3D elements."""
    elements, total = list_elements(category=category, limit=limit, offset=offset)
    return ElementListResponse(elements=elements, total_count=total)
