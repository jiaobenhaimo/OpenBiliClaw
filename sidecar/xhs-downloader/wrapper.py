"""Thin FastAPI wrapper around XHS-Downloader's `XHS.extract` for detail enrichment.

This wrapper is part of the OpenBiliClaw XHS sidecar. It runs in its own
container, imports XHS-Downloader, and exposes a single HTTP endpoint used by
the main OpenBiliClaw backend. No other code is shared with the main backend.

License: GPL-3.0 (derivative work of XHS-Downloader, see LICENSE).
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# XHS-Downloader is cloned into /opt/xhs-downloader by the Dockerfile and we
# run from that working directory, so `source` resolves to its package tree.
from source import XHS  # type: ignore[import-not-found]

logger = logging.getLogger("xhs-sidecar")
logging.basicConfig(
    level=os.environ.get("XHS_SIDECAR_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


_xhs_instance: XHS | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    """Keep a single XHS instance warm for the process lifetime."""
    global _xhs_instance
    _xhs_instance = XHS(
        download_record=False,
        record_data=False,
        image_download=False,
        video_download=False,
        live_download=False,
    )
    await _xhs_instance.__aenter__()
    logger.info("XHS sidecar ready")
    try:
        yield
    finally:
        if _xhs_instance is not None:
            await _xhs_instance.__aexit__(None, None, None)
            _xhs_instance = None


app = FastAPI(
    title="OpenBiliClaw XHS Sidecar",
    version="0.1.0",
    lifespan=lifespan,
)


class DetailRequest(BaseModel):
    url: str = Field(..., min_length=10, description="Full xhs note URL, including xsec_token if present.")


class DetailResponse(BaseModel):
    ok: bool
    data: dict[str, Any] | None = None
    error: str | None = None


@app.get("/health")
async def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/xhs/detail", response_model=DetailResponse)
async def xhs_detail(req: DetailRequest) -> DetailResponse:
    if _xhs_instance is None:
        raise HTTPException(status_code=503, detail="XHS instance not initialised")
    try:
        results = await _xhs_instance.extract(req.url, download=False)
    except Exception as exc:  # XHS-Downloader raises a mix of types; flatten
        logger.warning("extract failed for %s: %s", req.url, exc)
        return DetailResponse(ok=False, error=str(exc))

    # `extract` returns a list — a note URL can expand to multiple items when it
    # points to an album.  We pick the first for single-note enrichment.
    if not results:
        return DetailResponse(ok=False, error="no_data")

    item = results[0]
    if not isinstance(item, dict):
        return DetailResponse(ok=False, error="unexpected_response_shape")

    return DetailResponse(ok=True, data=item)
