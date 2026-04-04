"""Minimal HTTP server – stdlib only, ZERO external dependencies.

This replaces FastAPI/uvicorn with Python's built-in http.server to
guarantee a successful ECS deployment. Once the infrastructure is
proven green, we can layer FastAPI back in.

Listens on port 8000 and responds to:
  GET /health  → 200 {"status": "healthy", ...}
  GET /         → 200 {"service": "decoration-preview-api", ...}
  Everything else → 404
"""

import json
import logging
import os
import sys
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

# ---------------------------------------------------------------------------
# Logging – immediate stdout so CloudWatch picks it up
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("api_server")

# ---------------------------------------------------------------------------
# Startup banner
# ---------------------------------------------------------------------------
logger.info("=" * 60)
logger.info("Minimal API server loading (stdlib http.server)")
logger.info("Python %s", sys.version)
logger.info("PID %s | CWD %s", os.getpid(), os.getcwd())
logger.info("ENVIRONMENT=%s", os.environ.get("ENVIRONMENT", "unknown"))
logger.info("=" * 60)

START_TIME = time.time()


class HealthHandler(BaseHTTPRequestHandler):
    """Dead-simple request handler."""

    def _send_json(self, code: int, body: dict) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        logger.info("GET %s from %s", self.path, self.client_address[0])

        if self.path == "/health":
            uptime = int(time.time() - START_TIME)
            self._send_json(200, {
                "status": "healthy",
                "version": "0.1.0-minimal",
                "environment": os.environ.get("ENVIRONMENT", "unknown"),
                "uptime_seconds": uptime,
            })
        elif self.path == "/":
            self._send_json(200, {
                "service": "decoration-preview-api",
                "version": "0.1.0-minimal",
                "description": "Minimal stdlib server – infrastructure validation mode",
                "health_url": "/health",
            })
        else:
            self._send_json(404, {"error": "not found", "path": self.path})

    # Suppress default stderr logging (we use our own logger)
    def log_message(self, format, *args):
        pass


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    logger.info("Listening on 0.0.0.0:%d", port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        server.server_close()
        logger.info("Server closed.")


if __name__ == "__main__":
    main()
