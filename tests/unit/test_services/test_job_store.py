"""Tests for the in-memory job store."""

import pytest

from backend.app.core.exceptions import RenderJobNotFoundError
from backend.app.models.schemas import RenderStatus
from backend.app.services.job_store import InMemoryJobStore, JobRecord


@pytest.fixture
def store():
    """Create a fresh job store for each test."""
    return InMemoryJobStore()


@pytest.fixture
def sample_record():
    """Create a sample job record."""
    return JobRecord(
        job_id="job-test-123",
        element_id="elem-minifig-torso-001",
        artwork_filename="test.png",
    )


class TestJobStoreCreate:
    """Test job creation."""

    def test_create_job(self, store, sample_record):
        """Successfully create a job."""
        result = store.create_job(sample_record)
        assert result.job_id == "job-test-123"
        assert result.status == RenderStatus.PENDING

    def test_create_job_sets_timestamps(self, store, sample_record):
        """Job creation should set timestamps."""
        result = store.create_job(sample_record)
        assert result.created_at is not None
        assert result.updated_at is not None


class TestJobStoreGet:
    """Test job retrieval."""

    def test_get_existing_job(self, store, sample_record):
        """Retrieve a stored job."""
        store.create_job(sample_record)
        result = store.get_job("job-test-123")
        assert result.job_id == "job-test-123"

    def test_get_nonexistent_job(self, store):
        """Raise error for missing job."""
        with pytest.raises(RenderJobNotFoundError):
            store.get_job("job-nonexistent")


class TestJobStoreUpdate:
    """Test job status updates."""

    def test_update_status(self, store, sample_record):
        """Update job status."""
        store.create_job(sample_record)
        result = store.update_status(
            "job-test-123", RenderStatus.PROCESSING, progress_percent=50
        )
        assert result.status == RenderStatus.PROCESSING
        assert result.progress_percent == 50

    def test_update_status_with_error(self, store, sample_record):
        """Update job with error message."""
        store.create_job(sample_record)
        result = store.update_status(
            "job-test-123",
            RenderStatus.FAILED,
            error_message="Rendering timed out",
        )
        assert result.status == RenderStatus.FAILED
        assert result.error_message == "Rendering timed out"

    def test_update_nonexistent_job(self, store):
        """Raise error when updating missing job."""
        with pytest.raises(RenderJobNotFoundError):
            store.update_status("job-nonexistent", RenderStatus.COMPLETED)


class TestJobStoreDelete:
    """Test job deletion."""

    def test_delete_job(self, store, sample_record):
        """Delete an existing job."""
        store.create_job(sample_record)
        store.delete_job("job-test-123")
        with pytest.raises(RenderJobNotFoundError):
            store.get_job("job-test-123")

    def test_delete_nonexistent_job(self, store):
        """Raise error when deleting missing job."""
        with pytest.raises(RenderJobNotFoundError):
            store.delete_job("job-nonexistent")


class TestJobStoreList:
    """Test job listing."""

    def test_list_jobs_empty(self, store):
        """List returns empty when no jobs exist."""
        result = store.list_jobs()
        assert result == []

    def test_list_jobs_with_data(self, store):
        """List returns all jobs."""
        for i in range(3):
            store.create_job(
                JobRecord(
                    job_id=f"job-{i}",
                    element_id="elem-test",
                    artwork_filename="test.png",
                )
            )
        result = store.list_jobs()
        assert len(result) == 3

    def test_list_jobs_with_filter(self, store):
        """Filter jobs by status."""
        record1 = JobRecord(job_id="job-1", element_id="elem-test", artwork_filename="test.png")
        record2 = JobRecord(job_id="job-2", element_id="elem-test", artwork_filename="test.png")
        store.create_job(record1)
        store.create_job(record2)
        store.update_status("job-1", RenderStatus.COMPLETED, progress_percent=100)

        result = store.list_jobs(status_filter=RenderStatus.COMPLETED)
        assert len(result) == 1
        assert result[0].job_id == "job-1"

    def test_list_jobs_with_limit(self, store):
        """Respect limit parameter."""
        for i in range(10):
            store.create_job(
                JobRecord(
                    job_id=f"job-{i}",
                    element_id="elem-test",
                    artwork_filename="test.png",
                )
            )
        result = store.list_jobs(limit=5)
        assert len(result) == 5
