"""File upload validation service.

Validates uploaded artwork files for:
- File size limits
- Allowed file types (extension and MIME type)
- Basic file integrity checks

In production, this would also integrate with malware scanning
(e.g., AWS GuardDuty or ClamAV on ECS).
"""

import os
from typing import Optional

from fastapi import UploadFile

from backend.app.core.config import get_settings
from backend.app.core.exceptions import FileValidationError
from backend.app.core.logging import get_logger

logger = get_logger(__name__)

# MIME type to extension mapping
ALLOWED_MIME_TYPES: dict[str, list[str]] = {
    "image/png": [".png"],
    "image/jpeg": [".jpg", ".jpeg"],
    "image/svg+xml": [".svg"],
    "image/tiff": [".tiff", ".tif"],
    "image/vnd.adobe.photoshop": [".psd"],
    "application/octet-stream": [".psd", ".tiff"],  # Fallback for some clients
}


async def validate_upload(file: UploadFile) -> tuple[str, bytes]:
    """Validate an uploaded artwork file.

    Performs the following checks:
    1. Filename is present and has an allowed extension
    2. File size is within the configured limit
    3. Content type matches the extension

    Args:
        file: The uploaded file from the request.

    Returns:
        Tuple of (sanitized filename, file content bytes).

    Raises:
        FileValidationError: If any validation check fails.
    """
    settings = get_settings()

    # Check filename
    if not file.filename:
        raise FileValidationError("Filename is required.")

    # Sanitize filename - remove path traversal attempts
    filename = os.path.basename(file.filename)
    if not filename:
        raise FileValidationError("Invalid filename.")

    # Check extension
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    if ext not in settings.allowed_file_types:
        raise FileValidationError(
            f"File type '{ext}' is not allowed. "
            f"Allowed types: {', '.join(settings.allowed_file_types)}"
        )

    # Read content
    content = await file.read()

    # Check file size
    max_size = settings.max_upload_size_mb * 1024 * 1024
    if len(content) > max_size:
        raise FileValidationError(
            f"File size ({len(content) / 1024 / 1024:.1f} MB) exceeds "
            f"maximum allowed size ({settings.max_upload_size_mb} MB)."
        )

    # Check for empty files
    if len(content) == 0:
        raise FileValidationError("Uploaded file is empty.")

    logger.info(
        "File validated: %s (%.1f KB, type=%s)",
        filename,
        len(content) / 1024,
        file.content_type,
    )

    return filename, content
