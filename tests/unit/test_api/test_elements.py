"""Tests for elements API endpoint."""

import pytest


class TestListElements:
    """Test GET /api/v1/elements endpoint."""

    def test_list_elements_success(self, client, auth_headers):
        """List all available elements."""
        response = client.get("/api/v1/elements", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "elements" in data
        assert "total_count" in data
        assert data["total_count"] > 0

    def test_list_elements_contains_expected_fields(self, client, auth_headers):
        """Each element should have required fields."""
        response = client.get("/api/v1/elements", headers=auth_headers)
        data = response.json()
        for element in data["elements"]:
            assert "element_id" in element
            assert "name" in element
            assert "category" in element
            assert "decoration_zones" in element

    def test_list_elements_filter_by_category(self, client, auth_headers):
        """Filter elements by category."""
        response = client.get(
            "/api/v1/elements",
            headers=auth_headers,
            params={"category": "Minifigure Parts"},
        )
        assert response.status_code == 200
        data = response.json()
        for element in data["elements"]:
            assert element["category"] == "Minifigure Parts"

    def test_list_elements_with_pagination(self, client, auth_headers):
        """Pagination parameters should work."""
        response = client.get(
            "/api/v1/elements",
            headers=auth_headers,
            params={"limit": 2, "offset": 0},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["elements"]) <= 2

    def test_list_elements_no_auth(self, client):
        """Reject request without authentication."""
        response = client.get("/api/v1/elements")
        assert response.status_code == 401

    def test_list_elements_invalid_auth(self, client, invalid_auth_headers):
        """Reject request with invalid auth."""
        response = client.get("/api/v1/elements", headers=invalid_auth_headers)
        assert response.status_code == 403
