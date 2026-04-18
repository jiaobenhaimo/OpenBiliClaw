# OpenBiliClaw XHS sidecar — isolated GPL-3.0 process for xhs note detail enrichment.
#
# This container embeds XHS-Downloader (https://github.com/JoeanAmier/XHS-Downloader)
# which is licensed under GPL-3.0. The container exposes only a minimal HTTP
# endpoint consumed by the main OpenBiliClaw backend; the main backend never
# imports or links to XHS-Downloader code.

FROM python:3.12-slim

ARG XHS_COMMIT=5f9bd542e3c0c2689e5ea4481b8726927da761c2

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /opt

# System deps required by lxml and by git clone
RUN apt-get update \
    && apt-get install -y --no-install-recommends git libxml2-dev libxslt1-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Pin XHS-Downloader to a known-good commit for reproducible builds
RUN git clone https://github.com/JoeanAmier/XHS-Downloader.git xhs-downloader \
    && cd xhs-downloader \
    && git checkout "${XHS_COMMIT}" \
    && rm -rf .git

WORKDIR /opt/xhs-downloader

# Install XHS-Downloader's pinned runtime deps
RUN pip install -r requirements.txt

# Install our thin wrapper's extra deps (most already satisfied by upstream)
COPY requirements.txt /opt/wrapper-requirements.txt
RUN pip install -r /opt/wrapper-requirements.txt

# Drop in the wrapper alongside the cloned package so `from source import XHS` works
COPY wrapper.py /opt/xhs-downloader/wrapper.py

# Non-root user
RUN groupadd -r xhs && useradd -r -g xhs -d /opt/xhs-downloader xhs \
    && chown -R xhs:xhs /opt/xhs-downloader
USER xhs

EXPOSE 5556

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5556/health', timeout=3).read()" || exit 1

CMD ["uvicorn", "wrapper:app", "--host", "0.0.0.0", "--port", "5556"]
