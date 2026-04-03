"""Pydantic request and response models.

All API contracts are defined here, ensuring strict validation
and automatic OpenAPI documentation generation.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# --- Enums ---

class RenderStatus(str, Enum):
    """Possible states of a render job."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OutputFormat(str, Enum):
    """Supported output image formats."""
    PNG = "png"
    JPEG = "jpeg"
    WEBP = "webp"


# --- Request Models ---

class RenderRequest(BaseModel):
    """Request body for creating a new render job.

    The artwork file is uploaded as multipart form data alongside
    these JSON fields.
    """
    element_id: str = Field(
        ...,
        description="Unique identifier of the 3D element to apply decoration to",
        examples=["elem-minifig-torso-001"],
        min_length=1,
        max_length=100,
    )
    output_format: OutputFormat = Field(
        default=OutputFormat.PNG,
        description="Desired output image format",
    )
    resolution_width: int = Field(
        default=1024,
        description="Output image width in pixels",
        ge=64,
        le=4096,
    )
    resolution_height: int = Field(
        default=1024,
        description="Output image height in pixels",
        ge=64,
        le=4096,
    )
    camera_angle: Optional[str] = Field(
        default="front",
        description="Camera angle for the preview render",
        examples=["front", "back", "left", "right", "isometric"],
    )
    callback_url: Optional[str] = Field(
        default=None,
        description="Webhook URL to notify when rendering is complete",
    )


# --- Response Models ---

class RenderJobResponse(BaseModel):
    """Response after creating a render job."""
    job_id: str = Field(..., description="Unique identifier for the render job")
    status: RenderStatus = Field(..., description="Current job status")
    element_id: str = Field(..., description="Element ID being rendered")
    created_at: datetime = Field(..., description="Job creation timestamp")
    estimated_duration_seconds: Optional[int] = Field(
        default=30,
        description="Estimated rendering time in seconds",
    )
    message: str = Field(
        default="Render job queued successfully",
        description="Human-readable status message",
    )


class RenderStatusResponse(BaseModel):
    """Response for job status queries."""
    job_id: str = Field(..., description="Unique identifier for the render job")
    status: RenderStatus = Field(..., description="Current job status")
    element_id: str = Field(..., description="Element ID being rendered")
    created_at: datetime = Field(..., description="Job creation timestamp")
    updated_at: datetime = Field(..., description="Last status update timestamp")
    progress_percent: int = Field(
        default=0,
        description="Rendering progress (0-100)",
        ge=0,
        le=100,
    )
    estimated_duration_seconds: Optional[int] = Field(
        default=None,
        description="Estimated remaining time in seconds",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error details if the job failed",
    )


class PreviewResponse(BaseModel):
    """Response containing the rendered preview."""
    job_id: str = Field(..., description="Render job ID")
    preview_url: str = Field(
        ...,
        description="Pre-signed URL to download the rendered preview image",
    )
    thumbnail_url: Optional[str] = Field(
        default=None,
        description="Pre-signed URL for a thumbnail version",
    )
    output_format: OutputFormat = Field(..., description="Output image format")
    resolution_width: int = Field(..., description="Image width in pixels")
    resolution_height: int = Field(..., description="Image height in pixels")
    file_size_bytes: int = Field(..., description="File size in bytes")
    expires_at: datetime = Field(
        ...,
        description="When the pre-signed URL expires",
    )


class ElementInfo(BaseModel):
    """Information about an available 3D element."""
    element_id: str = Field(..., description="Unique element identifier")
    name: str = Field(..., description="Human-readable element name")
    category: str = Field(..., description="Element category")
    description: Optional[str] = Field(default=None, description="Element description")
    thumbnail_url: Optional[str] = Field(
        default=None,
        description="URL to element thumbnail image",
    )
    decoration_zones: list[str] = Field(
        default_factory=list,
        description="Available decoration zones on this element",
    )
    supported_formats: list[OutputFormat] = Field(
        default_factory=lambda: [OutputFormat.PNG, OutputFormat.JPEG, OutputFormat.WEBP],
        description="Supported output formats for this element",
    )


class ElementListResponse(BaseModel):
    """Response for listing available elements."""
    elements: list[ElementInfo] = Field(..., description="List of available elements")
    total_count: int = Field(..., description="Total number of elements")


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(default="healthy", description="Service health status")
    version: str = Field(..., description="API version")
    environment: str = Field(..., description="Deployment environment")


class ErrorResponse(BaseModel):
    """Standard error response."""
    detail: str = Field(..., description="Error message")
    error_code: Optional[str] = Field(default=None, description="Machine-readable error code")
