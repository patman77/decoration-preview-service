"""Stubbed rendering worker.

Simulates 3D rendering by performing a simple 2D image overlay
using Pillow. In production, this would:
1. Pull the job from SQS
2. Download artwork from S3
3. Load the 3D element model
4. Apply the decoration using Blender (headless)
5. Render the scene from the specified camera angle
6. Upload the result to S3
7. Update job status in DynamoDB
8. Send completion notification via SNS

This stub demonstrates the async processing pattern and job
lifecycle management without requiring Blender or GPU resources.
"""

import asyncio
import io
import os
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from backend.app.core.logging import get_logger
from backend.app.models.schemas import RenderStatus
from backend.app.services.job_store import JobRecord, job_store

logger = get_logger(__name__)


def _get_render_output_dir() -> Path:
    """Return (and lazily create) the render output directory.

    Uses /tmp/rendered in containerised environments (always writable)
    and falls back to a ``rendered/`` directory relative to the
    working directory for local development.
    """
    # Prefer /tmp in containers – it is always writable regardless of
    # the user the process runs as or root-filesystem permissions.
    for candidate in (Path("/tmp/rendered"), Path("rendered")):
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except OSError as exc:
            logger.warning(
                "Could not create render output dir %s: %s", candidate, exc
            )
    # Ultimate fallback – use /tmp directly
    fallback = Path("/tmp")
    logger.warning("Using bare /tmp as render output directory")
    return fallback


# Lazily initialised on first use so that a directory-creation failure
# at module-import time does not prevent the API service from starting.
RENDER_OUTPUT_DIR: Path | None = None


def get_render_output_dir() -> Path:
    """Return the render output directory, initialising it on first call."""
    global RENDER_OUTPUT_DIR
    if RENDER_OUTPUT_DIR is None:
        RENDER_OUTPUT_DIR = _get_render_output_dir()
    return RENDER_OUTPUT_DIR


def _create_element_base(width: int, height: int, element_id: str) -> Image.Image:
    """Create a placeholder 3D element base image.

    In production, this loads the actual 3D model and renders it.
    Here we create a styled placeholder representing the element.

    Args:
        width: Image width.
        height: Image height.
        element_id: Element identifier for visual label.

    Returns:
        Base image representing the 3D element.
    """
    img = Image.new("RGBA", (width, height), (240, 240, 245, 255))
    draw = ImageDraw.Draw(img)

    # Draw a stylized element shape based on category
    cx, cy = width // 2, height // 2
    margin = min(width, height) // 8

    if "torso" in element_id:
        # Torso shape - trapezoid
        points = [
            (cx - margin * 2, cy - margin * 3),
            (cx + margin * 2, cy - margin * 3),
            (cx + margin * 3, cy + margin * 3),
            (cx - margin * 3, cy + margin * 3),
        ]
        draw.polygon(points, fill=(255, 220, 100, 255), outline=(200, 170, 50, 255), width=3)
    elif "head" in element_id:
        # Head shape - circle
        r = margin * 2
        draw.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            fill=(255, 220, 100, 255),
            outline=(200, 170, 50, 255),
            width=3,
        )
    elif "brick" in element_id:
        # Brick shape - rectangle with studs
        draw.rectangle(
            [cx - margin * 3, cy - margin * 1.5, cx + margin * 3, cy + margin * 1.5],
            fill=(200, 50, 50, 255),
            outline=(150, 30, 30, 255),
            width=3,
        )
        # Studs on top
        for i in range(4):
            sx = cx - margin * 2.5 + i * margin * 1.7
            draw.ellipse(
                [sx - 12, cy - margin * 1.5 - 20, sx + 12, cy - margin * 1.5],
                fill=(220, 60, 60, 255),
                outline=(150, 30, 30, 255),
                width=2,
            )
    elif "tile" in element_id:
        # Tile - flat rectangle
        draw.rectangle(
            [cx - margin * 2, cy - margin * 2, cx + margin * 2, cy + margin * 2],
            fill=(50, 150, 220, 255),
            outline=(30, 120, 190, 255),
            width=3,
        )
    elif "shield" in element_id:
        # Shield shape
        points = [
            (cx, cy - margin * 3),
            (cx + margin * 2.5, cy - margin),
            (cx + margin * 2, cy + margin * 2),
            (cx, cy + margin * 3),
            (cx - margin * 2, cy + margin * 2),
            (cx - margin * 2.5, cy - margin),
        ]
        draw.polygon(points, fill=(180, 180, 190, 255), outline=(100, 100, 110, 255), width=3)
    else:
        # Generic element - rounded rectangle
        draw.rounded_rectangle(
            [cx - margin * 2, cy - margin * 2, cx + margin * 2, cy + margin * 2],
            radius=20,
            fill=(100, 200, 100, 255),
            outline=(60, 160, 60, 255),
            width=3,
        )

    # Add label
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except (OSError, IOError):
        font = ImageFont.load_default()

    label = f"3D Element: {element_id}"
    draw.text((10, height - 30), label, fill=(100, 100, 100, 200), font=font)

    return img


def _overlay_artwork(
    base: Image.Image,
    artwork_bytes: bytes,
    element_id: str,
) -> Image.Image:
    """Overlay 2D artwork onto the element base image.

    In production, this is where Blender applies the UV-mapped
    texture to the 3D model surface. Here we simulate it with
    a simple alpha composite.

    Args:
        base: Base element image.
        artwork_bytes: Raw artwork file bytes.
        element_id: Element ID (to determine placement).

    Returns:
        Composited image with artwork applied.
    """
    try:
        artwork = Image.open(io.BytesIO(artwork_bytes)).convert("RGBA")
    except Exception as e:
        logger.warning("Could not open artwork image, using placeholder: %s", e)
        artwork = Image.new("RGBA", (200, 200), (255, 0, 100, 180))
        draw = ImageDraw.Draw(artwork)
        draw.text((10, 90), "Artwork", fill=(255, 255, 255, 255))

    # Scale artwork to fit decoration zone (approx 40% of element area)
    zone_w = int(base.width * 0.4)
    zone_h = int(base.height * 0.4)
    artwork = artwork.resize((zone_w, zone_h), Image.Resampling.LANCZOS)

    # Center the artwork on the element
    paste_x = (base.width - zone_w) // 2
    paste_y = (base.height - zone_h) // 2

    # Composite with transparency
    result = base.copy()
    result.paste(artwork, (paste_x, paste_y), artwork)

    return result


def _add_watermark(image: Image.Image) -> Image.Image:
    """Add a preview watermark to the rendered image."""
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
    except (OSError, IOError):
        font = ImageFont.load_default()

    draw.text(
        (10, 10),
        "PREVIEW",
        fill=(200, 200, 200, 128),
        font=font,
    )
    return image


async def process_render_job(
    job_id: str,
    artwork_content: bytes,
) -> None:
    """Process a render job asynchronously.

    This simulates the full rendering pipeline:
    1. Update status to PROCESSING
    2. Create element base image
    3. Overlay artwork
    4. Apply watermark
    5. Save output
    6. Update status to COMPLETED

    Args:
        job_id: The render job ID.
        artwork_content: Raw artwork file bytes.
    """
    try:
        job = job_store.get_job(job_id)

        # Step 1: Mark as processing
        job_store.update_status(job_id, RenderStatus.PROCESSING, progress_percent=10)
        logger.info("Starting render for job %s", job_id)

        # Simulate processing delay (represents Blender rendering time)
        await asyncio.sleep(1)
        job_store.update_status(job_id, RenderStatus.PROCESSING, progress_percent=30)

        # Step 2: Create base element image
        base_image = _create_element_base(
            job.resolution_width, job.resolution_height, job.element_id
        )
        job_store.update_status(job_id, RenderStatus.PROCESSING, progress_percent=50)

        await asyncio.sleep(0.5)

        # Step 3: Overlay artwork
        result = _overlay_artwork(base_image, artwork_content, job.element_id)
        job_store.update_status(job_id, RenderStatus.PROCESSING, progress_percent=70)

        await asyncio.sleep(0.5)

        # Step 4: Add watermark
        result = _add_watermark(result)
        job_store.update_status(job_id, RenderStatus.PROCESSING, progress_percent=90)

        # Step 5: Save output
        output_format = job.output_format.upper()
        if output_format == "JPEG":
            # JPEG doesn't support RGBA
            result = result.convert("RGB")

        output_filename = f"{job_id}.{job.output_format}"
        output_path = get_render_output_dir() / output_filename

        save_kwargs = {}
        if output_format == "PNG":
            save_kwargs["optimize"] = True
        elif output_format == "JPEG":
            save_kwargs["quality"] = 90
        elif output_format == "WEBP":
            save_kwargs["quality"] = 90

        pil_format = "PNG" if output_format == "PNG" else output_format
        result.save(str(output_path), format=pil_format, **save_kwargs)

        file_size = output_path.stat().st_size

        # Also create thumbnail
        thumbnail = result.copy()
        thumbnail.thumbnail((256, 256), Image.Resampling.LANCZOS)
        thumb_filename = f"{job_id}_thumb.{job.output_format}"
        thumb_path = get_render_output_dir() / thumb_filename
        thumbnail.save(str(thumb_path), format=pil_format, **save_kwargs)

        # Step 6: Update status to completed
        job_store.update_status(
            job_id,
            RenderStatus.COMPLETED,
            progress_percent=100,
            preview_path=str(output_path),
            thumbnail_path=str(thumb_path),
            file_size_bytes=file_size,
        )

        logger.info(
            "Render completed for job %s: %s (%.1f KB)",
            job_id, output_filename, file_size / 1024,
        )

    except Exception as e:
        logger.error("Render failed for job %s: %s", job_id, str(e), exc_info=True)
        try:
            job_store.update_status(
                job_id,
                RenderStatus.FAILED,
                progress_percent=0,
                error_message=str(e),
            )
        except Exception:
            logger.error("Failed to update job status for %s", job_id)


async def _poll_sqs_queue() -> None:
    """Long-running SQS queue poller for render worker mode.

    In production, this continuously polls the SQS render queue for
    new jobs. For the current stubbed version, it runs an idle loop
    to keep the container alive and ready to process jobs.

    The actual SQS integration would:
    1. Receive messages from the render queue
    2. Parse the job payload
    3. Download artwork from S3
    4. Call process_render_job()
    5. Delete the message on success
    6. Let it return to queue on failure (dead-letter queue handles retries)
    """
    import signal
    import sys

    shutdown = False

    def handle_signal(signum, frame):
        nonlocal shutdown
        logger.info("Received signal %s, shutting down gracefully...", signum)
        shutdown = True

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    logger.info("Render worker started, polling for jobs...")

    while not shutdown:
        try:
            # In production: poll SQS queue
            # messages = sqs_client.receive_message(
            #     QueueUrl=os.environ.get("RENDER_QUEUE_URL"),
            #     MaxNumberOfMessages=1,
            #     WaitTimeSeconds=20,  # Long polling
            # )
            # For now, just wait (long-poll simulation)
            await asyncio.sleep(20)
            logger.debug("Render worker heartbeat - waiting for jobs...")
        except asyncio.CancelledError:
            logger.info("Worker task cancelled, shutting down...")
            break
        except Exception as e:
            logger.error("Error in worker poll loop: %s", e, exc_info=True)
            await asyncio.sleep(5)  # Back off on errors

    logger.info("Render worker stopped.")


def main() -> None:
    """Entry point for the render worker process."""
    import sys

    from backend.app.core.logging import setup_logging

    setup_logging()
    setup_logger = get_logger("worker.main")
    setup_logger.info("Initializing render worker process...")
    try:
        asyncio.run(_poll_sqs_queue())
    except KeyboardInterrupt:
        setup_logger.info("Worker interrupted, exiting.")
    except Exception as e:
        setup_logger.error("Worker crashed: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
