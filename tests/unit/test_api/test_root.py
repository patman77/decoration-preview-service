"""Tests for root endpoint."""

import pytest


class TestRootEndpoint:
    """Test the / (root) endpoint."""

    def test_root_returns_200(self, client):
        """Root endpoint should return 200 OK."""
        response = client.get("/")
        assert response.status_code == 200

    def test_root_contains_service_name(self, client):
        """Root endpoint should include the service name."""
        response = client.get("/")
        data = response.json()
        assert "service" in data
        assert data["service"] == "Decoration Preview Service"

    def test_root_contains_version(self, client):
        """Root endpoint should include the API version."""
        response = client.get("/")
        data = response.json()
        assert "version" in data
        assert data["version"] == "1.0.0"

    def test_root_contains_description(self, client):
        """Root endpoint should include a service description."""
        response = client.get("/")
        data = response.json()
        assert "description" in data
        assert len(data["description"]) > 0

    def test_root_contains_docs_url(self, client):
        """Root endpoint should link to the API documentation."""
        response = client.get("/")
        data = response.json()
        assert "docs_url" in data
        assert data["docs_url"] == "/docs"

    def test_root_contains_health_url(self, client):
        """Root endpoint should link to the health check."""
        response = client.get("/")
        data = response.json()
        assert "health_url" in data
        assert data["health_url"] == "/health"

    def test_root_contains_api_base_url(self, client):
        """Root endpoint should include the API base URL."""
        response = client.get("/")
        data = response.json()
        assert "api_base_url" in data
        assert data["api_base_url"] == "/api/v1"

    def test_root_no_auth_required(self, client):
        """Root endpoint should not require authentication."""
        response = client.get("/")
        assert response.status_code == 200
