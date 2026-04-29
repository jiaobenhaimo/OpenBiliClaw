# Multi-arch image: python:3.11-slim is published on Docker Hub for
# linux/amd64, linux/arm64, linux/arm/v7, linux/386 and others, so this
# Dockerfile builds the OpenBiliClaw backend on Intel Macs, Apple Silicon
# (M1/M2/M3), x86_64 Linux, ARM Linux (Raspberry Pi 4/5), and Windows
# with Docker Desktop (which runs linux containers via WSL2 by default).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md config.example.toml ./
COPY src ./src

RUN pip install .

EXPOSE 8420

# Healthcheck via Python stdlib so we don't bloat the image with curl.
# Hits /api/health every 30s after a 20s warmup. Docker / Compose use
# this to report whether the backend is actually ready, not just running.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8420/api/health', timeout=4).status == 200 else 1)" \
    || exit 1

CMD ["python", "-m", "openbiliclaw.docker_runtime", "openbiliclaw", "serve-api", "--host", "0.0.0.0", "--port", "8420"]
