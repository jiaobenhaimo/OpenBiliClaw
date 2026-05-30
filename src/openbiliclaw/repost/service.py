"""Orchestration for repost detection + replacement.

:class:`RepostService` owns the two direction-specific caches and wires
together detection → reachability → search → cache for each direction.
The two directions are fully separated: separate caches, separate
detectors, separate search backends, separate public methods.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from . import detect
from . import search as _search_mod
from .cache import MISS, RepostCache

logger = logging.getLogger(__name__)

_B2Y_CACHE_FILE = "repost_bili_to_yt.json"  # bvid -> youtube match
_Y2B_CACHE_FILE = "repost_yt_to_bili.json"  # yt id -> bilibili match
# The legacy single-file cache the old yt_replacer wrote. Removed on
# clear() so upgraders don't leave an orphan behind.
_LEGACY_CACHE_FILE = "yt_replacer_cache.json"


class RepostService:
    """Bidirectional repost linking with separated per-direction caches."""

    def __init__(self, data_dir: str = "", *, cache_ttl_hours: int = 24) -> None:
        base = Path(data_dir) if data_dir else (Path.cwd() / "data")
        self._data_dir = base
        ttl = max(0, int(cache_ttl_hours)) * 3600
        self._b2y = RepostCache(base / _B2Y_CACHE_FILE, ttl_seconds=ttl)
        self._y2b = RepostCache(base / _Y2B_CACHE_FILE, ttl_seconds=ttl)

    # ── Direction A: bilibili video → youtube original ────────────

    def link_bilibili_to_youtube(
        self,
        bvid: str,
        title: str,
        *,
        author: str = "",
        description: str = "",
        force: bool = False,
        skip_detection: bool = False,
        comments: list[str] | None = None,
        search: bool = True,
    ) -> dict[str, Any] | None:
        """Resolve a Bilibili repost to its YouTube original.

        Returns ``{bvid, yt_url, yt_title, yt_uploader, yt_cover_url}``
        on a confirmed match; a transient dict with
        ``repost_detected=True`` and empty ``yt_url`` when it's clearly
        a repost but YouTube isn't reachable right now; or ``None``.

        ``search=False`` is cache-only mode: return whatever is cached
        and otherwise ``None``, without running detection, the
        reachability probe, or the (blocking) YouTube search. The serve
        path uses this so a request never stalls on yt-dlp; a background
        pass (:meth:`warm_bilibili_to_youtube`) fills the cache.
        """
        cached = self._b2y.get(bvid) if not force else MISS
        if cached is not MISS:
            return cached  # may be None (cached no-match)

        if not search:
            # Cache-only: we don't know yet, and we won't block to find
            # out. The warming pass will populate this entry.
            return None

        if not skip_detection:
            signal = detect.detect_bilibili_from_youtube(
                title, description=description, comments=comments
            )
            if not signal:
                self._b2y.set(bvid, None)
                return None

        # Don't persist a no-match when the platform is simply
        # unreachable — that's transient, and the long-lived cache
        # would lock the bvid out for the full TTL.
        if not _search_mod.youtube_reachable():
            logger.info("link_bilibili_to_youtube: youtube unreachable for %s", bvid)
            return {
                "bvid": bvid,
                "yt_url": "",
                "yt_title": "",
                "yt_uploader": "",
                "yt_cover_url": "",
                "repost_detected": True,
            }

        match = _search_mod.find_youtube_original(
            title, author=author, description=description
        )
        if match is None:
            self._b2y.set(bvid, None)
            return None

        entry = {
            "bvid": bvid,
            "yt_url": match["url"],
            "yt_title": match["title"],
            "yt_uploader": match.get("uploader", ""),
            "yt_cover_url": match.get("cover_url", ""),
        }
        self._b2y.set(bvid, entry)
        logger.info("link_bilibili_to_youtube: %s -> %s", bvid, match["url"])
        return entry

    # ── Direction B: youtube video → bilibili original ────────────

    def link_youtube_to_bilibili(
        self,
        yt_id: str,
        title: str,
        *,
        author: str = "",
        description: str = "",
        force: bool = False,
        skip_detection: bool = False,
        comments: list[str] | None = None,
        search: bool = True,
    ) -> dict[str, Any] | None:
        """Resolve a YouTube repost to its Bilibili original.

        ``yt_id`` is the cache key (the YouTube video id, or any stable
        id the caller has). Returns
        ``{yt_id, bvid, bili_url, bili_title, bili_up_name, bili_cover_url}``
        on a confirmed match; a transient ``repost_detected=True`` dict
        when Bilibili is unreachable; or ``None``.

        ``search=False`` is cache-only mode (see
        :meth:`link_bilibili_to_youtube`).
        """
        cached = self._y2b.get(yt_id) if not force else MISS
        if cached is not MISS:
            return cached

        if not search:
            return None

        if not skip_detection:
            signal = detect.detect_youtube_from_bilibili(
                title, description=description, comments=comments
            )
            if not signal:
                self._y2b.set(yt_id, None)
                return None

        if not _search_mod.bilibili_reachable():
            logger.info("link_youtube_to_bilibili: bilibili unreachable for %s", yt_id)
            return {
                "yt_id": yt_id,
                "bvid": "",
                "bili_url": "",
                "bili_title": "",
                "bili_up_name": "",
                "bili_cover_url": "",
                "repost_detected": True,
            }

        match = _search_mod.find_bilibili_original(
            title, author=author, description=description
        )
        if match is None:
            self._y2b.set(yt_id, None)
            return None

        entry = {
            "yt_id": yt_id,
            "bvid": match["bvid"],
            "bili_url": match["url"],
            "bili_title": match["title"],
            "bili_up_name": match.get("up_name", ""),
            "bili_cover_url": match.get("cover_url", ""),
        }
        self._y2b.set(yt_id, entry)
        logger.info("link_youtube_to_bilibili: %s -> %s", yt_id, match["url"])
        return entry

    # ── Recommendation-row replacement (direction A only) ─────────

    def replace_recommendation_row(
        self,
        row: dict[str, Any],
        *,
        comments: list[str] | None = None,
        search: bool = True,
    ) -> dict[str, Any] | None:
        """Compute the field overrides to swap a Bilibili-sourced repost
        row for its YouTube original.

        Returns a dict of overrides (``content_url``, ``source_platform``,
        ``expression``, optionally ``cover_url``) or ``None`` if no
        replacement applies. Direction A only — the rec feed surfaces
        Bilibili-pool items, so the only automatic swap that makes sense
        here is bilibili→youtube.

        ``search=False`` applies only an already-cached replacement and
        never blocks on a lookup (used by the serve path).
        """
        bvid = str(row.get("bvid", "") or "")
        title = str(row.get("title", "") or "")
        author = str(row.get("up_name", "") or "")
        description = str(row.get("description", "") or "")
        source_platform = str(row.get("source_platform", "") or "")

        if source_platform == "youtube":
            return None
        if not bvid or not title:
            return None

        yt = self.link_bilibili_to_youtube(
            bvid,
            title,
            author=author,
            description=description,
            comments=comments,
            search=search,
        )
        if yt is None:
            return None

        original_expr = str(row.get("expression", "") or "")

        # Detected-but-no-URL (YouTube unreachable): annotate only.
        if yt.get("repost_detected") and not yt.get("yt_url"):
            suffix = "\n此视频疑似搬运内容"
            return {
                "expression": (original_expr + suffix) if original_expr else "此视频疑似搬运内容",
            }

        yt_url = yt["yt_url"]
        yt_cover = yt.get("yt_cover_url", "")
        if not yt_cover and "youtube.com/watch?v=" in yt_url:
            vid = text_find_yt(yt_url)
            if vid:
                yt_cover = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
        suffix = f"\n💡 这是搬运，原视频在 YouTube：{yt_url}"
        override: dict[str, Any] = {
            "content_url": yt_url,
            "source_platform": "youtube",
            "expression": (original_expr + suffix) if original_expr else f"原视频在 YouTube：{yt_url}",
        }
        if yt_cover:
            override["cover_url"] = yt_cover
        return override

    # ── background warming (the slow, search-enabled pass) ────────

    def warm_bilibili_to_youtube(
        self,
        rows: list[dict[str, Any]],
        *,
        comments_by_bvid: dict[str, list[str]] | None = None,
    ) -> dict[str, int]:
        """Populate the direction-A cache for a batch of rows.

        This is the slow counterpart to the cache-only serve path: it
        actually runs detection + (when reachable) the blocking YouTube
        search for each Bilibili row not already cached, and persists
        the result so a subsequent cache-only lookup is instant.

        BLOCKING — yt-dlp and urllib are synchronous. Call this from a
        worker thread (``asyncio.to_thread``), never directly on the
        event loop.

        Skips youtube-sourced rows and any bvid already in the cache
        (whether it cached a match or a no-match), so repeated calls
        only do new work. Returns ``{scanned, matched}`` for logging.
        """
        comments_by_bvid = comments_by_bvid or {}
        scanned = 0
        matched = 0
        for row in rows:
            bvid = str(row.get("bvid", "") or "")
            if not bvid:
                continue
            if str(row.get("source_platform", "") or "") == "youtube":
                continue
            if self._b2y.get(bvid) is not MISS:
                continue  # already resolved (match or no-match)
            scanned += 1
            result = self.link_bilibili_to_youtube(
                bvid,
                str(row.get("title", "") or ""),
                author=str(row.get("up_name", "") or ""),
                description=str(row.get("description", "") or ""),
                comments=comments_by_bvid.get(bvid),
                search=True,
            )
            if result and result.get("yt_url"):
                matched += 1
        if scanned:
            logger.info(
                "warm_bilibili_to_youtube: scanned=%d matched=%d", scanned, matched
            )
        return {"scanned": scanned, "matched": matched}

    # ── maintenance ───────────────────────────────────────────────

    def clear(self) -> None:
        """Clear both direction caches (and the legacy single-file cache)."""
        self._b2y.clear()
        self._y2b.clear()
        legacy = self._data_dir / _LEGACY_CACHE_FILE
        try:
            if legacy.exists():
                legacy.unlink()
        except OSError:
            logger.debug("RepostService: failed to remove legacy cache", exc_info=True)


def text_find_yt(url: str) -> str | None:
    """Local import shim to avoid a circular import at module load."""
    from . import text

    return text.find_youtube_id(url)
