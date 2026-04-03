"""Custom exception classes and error handlers.

Centralized error handling ensures consistent error responses
across all API endpoints.
"""

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse

from backend.app.core.logging import get_logger

logger = get_logger(__name__)


class RenderJobNotFoundError(Exception):
    """Raised when a render job ID does not exist."""

    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        super().__init__(f"Render job not found: {job_id}")


class RenderJobAlreadyCancelledError(Exception):
    """Raised when attempting to cancel an already-cancelled job."""

    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        super().__init__(f"Render job already cancelled: {job_id}")


class FileValidationError(Exception):
    """Raised when uploaded file fails validation."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class ElementNotFoundError(Exception):
    """Raised when an element ID does not exist."""

    def __init__(self, element_id: str) -> None:
        self.element_id = element_id
        super().__init__(f"Element not found: {element_id}")


async def render_job_not_found_handler(
    request: Request, exc: RenderJobNotFoundError
) -> JSONResponse:
    """Handle RenderJobNotFoundError."""
    logger.warning("Render job not found: %s", exc.job_id)
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": f"Render job not found: {exc.job_id}"},
    )


async def file_validation_handler(
    request: Request, exc: FileValidationError
) -> JSONResponse:
    """Handle FileValidationError."""
    logger.warning("File validation failed: %s", exc.detail)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.detail},
    )


async def element_not_found_handler(
    request: Request, exc: ElementNotFoundError
) -> JSONResponse:
    """Handle ElementNotFoundError."""
    logger.warning("Element not found: %s", exc.element_id)
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": f"Element not found: {exc.element_id}"},
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions with a safe error response."""
    logger.error("Unhandled exception: %s", str(exc), exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal error occurred. Please try again later."},
    )
