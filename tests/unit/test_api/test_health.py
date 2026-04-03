"""Tests for health check endpoint."""

import pytest


class TestHealthCheck:
    """Test the /health endpoint."""

    def test_health_check_returns_200(self, client):
        """Health check should return 200 with service info."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_check_contains_status(self, client):
        """Health check should report healthy status."""
        response = client.get("/health")
        data = response.json()
        assert data["status"] == "healthy"

    def test_health_check_contains_version(self, client):
        """Health check should include API version."""
        response = client.get("/health")
        data = response.json()
        assert "version" in data
        assert data["version"] == "1.0.0"

    def test_health_check_contains_environment(self, client):
        """Health check should include environment."""
        response = client.get("/health")
        data = response.json()
        assert "environment" in data

    def test_health_check_no_auth_required(self, client):
        """Health check should not require authentication."""
        response = client.get("/health")
        assert response.status_code == 200
