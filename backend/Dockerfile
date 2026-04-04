FROM python:3.11-slim

WORKDIR /app

# Install only curl (needed for health check) – no other system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# NO pip install – we use ZERO external Python packages
# Copy application code
COPY . /app/backend/

# Create writable directories that the app may need at runtime
RUN mkdir -p /tmp/rendered

# Non-root user for security
RUN useradd -m appuser && chown -R appuser:appuser /app /tmp/rendered
USER appuser

# Health check — generous start-period so Fargate doesn't kill the task
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

# Run the minimal stdlib HTTP server directly
CMD ["python", "-m", "backend.app.main"]
