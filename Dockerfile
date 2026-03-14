FROM python:3.13-slim AS base

# Prevent Python from writing .pyc and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies for asyncpg and psycopg2
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy everything needed for the package install
COPY pyproject.toml README.md ./
COPY src/ src/

# Install the package and all dependencies
RUN uv pip install --system hatchling && \
    uv pip install --system ".[dev]"

# Copy Alembic files
COPY alembic.ini ./
COPY alembic/ alembic/

# Expose FastAPI port
EXPOSE 8000

# Default: run the main application
CMD ["python", "-m", "copypoly.main"]
