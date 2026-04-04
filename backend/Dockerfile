FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . /app/backend/

# Create writable directories that the app may need at runtime
RUN mkdir -p /tmp/rendered

# Non-root user for security
RUN useradd -m appuser && chown -R appuser:appuser /app /tmp/rendered
USER appuser

# Health check — generous start-period so Fargate doesn't kill the task
# while Python is still loading heavy dependencies (Pillow, boto3, etc.)
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

# --log-level info ensures startup messages (including errors) reach CloudWatch
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
