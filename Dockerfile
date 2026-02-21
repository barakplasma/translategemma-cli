# ---------------------------------------------------------------------------
# TranslateGemma Web UI – Docker image
#
# Build (CPU):
#   docker build -t translategemma:latest .
#
# Build (CUDA):
#   docker build --build-arg BASE_IMAGE=nvidia/cuda:12.1.0-runtime-ubuntu22.04 \
#                --build-arg EXTRAS=cuda -t translategemma:cuda .
#
# Run:
#   docker run -p 8080:8080 \
#     -v /path/to/models:/root/.cache/translate \
#     translategemma:latest
#
# Offline / air-gapped usage:
#   1. Save the image:  docker save translategemma:latest | gzip > translategemma.tar.gz
#   2. Load elsewhere:  docker load < translategemma.tar.gz
#   3. Run as above (models volume must be pre-populated).
# ---------------------------------------------------------------------------

ARG BASE_IMAGE=python:3.11-slim
FROM ${BASE_IMAGE}

# Python extras to install (cpu | cuda | mlx)
ARG EXTRAS=cpu

LABEL org.opencontainers.image.title="TranslateGemma Web UI" \
      org.opencontainers.image.description="Offline-capable neural translation web interface" \
      org.opencontainers.image.version="0.1.0"

# Install OS-level build tools and clean up in one layer
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential \
      curl \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only the dependency manifests first so Docker can cache pip installs
COPY requirements-${EXTRAS}.txt ./requirements-platform.txt
COPY requirements-dev.txt ./requirements-dev.txt

# Install platform dependencies
RUN pip install --no-cache-dir -r requirements-platform.txt

# Install web-server dependencies
RUN pip install --no-cache-dir \
      "fastapi>=0.100.0,<1.0" \
      "uvicorn[standard]>=0.23.0,<1.0" \
      "python-multipart>=0.0.6"

# Copy source last so code changes don't bust the dependency cache
COPY . .

# Install the package itself (editable for easier debugging)
RUN pip install --no-cache-dir -e ".[${EXTRAS}]"

# Pre-create runtime directories
RUN mkdir -p /root/.cache/translate /root/.config/translate

# Expose the web-UI port
EXPOSE 8080

# Health-check so orchestrators know when the container is ready
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -f http://localhost:8080/api/health || exit 1

# Environment defaults (overridable at runtime)
ENV TRANSLATEGEMMA_HOST=0.0.0.0 \
    TRANSLATEGEMMA_PORT=8080 \
    TOKENIZERS_PARALLELISM=false \
    TRANSFORMERS_VERBOSITY=error

CMD ["python", "-m", "translategemma_cli.web"]
