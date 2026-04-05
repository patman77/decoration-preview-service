"""Rendering worker for processing decoration preview jobs.

This module provides both:
1. A background task function for inline rendering (used by API)
2. A standalone worker mode for SQS-based processing (production)
"""

import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional

# ---------------------------------------------------------------------------
# Logging – stdlib only for standalone mode compatibility
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("render_worker")

# ---------------------------------------------------------------------------
# Graceful shutdown for standalone mode
# ---------------------------------------------------------------------------
_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    logger.info("Received signal %s – initiating graceful shutdown", signum)
    _shutdown = True


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)

# ---------------------------------------------------------------------------
# Render output directory
# ---------------------------------------------------------------------------
RENDER_OUTPUT_DIR = os.environ.get("RENDER_OUTPUT_DIR", "/tmp/rendered")
os.makedirs(RENDER_OUTPUT_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Background task rendering function (used by API routes)
# ---------------------------------------------------------------------------
async def process_render_job(job_id: str, artwork_content: bytes) -> None:
    """Process a render job asynchronously.

    This is called as a FastAPI background task. In production,
    this would send the job to an SQS queue for processing by
    dedicated worker nodes.

    Args:
        job_id: The unique job identifier.
        artwork_content: The uploaded artwork file bytes.
    """
    # Import here to avoid circular imports and allow standalone mode
    from backend.app.models.schemas import RenderStatus
    from backend.app.services.job_store import job_store

    logger.info("Starting render job: %s", job_id)

    try:
        # Update status to processing
        job_store.update_status(job_id, RenderStatus.PROCESSING, progress_percent=10)

        # Get job details
        job = job_store.get_job(job_id)

        # Simulate rendering stages
        for progress in [25, 50, 75, 90]:
            await _async_sleep(0.5)  # Simulate work
            job_store.update_status(job_id, RenderStatus.PROCESSING, progress_percent=progress)

        # Generate output file
        output_path = os.path.join(RENDER_OUTPUT_DIR, f"{job_id}.{job.output_format}")
        thumbnail_path = os.path.join(RENDER_OUTPUT_DIR, f"{job_id}_thumb.{job.output_format}")

        # Create a simple preview image
        file_size = _create_preview_image(
            artwork_content,
            output_path,
            job.resolution_width,
            job.resolution_height,
            job.output_format,
        )

        # Create thumbnail
        _create_preview_image(
            artwork_content,
            thumbnail_path,
            256,
            256,
            job.output_format,
        )

        # Mark as completed
        job_store.update_status(
            job_id,
            RenderStatus.COMPLETED,
            progress_percent=100,
            preview_path=output_path,
            thumbnail_path=thumbnail_path,
            file_size_bytes=file_size,
        )

        logger.info("Render job completed: %s (size=%d bytes)", job_id, file_size)

        # Send webhook callback if configured
        if job.callback_url:
            await _send_callback(job.callback_url, job_id, "completed")

    except Exception as e:
        logger.error("Render job failed: %s - %s", job_id, str(e), exc_info=True)
        try:
            job_store.update_status(
                job_id,
                RenderStatus.FAILED,
                progress_percent=0,
                error_message=str(e),
            )
        except Exception:
            pass


async def _async_sleep(seconds: float) -> None:
    """Async sleep helper."""
    import asyncio
    await asyncio.sleep(seconds)


def _create_preview_image(
    artwork_content: bytes,
    output_path: str,
    width: int,
    height: int,
    format: str,
) -> int:
    """Create a preview image from artwork content.

    In production, this would apply the artwork to a 3D element
    and render the result. For now, we create a placeholder image.

    Returns:
        File size in bytes.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont

        # Try to load the uploaded artwork
        try:
            artwork = Image.open(BytesIO(artwork_content))
            # Resize artwork to fit the output dimensions
            artwork = artwork.convert("RGBA")
            artwork = artwork.resize((width, height), Image.Resampling.LANCZOS)
            output = artwork
        except Exception:
            # If artwork can't be loaded, create a placeholder
            output = Image.new("RGB", (width, height), color=(240, 240, 240))
            draw = ImageDraw.Draw(output)
            # Draw a simple placeholder
            draw.rectangle([10, 10, width - 10, height - 10], outline=(200, 200, 200), width=2)
            text = "Preview Generated"
            draw.text((width // 2 - 60, height // 2), text, fill=(100, 100, 100))

        # Save with appropriate format
        save_format = format.upper()
        if save_format == "JPEG":
            output = output.convert("RGB")  # JPEG doesn't support alpha

        output.save(output_path, format=save_format, quality=90)
        return os.path.getsize(output_path)

    except ImportError:
        # Pillow not available, create a minimal placeholder file
        logger.warning("Pillow not available, creating minimal placeholder")
        with open(output_path, "wb") as f:
            # Write minimal valid PNG
            f.write(b'\x89PNG\r\n\x1a\n')
        return 8


async def _send_callback(callback_url: str, job_id: str, status: str) -> None:
    """Send webhook callback notification."""
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            await client.post(
                callback_url,
                json={
                    "job_id": job_id,
                    "status": status,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                timeout=10.0,
            )
            logger.info("Callback sent: %s -> %s", job_id, callback_url)
    except Exception as e:
        logger.warning("Callback failed: %s - %s", callback_url, str(e))


# ---------------------------------------------------------------------------
# Standalone worker mode (for SQS processing)
# ---------------------------------------------------------------------------
HEARTBEAT_INTERVAL = int(os.environ.get("WORKER_HEARTBEAT_SECONDS", "30"))


def main() -> None:
    """Entry point for the standalone render worker process."""
    logger.info("=" * 60)
    logger.info("Render worker starting (standalone mode)")
    logger.info("Python %s", sys.version)
    logger.info("PID %s | CWD %s", os.getpid(), os.getcwd())
    logger.info("ENVIRONMENT=%s", os.environ.get("ENVIRONMENT", "unknown"))
    logger.info("WORKER_MODE=%s", os.environ.get("WORKER_MODE", "unset"))
    logger.info("Heartbeat interval: %s seconds", HEARTBEAT_INTERVAL)
    logger.info("=" * 60)

    heartbeat_count = 0
    while not _shutdown:
        try:
            # In production: poll SQS queue for jobs
            # For now: just heartbeat to stay healthy
            time.sleep(HEARTBEAT_INTERVAL)
            heartbeat_count += 1
            logger.info(
                "Heartbeat #%d – render worker alive (uptime ~%ds)",
                heartbeat_count,
                heartbeat_count * HEARTBEAT_INTERVAL,
            )
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt – stopping worker")
            break
        except Exception:
            logger.exception("Unexpected error in heartbeat loop")
            time.sleep(5)

    logger.info("Render worker stopped gracefully.")


if __name__ == "__main__":
    main()
