# =============================================================================
# Creonnect Backend — Production Dockerfile
# =============================================================================
# Multi-stage build: keeps the final image lean by separating build deps
# from the runtime image.
#
# Build:   docker build -t creonnect-backend .
# Run:     docker run -p 8000:8000 --env-file backend/.env creonnect-backend
# =============================================================================

# ── Stage 1: Builder ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

# Prevent .pyc files and enable unbuffered output for cleaner logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system build dependencies (needed for psycopg2, numpy, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies first (Docker layer cache optimisation)
COPY requirements.txt ./
COPY backend/requirements.txt ./backend/requirements.txt

RUN pip install --upgrade pip && \
    pip install --prefix=/install -r requirements.txt && \
    pip install --prefix=/install -r backend/requirements.txt


# ── Stage 2: Runtime ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install only runtime system libraries (no compilers)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed packages from the builder stage
COPY --from=builder /install /usr/local

# Copy application source code
COPY . .

# Create a non-root user for security
RUN addgroup --system --gid 1001 appgroup && \
    adduser --system --uid 1001 --ingroup appgroup --no-create-home appuser && \
    chown -R appuser:appgroup /app

USER appuser

# Expose the FastAPI application port
EXPOSE 8000

# Health check — polls the /health endpoint every 30 seconds
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Entrypoint: run the FastAPI app via uvicorn
# Workers: 2 (suitable for a t3.small/Fargate task; scale via ECS desired count)
CMD ["python", "-m", "uvicorn", "backend.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--log-level", "info"]
