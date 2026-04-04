"""Minimal rendering worker – keep-alive stub.

This is a deliberately minimal version designed to guarantee a
successful ECS deployment.  It avoids ALL non-stdlib imports so
that import-time failures are impossible.

Once the deployment is confirmed healthy, functionality (SQS
polling, image processing, etc.) can be layered back in
incrementally.
"""

import logging
import os
import signal
import sys
import time

# ---------------------------------------------------------------------------
# Logging – stdlib only, no project imports
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("render_worker")

# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------
_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    logger.info("Received signal %s – initiating graceful shutdown", signum)
    _shutdown = True


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
HEARTBEAT_INTERVAL = int(os.environ.get("WORKER_HEARTBEAT_SECONDS", "30"))


def main() -> None:
    """Entry point for the render worker process."""
    logger.info("=" * 60)
    logger.info("Render worker starting (minimal keep-alive mode)")
    logger.info("Python %s", sys.version)
    logger.info("PID %s | CWD %s", os.getpid(), os.getcwd())
    logger.info("ENVIRONMENT=%s", os.environ.get("ENVIRONMENT", "unknown"))
    logger.info("WORKER_MODE=%s", os.environ.get("WORKER_MODE", "unset"))
    logger.info("Heartbeat interval: %s seconds", HEARTBEAT_INTERVAL)
    logger.info("=" * 60)

    heartbeat_count = 0
    while not _shutdown:
        try:
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
            time.sleep(5)  # small back-off then continue

    logger.info("Render worker stopped gracefully.")


if __name__ == "__main__":
    main()
