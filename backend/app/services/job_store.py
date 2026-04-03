"""In-memory job store simulating DynamoDB.

In production, this would be backed by DynamoDB with:
- Partition key: job_id
- GSI on user_id + created_at for listing user jobs
- TTL on completed jobs for automatic cleanup

The in-memory implementation preserves the same interface,
making it trivial to swap in the real DynamoDB client.
"""

import threading
from datetime import datetime, timezone
from typing import Optional

from backend.app.core.exceptions import RenderJobNotFoundError
from backend.app.core.logging import get_logger
from backend.app.models.schemas import RenderStatus

logger = get_logger(__name__)


class JobRecord:
    """Internal representation of a render job record."""

    def __init__(
        self,
        job_id: str,
        element_id: str,
        artwork_filename: str,
        output_format: str = "png",
        resolution_width: int = 1024,
        resolution_height: int = 1024,
        camera_angle: str = "front",
        callback_url: Optional[str] = None,
    ) -> None:
        self.job_id = job_id
        self.element_id = element_id
        self.artwork_filename = artwork_filename
        self.output_format = output_format
        self.resolution_width = resolution_width
        self.resolution_height = resolution_height
        self.camera_angle = camera_angle
        self.callback_url = callback_url
        self.status = RenderStatus.PENDING
        self.progress_percent = 0
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
        self.error_message: Optional[str] = None
        self.preview_path: Optional[str] = None
        self.thumbnail_path: Optional[str] = None
        self.file_size_bytes: int = 0

    def to_dict(self) -> dict:
        """Serialize to dictionary (mirrors DynamoDB item format)."""
        return {
            "job_id": self.job_id,
            "element_id": self.element_id,
            "artwork_filename": self.artwork_filename,
            "output_format": self.output_format,
            "resolution_width": self.resolution_width,
            "resolution_height": self.resolution_height,
            "camera_angle": self.camera_angle,
            "callback_url": self.callback_url,
            "status": self.status.value,
            "progress_percent": self.progress_percent,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "error_message": self.error_message,
            "preview_path": self.preview_path,
            "thumbnail_path": self.thumbnail_path,
            "file_size_bytes": self.file_size_bytes,
        }


class InMemoryJobStore:
    """Thread-safe in-memory job store.

    Simulates DynamoDB operations with the same interface.
    Thread safety is ensured via a reentrant lock.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.RLock()

    def create_job(self, record: JobRecord) -> JobRecord:
        """Store a new job record."""
        with self._lock:
            self._jobs[record.job_id] = record
            logger.info("Job created: %s for element %s", record.job_id, record.element_id)
            return record

    def get_job(self, job_id: str) -> JobRecord:
        """Retrieve a job by ID.

        Raises:
            RenderJobNotFoundError: If job does not exist.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise RenderJobNotFoundError(job_id)
            return job

    def update_status(
        self,
        job_id: str,
        status: RenderStatus,
        progress_percent: int = 0,
        error_message: Optional[str] = None,
        preview_path: Optional[str] = None,
        thumbnail_path: Optional[str] = None,
        file_size_bytes: Optional[int] = None,
    ) -> JobRecord:
        """Update job status and metadata."""
        with self._lock:
            job = self.get_job(job_id)
            job.status = status
            job.progress_percent = progress_percent
            job.updated_at = datetime.now(timezone.utc)
            if error_message is not None:
                job.error_message = error_message
            if preview_path is not None:
                job.preview_path = preview_path
            if thumbnail_path is not None:
                job.thumbnail_path = thumbnail_path
            if file_size_bytes is not None:
                job.file_size_bytes = file_size_bytes
            logger.info(
                "Job %s updated: status=%s, progress=%d%%",
                job_id, status.value, progress_percent,
            )
            return job

    def delete_job(self, job_id: str) -> None:
        """Delete a job record."""
        with self._lock:
            if job_id not in self._jobs:
                raise RenderJobNotFoundError(job_id)
            del self._jobs[job_id]
            logger.info("Job deleted: %s", job_id)

    def list_jobs(
        self,
        status_filter: Optional[RenderStatus] = None,
        limit: int = 50,
    ) -> list[JobRecord]:
        """List jobs with optional status filter."""
        with self._lock:
            jobs = list(self._jobs.values())
            if status_filter:
                jobs = [j for j in jobs if j.status == status_filter]
            jobs.sort(key=lambda j: j.created_at, reverse=True)
            return jobs[:limit]


# Singleton instance for the application lifecycle
job_store = InMemoryJobStore()
