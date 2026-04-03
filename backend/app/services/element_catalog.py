"""Element catalog service.

Manages the catalog of available 3D elements that can receive decorations.
In production, this would read from S3 or a database. For the demo,
we use a static catalog.
"""

from typing import Optional

from backend.app.core.exceptions import ElementNotFoundError
from backend.app.core.logging import get_logger
from backend.app.models.schemas import ElementInfo, OutputFormat

logger = get_logger(__name__)

# Static element catalog (in production, loaded from S3/database)
ELEMENT_CATALOG: dict[str, ElementInfo] = {
    "elem-minifig-torso-001": ElementInfo(
        element_id="elem-minifig-torso-001",
        name="Minifigure Torso",
        category="Minifigure Parts",
        description="Standard minifigure torso with front and back decoration zones",
        decoration_zones=["front", "back"],
        supported_formats=[OutputFormat.PNG, OutputFormat.JPEG, OutputFormat.WEBP],
    ),
    "elem-minifig-head-001": ElementInfo(
        element_id="elem-minifig-head-001",
        name="Minifigure Head",
        category="Minifigure Parts",
        description="Standard minifigure head with face decoration zone",
        decoration_zones=["face"],
        supported_formats=[OutputFormat.PNG, OutputFormat.JPEG, OutputFormat.WEBP],
    ),
    "elem-brick-2x4-001": ElementInfo(
        element_id="elem-brick-2x4-001",
        name="2x4 Brick",
        category="Basic Bricks",
        description="Classic 2x4 brick with top surface decoration",
        decoration_zones=["top", "front"],
        supported_formats=[OutputFormat.PNG, OutputFormat.JPEG, OutputFormat.WEBP],
    ),
    "elem-tile-2x2-001": ElementInfo(
        element_id="elem-tile-2x2-001",
        name="2x2 Tile",
        category="Tiles",
        description="Flat 2x2 tile with surface decoration",
        decoration_zones=["top"],
        supported_formats=[OutputFormat.PNG, OutputFormat.JPEG, OutputFormat.WEBP],
    ),
    "elem-shield-001": ElementInfo(
        element_id="elem-shield-001",
        name="Minifigure Shield",
        category="Accessories",
        description="Minifigure shield accessory with front decoration",
        decoration_zones=["front"],
        supported_formats=[OutputFormat.PNG, OutputFormat.JPEG, OutputFormat.WEBP],
    ),
    "elem-slope-2x2-001": ElementInfo(
        element_id="elem-slope-2x2-001",
        name="2x2 Slope Brick",
        category="Slopes",
        description="2x2 slope brick with angled surface decoration",
        decoration_zones=["slope_face"],
        supported_formats=[OutputFormat.PNG, OutputFormat.JPEG, OutputFormat.WEBP],
    ),
}


def get_element(element_id: str) -> ElementInfo:
    """Retrieve an element by ID.

    Args:
        element_id: The unique element identifier.

    Returns:
        Element information.

    Raises:
        ElementNotFoundError: If element does not exist.
    """
    element = ELEMENT_CATALOG.get(element_id)
    if element is None:
        raise ElementNotFoundError(element_id)
    return element


def list_elements(
    category: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[ElementInfo], int]:
    """List available elements with optional filtering.

    Args:
        category: Optional category filter.
        limit: Maximum number of results.
        offset: Pagination offset.

    Returns:
        Tuple of (elements list, total count).
    """
    elements = list(ELEMENT_CATALOG.values())
    if category:
        elements = [e for e in elements if e.category.lower() == category.lower()]
    total = len(elements)
    return elements[offset : offset + limit], total


def element_exists(element_id: str) -> bool:
    """Check if an element exists in the catalog."""
    return element_id in ELEMENT_CATALOG
