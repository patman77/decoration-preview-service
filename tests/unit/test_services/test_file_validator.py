"""Tests for file upload validation."""

import io

import pytest
from fastapi import UploadFile

from backend.app.core.exceptions import FileValidationError
from backend.app.services.file_validator import validate_upload


def _make_upload_file(
    filename: str,
    content: bytes,
    content_type: str = "image/png",
) -> UploadFile:
    """Helper to create an UploadFile for testing."""
    return UploadFile(
        filename=filename,
        file=io.BytesIO(content),
        headers={"content-type": content_type},
    )


class TestFileValidator:
    """Test file upload validation."""

    @pytest.mark.asyncio
    async def test_valid_png_file(self):
        """Accept valid PNG file."""
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGBA", (10, 10)).save(buf, format="PNG")
        content = buf.getvalue()

        file = _make_upload_file("artwork.png", content)
        filename, data = await validate_upload(file)
        assert filename == "artwork.png"
        assert len(data) > 0

    @pytest.mark.asyncio
    async def test_valid_jpeg_file(self):
        """Accept valid JPEG file."""
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (10, 10)).save(buf, format="JPEG")
        content = buf.getvalue()

        file = _make_upload_file("artwork.jpg", content, "image/jpeg")
        filename, data = await validate_upload(file)
        assert filename == "artwork.jpg"

    @pytest.mark.asyncio
    async def test_reject_disallowed_extension(self):
        """Reject files with disallowed extensions."""
        file = _make_upload_file("malware.exe", b"fake content", "application/octet-stream")
        with pytest.raises(FileValidationError, match="not allowed"):
            await validate_upload(file)

    @pytest.mark.asyncio
    async def test_reject_empty_file(self):
        """Reject empty files."""
        file = _make_upload_file("empty.png", b"")
        with pytest.raises(FileValidationError, match="empty"):
            await validate_upload(file)

    @pytest.mark.asyncio
    async def test_reject_no_filename(self):
        """Reject uploads without filename."""
        file = _make_upload_file("", b"content")
        with pytest.raises(FileValidationError):
            await validate_upload(file)

    @pytest.mark.asyncio
    async def test_sanitize_path_traversal(self):
        """Sanitize filenames with path traversal."""
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGBA", (10, 10)).save(buf, format="PNG")
        content = buf.getvalue()

        file = _make_upload_file("../../etc/passwd.png", content)
        filename, _ = await validate_upload(file)
        assert filename == "passwd.png"
        assert "/" not in filename
        assert ".." not in filename
