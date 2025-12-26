# syntax=docker/dockerfile:1

# Build frontend
FROM node:20-slim AS frontend-builder
WORKDIR /app/client
COPY client/package*.json ./
RUN npm ci
COPY client/ ./
RUN npm run build

# Build backend
FROM python:3.11-slim AS backend-builder

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock README.md ./

# Copy app directory for the package build
COPY app ./app

# Install dependencies using uv (production only, no dev/analysis deps)
RUN uv sync --frozen --no-dev

# Production stage
FROM python:3.11-slim AS production

# Install runtime dependencies for GCP Cloud SQL connector
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy uv from builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Create non-root user for security (GCP Cloud Run best practice)
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# Copy virtual environment from backend builder
COPY --from=backend-builder /app/.venv /app/.venv

# Copy application code
COPY --chown=appuser:appuser . .

# Copy frontend build from frontend builder
COPY --from=frontend-builder --chown=appuser:appuser /app/client/dist /app/static/client

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Switch to non-root user
USER appuser

# Expose port (Cloud Run uses 8080 by default)
EXPOSE 8080

# Health check for Cloud Run
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

# Run the application with uvicorn
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
