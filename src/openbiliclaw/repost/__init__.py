"""Bidirectional repost detection & linking.

Two directions, fully separated (separate caches, separate detectors,
separate search backends):

  A. bilibili video that re-uploads a YouTube original
     → :func:`link_bilibili_to_youtube`
  B. youtube video that re-uploads a Bilibili original
     → :func:`link_youtube_to_bilibili`

The class-based entry point is :class:`RepostService`. The module-level
functions below are thin wrappers kept for the existing call sites
(they were previously in ``openbiliclaw.yt_replacer``); they share a
per-``data_dir`` service instance so the caches persist across calls.
"""

from __future__ import annotations

from typing import Any

from .detect import (
    RepostSignal,
    detect_bilibili_from_youtube,
    detect_youtube_from_bilibili,
)
from .service import RepostService

__all__ = [
    "RepostService",
    "RepostSignal",
    "detect_bilibili_from_youtube",
    "detect_youtube_from_bilibili",
    # backward-compatible function API
    "is_likely_repost",
    "is_likely_bilibili_origin",
    "replace_if_foreign",
    "replace_if_from_bilibili",
    "replace_recommendation_row",
    "warm_recommendation_reposts",
    "clear_cache",
]

# ── per-data_dir service cache ─────────────────────────────────────
_services: dict[str, RepostService] = {}


def _service(data_dir: str = "", *, cache_ttl_hours: int = 24) -> RepostService:
    key = data_dir or "<cwd>"
    svc = _services.get(key)
    if svc is None:
        svc = RepostService(data_dir, cache_ttl_hours=cache_ttl_hours)
        _services[key] = svc
    return svc


# ── detection (pure, no cache) ─────────────────────────────────────


def is_likely_repost(
    title: str, description: str = "", comments: list[str] | None = None
) -> bool:
    """Direction A detector: is this Bilibili video a YouTube repost?"""
    return bool(
        detect_bilibili_from_youtube(title, description=description, comments=comments)
    )


def is_likely_bilibili_origin(
    title: str, description: str = "", comments: list[str] | None = None
) -> bool:
    """Direction B detector: is this YouTube video a Bilibili repost?"""
    return bool(
        detect_youtube_from_bilibili(title, description=description, comments=comments)
    )


# ── direction A wrappers (bilibili → youtube) ──────────────────────


def replace_if_foreign(
    bvid: str,
    title: str,
    author: str = "",
    description: str = "",
    *,
    data_dir: str = "",
    force: bool = False,
    skip_detection: bool = False,
    comments: list[str] | None = None,
) -> dict[str, Any] | None:
    """Backward-compatible alias for direction A.

    Returns the same shape the old ``yt_replacer.replace_if_foreign``
    did: ``{bvid, yt_url, yt_title, yt_uploader, yt_cover_url}`` (plus
    ``repost_detected`` on the transient-unreachable path), or ``None``.
    """
    return _service(data_dir).link_bilibili_to_youtube(
        bvid,
        title,
        author=author,
        description=description,
        force=force,
        skip_detection=skip_detection,
        comments=comments,
    )


# ── direction B wrappers (youtube → bilibili) ──────────────────────


def replace_if_from_bilibili(
    yt_id: str,
    title: str,
    author: str = "",
    description: str = "",
    *,
    data_dir: str = "",
    force: bool = False,
    skip_detection: bool = False,
    comments: list[str] | None = None,
) -> dict[str, Any] | None:
    """Backward-compatible alias for direction B.

    The old signature took the bilibili-side ``bvid`` as the first
    positional arg even for the YouTube→Bilibili direction (the caller
    used the content_cache row's bvid as a stable key). We keep that
    convention: the first arg is just the cache key.

    Returns ``{bvid, url, title, up_name, cover_url}`` to match what the
    old function returned (mapped from the service's richer dict).
    """
    result = _service(data_dir).link_youtube_to_bilibili(
        yt_id,
        title,
        author=author,
        description=description,
        force=force,
        skip_detection=skip_detection,
        comments=comments,
    )
    if result is None:
        return None
    if result.get("repost_detected") and not result.get("bili_url"):
        # Preserve the transient signal in the old-style shape.
        return {
            "bvid": "",
            "url": "",
            "title": "",
            "up_name": "",
            "cover_url": "",
            "repost_detected": True,
        }
    return {
        "bvid": result.get("bvid", ""),
        "url": result.get("bili_url", ""),
        "title": result.get("bili_title", ""),
        "up_name": result.get("bili_up_name", ""),
        "cover_url": result.get("bili_cover_url", ""),
    }


# ── orchestration + maintenance ────────────────────────────────────


def replace_recommendation_row(
    row: dict[str, Any],
    *,
    data_dir: str = "",
    comments: list[str] | None = None,
    search: bool = True,
) -> dict[str, Any] | None:
    """Direction-A recommendation-row override.

    ``search=False`` applies only an already-cached replacement (used
    by the serve path so a request never blocks on a YouTube lookup).
    """
    return _service(data_dir).replace_recommendation_row(
        row, comments=comments, search=search
    )


def warm_recommendation_reposts(
    rows: list[dict[str, Any]],
    *,
    data_dir: str = "",
    comments_by_bvid: dict[str, list[str]] | None = None,
) -> dict[str, int]:
    """Background warming for direction A (bilibili → youtube).

    Runs the actual (blocking) searches for uncached rows and persists
    results into the SAME per-``data_dir`` cache the cache-only serve
    path reads. BLOCKING — call via ``asyncio.to_thread`` off the event
    loop. Returns ``{scanned, matched}``.
    """
    return _service(data_dir).warm_bilibili_to_youtube(
        rows, comments_by_bvid=comments_by_bvid
    )


def clear_cache(data_dir: str = "") -> None:
    """Clear both direction caches for *data_dir* (and the legacy file)."""
    _service(data_dir).clear()
    # Drop the cached service so a subsequent call rebuilds clean caches.
    _services.pop(data_dir or "<cwd>", None)
