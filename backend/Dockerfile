# Force AMD64 architecture for ECS Fargate compatibility
# (builds correctly even on Apple Silicon/ARM64 Macs)
FROM --platform=linux/amd64 python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt /app/backend/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Copy application code
COPY . /app/backend/

# Create writable directories that the app may need at runtime
RUN mkdir -p /tmp/rendered

# Non-root user for security
RUN useradd -m appuser && chown -R appuser:appuser /app /tmp/rendered
USER appuser

# Health check — generous start-period so Fargate doesn't kill the task
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

# Run FastAPI with Uvicorn
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
