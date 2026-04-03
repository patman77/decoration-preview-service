"""Structured logging configuration.

Provides JSON-formatted logs suitable for CloudWatch ingestion
and centralized log aggregation.
"""

import logging
import sys
from typing import Optional

from backend.app.core.config import get_settings


def setup_logging(level: Optional[str] = None) -> logging.Logger:
    """Configure application-wide structured logging.

    Args:
        level: Override log level. Defaults to settings.log_level.

    Returns:
        Configured root logger instance.
    """
    settings = get_settings()
    log_level = level or settings.log_level

    # Configure root logger
    logger = logging.getLogger("decoration_preview")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Prevent duplicate handlers on reload
    if logger.handlers:
        logger.handlers.clear()

    # Console handler with structured format
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a child logger with the given name.

    Args:
        name: Logger name, typically __name__ of the calling module.

    Returns:
        Child logger instance.
    """
    return logging.getLogger(f"decoration_preview.{name}")
