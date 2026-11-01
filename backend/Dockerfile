# Koyeb Production Dockerfile for Dynamic Job-Shop Scheduling System
FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8000

WORKDIR /app

# Install minimal OS runtime libraries for PyTorch and PostgreSQL
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY app/ /app/app/
COPY models/ /app/models/
COPY data/ /app/data/

# Create a non-root system user and adjust permissions
RUN useradd -m -u 1000 appuser && \
    mkdir -p /tmp/runtime_db && \
    chown -R appuser:appuser /app /tmp/runtime_db

USER appuser

# Healthcheck configuration using Python HTTP call
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{__import__(\"os\").environ.get(\"PORT\", 8000)}/api/health')" || exit 1

# Expose port and launch Uvicorn using the Koyeb-provided $PORT
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]

