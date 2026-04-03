"""Tests for the element catalog service."""

import pytest

from backend.app.core.exceptions import ElementNotFoundError
from backend.app.services.element_catalog import (
    element_exists,
    get_element,
    list_elements,
)


class TestGetElement:
    """Test element retrieval."""

    def test_get_existing_element(self):
        """Retrieve a known element."""
        element = get_element("elem-minifig-torso-001")
        assert element.element_id == "elem-minifig-torso-001"
        assert element.name == "Minifigure Torso"

    def test_get_nonexistent_element(self):
        """Raise error for unknown element."""
        with pytest.raises(ElementNotFoundError):
            get_element("elem-nonexistent")

    def test_element_has_decoration_zones(self):
        """Elements should have decoration zones."""
        element = get_element("elem-minifig-torso-001")
        assert len(element.decoration_zones) > 0
        assert "front" in element.decoration_zones


class TestElementExists:
    """Test element existence check."""

    def test_existing_element(self):
        """Return True for existing element."""
        assert element_exists("elem-minifig-torso-001") is True

    def test_nonexistent_element(self):
        """Return False for missing element."""
        assert element_exists("elem-nonexistent") is False


class TestListElements:
    """Test element listing."""

    def test_list_all_elements(self):
        """List all elements."""
        elements, total = list_elements()
        assert total > 0
        assert len(elements) == total

    def test_list_elements_by_category(self):
        """Filter by category."""
        elements, total = list_elements(category="Minifigure Parts")
        assert total > 0
        for elem in elements:
            assert elem.category == "Minifigure Parts"

    def test_list_elements_nonexistent_category(self):
        """Empty result for unknown category."""
        elements, total = list_elements(category="Nonexistent")
        assert total == 0
        assert elements == []

    def test_list_elements_with_pagination(self):
        """Pagination should limit results."""
        elements, total = list_elements(limit=2, offset=0)
        assert len(elements) <= 2
        assert total >= len(elements)
