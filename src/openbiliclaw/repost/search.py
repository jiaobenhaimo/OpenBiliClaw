"""Cross-platform search for finding a repost's original.

Two searchers (YouTube via yt-dlp, Bilibili via its web search API) and
two ``find_*_original`` scorers that rank results by title similarity.
Network-touching, but each network call is isolated in a small function
so tests can monkeypatch ``_search_youtube`` / ``_search_bilibili``.
"""

from __future__ import annotations

import json
import logging
import socket
import time
import urllib.parse
import urllib.request
from typing import Any

from . import text

logger = logging.getLogger(__name__)

# Per-host reachability cache: host -> (reachable, checked_at).
_reach_cache: dict[str, tuple[bool, float]] = {}
_REACH_TTL = 300.0  # 5 min


def host_reachable(host: str, *, port: int = 443, timeout: float = 3.0) -> bool:
    """Best-effort TCP reachability check for *host*, cached 5 minutes.

    Used to skip an expensive search when the target platform clearly
    isn't reachable from this server (e.g. YouTube from inside mainland
    China without a tunnel). The result is cached briefly so a transient
    blip doesn't get baked into the long-lived lookup cache.
    """
    now = time.time()
    cached = _reach_cache.get(host)
    if cached is not None and (now - cached[1]) < _REACH_TTL:
        return cached[0]
    reachable = False
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        reachable = True
    except OSError:
        reachable = False
    _reach_cache[host] = (reachable, now)
    logger.debug("reachability: %s -> %s", host, reachable)
    return reachable


def youtube_reachable() -> bool:
    """Reachability proxy for YouTube.

    Probes ``google.com`` rather than ``youtube.com`` deliberately: in
    regions where YouTube is blocked google is usually blocked too, and
    google's endpoint is more stable to probe than YouTube's CDN. This
    is a heuristic — it can be wrong at the margins (google reachable
    but YouTube not, or vice-versa) — but it's only used to avoid a
    pointless yt-dlp invocation, never to make a correctness decision.
    """
    return host_reachable("google.com")


def bilibili_reachable() -> bool:
    return host_reachable("api.bilibili.com")


# ── YouTube search (direction A: find the YouTube original) ────────


def _search_youtube(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Search YouTube via yt-dlp; return raw flat entries."""
    import yt_dlp  # type: ignore[import-untyped]

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "source_address": "0.0.0.0",
        "extractor_args": {"youtube": {"skip": ["dash", "hls", "comment"]}},
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
            return list(info.get("entries", [])) if info else []
    except Exception:
        logger.debug("yt-dlp search failed for query=%r", query, exc_info=True)
        return []


def find_youtube_original(
    title: str,
    *,
    author: str = "",
    description: str = "",
    min_similarity: float = 0.35,
) -> dict[str, Any] | None:
    """Find the YouTube original of a Bilibili repost.

    Fast path: if the description already has a YouTube link, use it.
    Otherwise search YouTube with the English terms of the title and
    return the best title-similarity match above ``min_similarity``.

    Returns ``{url, title, uploader, cover_url}`` or ``None``.
    """
    direct = text.find_youtube_id(description or "")
    if direct:
        return {
            "url": f"https://www.youtube.com/watch?v={direct}",
            "title": title,
            "uploader": author or "",
            "cover_url": f"https://i.ytimg.com/vi/{direct}/hqdefault.jpg",
        }

    query = text.build_search_query(title, prefer="english")
    if not query or len(query) < 5:
        return None

    results = _search_youtube(query, max_results=10)
    if not results:
        return None

    best_sim, best = _best_match(title, author, results, title_key="title", author_key="uploader")
    if best_sim < min_similarity:
        logger.debug("find_youtube_original: weak match %.2f for %r", best_sim, title)
        return None

    vid = str(best.get("id", "") or "")
    return {
        "url": f"https://www.youtube.com/watch?v={vid}",
        "title": str(best.get("title", "") or ""),
        "uploader": str(best.get("uploader", "") or ""),
        "cover_url": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if vid else "",
    }


# ── Bilibili search (direction B: find the Bilibili original) ──────

_buvid_cookie: str = ""
_buvid_fetched_at: float = 0.0
_BUVID_TTL = 3600.0


def _get_buvid_cookie() -> str:
    """Fetch (and cache for 1h) a ``buvid3`` cookie from bilibili.

    Bilibili's web search API returns sparse or empty results for
    requests without a ``buvid3`` cookie. A single GET to the homepage
    sets one via ``Set-Cookie``; we cache it process-wide. Best-effort:
    on any failure we return an empty string and the search proceeds
    cookie-less (degraded recall, but still functional).
    """
    global _buvid_cookie, _buvid_fetched_at
    now = time.time()
    if _buvid_cookie and (now - _buvid_fetched_at) < _BUVID_TTL:
        return _buvid_cookie
    try:
        req = urllib.request.Request(
            "https://www.bilibili.com",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            set_cookies = resp.headers.get_all("Set-Cookie") or []
        for c in set_cookies:
            if c.startswith("buvid3="):
                _buvid_cookie = c.split(";", 1)[0]
                _buvid_fetched_at = now
                break
    except Exception:
        logger.debug("bilibili buvid3 fetch failed", exc_info=True)
    return _buvid_cookie


def _search_bilibili(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Search Bilibili's web search API; return raw result entries."""
    url = (
        "https://api.bilibili.com/x/web-interface/search/type"
        f"?search_type=video&keyword={urllib.parse.quote(query)}"
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.bilibili.com",
    }
    cookie = _get_buvid_cookie()
    if cookie:
        headers["Cookie"] = cookie
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        result_list = (data.get("data", {}) or {}).get("result", []) or []
        return result_list[:max_results]
    except Exception:
        logger.debug("bilibili search failed for query=%r", query, exc_info=True)
        return []


def find_bilibili_original(
    title: str,
    *,
    author: str = "",
    description: str = "",
    min_similarity: float = 0.30,
) -> dict[str, Any] | None:
    """Find the Bilibili original of a YouTube repost.

    Fast path: if the text already carries a BV id, construct the URL
    directly. Otherwise search Bilibili (using the Chinese title as the
    query, since that's the searchable content) and return the best
    title-similarity match above ``min_similarity``.

    Returns ``{bvid, url, title, up_name, cover_url}`` or ``None``.
    """
    direct_bvid = text.find_bilibili_id(f"{description} {title}")
    if direct_bvid:
        return {
            "bvid": direct_bvid,
            "url": f"https://www.bilibili.com/video/{direct_bvid}",
            "title": title,
            "up_name": author or "",
            "cover_url": "",
        }

    query = text.build_search_query(title, prefer="native")
    if not query or len(query) < 4:
        return None

    results = _search_bilibili(query, max_results=10)
    if not results:
        return None

    # B站 titles arrive with <em> highlight tags — strip before scoring.
    import re as _re

    cleaned = []
    for entry in results:
        e = dict(entry)
        e["_clean_title"] = _re.sub(r"<[^>]+>", "", str(e.get("title", "") or ""))
        cleaned.append(e)

    best_sim, best = _best_match(
        title, author, cleaned, title_key="_clean_title", author_key="author"
    )
    if best_sim < min_similarity:
        logger.debug("find_bilibili_original: weak match %.2f for %r", best_sim, title)
        return None

    bvid = str(best.get("bvid", "") or "")
    arcurl = str(best.get("arcurl", "") or "")
    if arcurl:
        url = arcurl
    elif bvid:
        url = f"https://www.bilibili.com/video/{bvid}"
    else:
        return None

    pic = str(best.get("pic", "") or "")
    cover = pic if pic.startswith("http") else (f"https:{pic}" if pic else "")
    return {
        "bvid": bvid,
        "url": url,
        "title": str(best.get("_clean_title", "") or ""),
        "up_name": str(best.get("author", "") or ""),
        "cover_url": cover,
    }


# ── shared scoring ─────────────────────────────────────────────────


def _best_match(
    query_title: str,
    query_author: str,
    entries: list[dict[str, Any]],
    *,
    title_key: str,
    author_key: str,
) -> tuple[float, dict[str, Any]]:
    """Return ``(best_similarity, best_entry)`` over *entries*.

    Title similarity is the primary score; a matching author name nudges
    it up (never down), so a same-creator re-upload outranks a
    coincidental title twin from a different channel.
    """
    scored: list[tuple[float, dict[str, Any]]] = []
    for entry in entries:
        cand_title = str(entry.get(title_key, "") or "")
        sim = text.title_similarity(query_title, cand_title)
        cand_author = str(entry.get(author_key, "") or "")
        if query_author and cand_author:
            author_sim = text.title_similarity(query_author, cand_author)
            sim = max(sim, sim * 0.8 + author_sim * 0.2)
        scored.append((sim, entry))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0]
