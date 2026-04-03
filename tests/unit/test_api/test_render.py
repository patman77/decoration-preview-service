"""Tests for render API endpoints."""

import time

import pytest


class TestCreateRenderJob:
    """Test POST /api/v1/render endpoint."""

    def test_create_render_job_success(self, client, auth_headers, sample_png_file, valid_element_id):
        """Successfully create a render job."""
        response = client.post(
            "/api/v1/render",
            headers=auth_headers,
            files={"artwork_file": ("test.png", sample_png_file, "image/png")},
            data={"element_id": valid_element_id},
        )
        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "pending"
        assert data["element_id"] == valid_element_id

    def test_create_render_job_returns_job_id(self, client, auth_headers, sample_png_file, valid_element_id):
        """Job ID should start with 'job-' prefix."""
        response = client.post(
            "/api/v1/render",
            headers=auth_headers,
            files={"artwork_file": ("test.png", sample_png_file, "image/png")},
            data={"element_id": valid_element_id},
        )
        data = response.json()
        assert data["job_id"].startswith("job-")

    def test_create_render_job_with_options(
        self, client, auth_headers, sample_png_file, valid_element_id
    ):
        """Create a job with custom output options."""
        response = client.post(
            "/api/v1/render",
            headers=auth_headers,
            files={"artwork_file": ("test.png", sample_png_file, "image/png")},
            data={
                "element_id": valid_element_id,
                "output_format": "jpeg",
                "resolution_width": 512,
                "resolution_height": 512,
                "camera_angle": "isometric",
            },
        )
        assert response.status_code == 202

    def test_create_render_job_invalid_element(self, client, auth_headers, sample_png_file, invalid_element_id):
        """Reject request with non-existent element ID."""
        response = client.post(
            "/api/v1/render",
            headers=auth_headers,
            files={"artwork_file": ("test.png", sample_png_file, "image/png")},
            data={"element_id": invalid_element_id},
        )
        assert response.status_code == 404

    def test_create_render_job_invalid_file_type(self, client, auth_headers, valid_element_id):
        """Reject files with disallowed extensions."""
        import io
        response = client.post(
            "/api/v1/render",
            headers=auth_headers,
            files={"artwork_file": ("malware.exe", io.BytesIO(b"fake content"), "application/octet-stream")},
            data={"element_id": valid_element_id},
        )
        assert response.status_code == 422

    def test_create_render_job_empty_file(self, client, auth_headers, valid_element_id):
        """Reject empty files."""
        import io
        response = client.post(
            "/api/v1/render",
            headers=auth_headers,
            files={"artwork_file": ("empty.png", io.BytesIO(b""), "image/png")},
            data={"element_id": valid_element_id},
        )
        assert response.status_code == 422

    def test_create_render_job_no_auth(self, client, sample_png_file, valid_element_id):
        """Reject request without API key."""
        response = client.post(
            "/api/v1/render",
            files={"artwork_file": ("test.png", sample_png_file, "image/png")},
            data={"element_id": valid_element_id},
        )
        assert response.status_code == 401

    def test_create_render_job_invalid_auth(self, client, invalid_auth_headers, sample_png_file, valid_element_id):
        """Reject request with wrong API key."""
        response = client.post(
            "/api/v1/render",
            headers=invalid_auth_headers,
            files={"artwork_file": ("test.png", sample_png_file, "image/png")},
            data={"element_id": valid_element_id},
        )
        assert response.status_code == 403

    def test_create_render_job_missing_element_id(self, client, auth_headers, sample_png_file):
        """Reject request without element_id."""
        response = client.post(
            "/api/v1/render",
            headers=auth_headers,
            files={"artwork_file": ("test.png", sample_png_file, "image/png")},
        )
        assert response.status_code == 422


class TestGetRenderStatus:
    """Test GET /api/v1/render/{job_id}/status endpoint."""

    def test_get_status_success(self, client, auth_headers, sample_png_file, valid_element_id):
        """Get status of an existing job."""
        # Create a job first
        create_response = client.post(
            "/api/v1/render",
            headers=auth_headers,
            files={"artwork_file": ("test.png", sample_png_file, "image/png")},
            data={"element_id": valid_element_id},
        )
        job_id = create_response.json()["job_id"]

        # Check status
        response = client.get(f"/api/v1/render/{job_id}/status", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert data["status"] in ["pending", "processing", "completed"]

    def test_get_status_not_found(self, client, auth_headers):
        """Return 404 for non-existent job."""
        response = client.get("/api/v1/render/job-nonexistent/status", headers=auth_headers)
        assert response.status_code == 404

    def test_get_status_no_auth(self, client):
        """Reject status query without auth."""
        response = client.get("/api/v1/render/job-fake/status")
        assert response.status_code == 401


class TestGetPreview:
    """Test GET /api/v1/render/{job_id}/preview endpoint."""

    def test_get_preview_not_complete(self, client, auth_headers, sample_png_file, valid_element_id):
        """Return 409 if render is not yet complete."""
        # Create a job
        create_response = client.post(
            "/api/v1/render",
            headers=auth_headers,
            files={"artwork_file": ("test.png", sample_png_file, "image/png")},
            data={"element_id": valid_element_id},
        )
        job_id = create_response.json()["job_id"]

        # Try to get preview immediately (before render completes)
        response = client.get(f"/api/v1/render/{job_id}/preview", headers=auth_headers)
        # May be 409 (not complete) or 200 (if render finished fast)
        assert response.status_code in [200, 409]

    def test_get_preview_not_found(self, client, auth_headers):
        """Return 404 for non-existent job."""
        response = client.get("/api/v1/render/job-nonexistent/preview", headers=auth_headers)
        assert response.status_code == 404


class TestDeleteRenderJob:
    """Test DELETE /api/v1/render/{job_id} endpoint."""

    def test_delete_job_success(self, client, auth_headers, sample_png_file, valid_element_id):
        """Successfully delete a render job."""
        # Create a job
        create_response = client.post(
            "/api/v1/render",
            headers=auth_headers,
            files={"artwork_file": ("test.png", sample_png_file, "image/png")},
            data={"element_id": valid_element_id},
        )
        job_id = create_response.json()["job_id"]

        # Delete the job
        response = client.delete(f"/api/v1/render/{job_id}", headers=auth_headers)
        assert response.status_code == 204

        # Verify it's gone
        response = client.get(f"/api/v1/render/{job_id}/status", headers=auth_headers)
        assert response.status_code == 404

    def test_delete_job_not_found(self, client, auth_headers):
        """Return 404 when deleting non-existent job."""
        response = client.delete("/api/v1/render/job-nonexistent", headers=auth_headers)
        assert response.status_code == 404

    def test_delete_job_no_auth(self, client):
        """Reject delete without auth."""
        response = client.delete("/api/v1/render/job-fake")
        assert response.status_code == 401
