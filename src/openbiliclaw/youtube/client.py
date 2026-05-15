"""YouTube scraper client for discovery strategies.

Wraps scrapetube (search + channel) and YouTube InnerTube API (trending)
behind a single async interface. All blocking calls run in the default thread
executor so they don't stall the event loop.

Supports three discovery modes:
  - search_videos       — keyword search via scrapetube
  - get_trending        — trending feed via InnerTube browse API
  - get_channel_videos  — recent uploads from a channel via scrapetube

Field-name notes (scrapetube returns YouTube's internal renderer dicts):
  title         → {"runs": [{"text": "..."}]}  or  {"simpleText": "..."}
  ownerText     → {"runs": [{"text": "channel name"}]}
  viewCountText → {"simpleText": "1,234,567 views"}
  lengthText    → {"simpleText": "12:34"}
  thumbnail     → {"thumbnails": [{"url": "...", "width": N, "height": N}]}
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from functools import partial
from typing import Any
from urllib import request as urllib_request

from openbiliclaw.discovery.engine import DiscoveredContent

logger = logging.getLogger(__name__)

_DEFAULT_REGION = "US"

# InnerTube client config for anonymous web requests
_INNERTUBE_KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"
_INNERTUBE_CONTEXT = {
    "client": {
        "clientName": "WEB",
        "clientVersion": "2.20240101.00.00",
        "hl": "en",
    }
}


# ---------------------------------------------------------------------------
# Blocking helpers (run in executor)
# ---------------------------------------------------------------------------


def _scrapetube_search(query: str, limit: int) -> list[dict[str, Any]]:
    try:
        import scrapetube  # type: ignore[import-untyped]

        return [dict(v) for v in scrapetube.get_search(query, results_type="video", limit=limit)]
    except Exception as exc:
        logger.warning("scrapetube.search(%r) failed: %s", query, exc)
        return []


def _scrapetube_channel(channel_id: str, limit: int) -> list[dict[str, Any]]:
    try:
        import scrapetube

        if channel_id.startswith("@") or channel_id.startswith("UC"):
            return [
                dict(v)
                for v in scrapetube.get_channel(
                    channel_url=None, channel_id=channel_id, limit=limit
                )
            ]
        return [dict(v) for v in scrapetube.get_channel(channel_url=channel_id, limit=limit)]
    except Exception as exc:
        logger.warning("scrapetube.channel(%r) failed: %s", channel_id, exc)
        return []


def _innertube_trending(region_code: str, limit: int) -> list[dict[str, Any]]:
    """Fetch YouTube trending via the InnerTube browse API (no API key needed).

    Uses the FEtrending browseId which maps to the YouTube Trending page.
    Returns a flat list of video dicts ready for normalize_yt_video().
    """
    try:
        payload = json.dumps(
            {
                "browseId": "FEtrending",
                "context": {
                    **_INNERTUBE_CONTEXT,
                    "client": {
                        **_INNERTUBE_CONTEXT["client"],
                        "gl": region_code,
                    },
                },
            },
            ensure_ascii=False,
        ).encode()

        url = f"https://www.youtube.com/youtubei/v1/browse?key={_INNERTUBE_KEY}"
        req = urllib_request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "X-YouTube-Client-Name": "1",
                "X-YouTube-Client-Version": "2.20240101.00.00",
            },
            method="POST",
        )
        with urllib_request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())

        return list(_extract_innertube_videos(data, limit=limit))
    except Exception as exc:
        logger.warning("InnerTube trending(%s) failed: %s", region_code, exc)
        return []


def _extract_innertube_videos(
    data: dict[str, Any], *, limit: int
) -> list[dict[str, Any]]:
    """Walk InnerTube's nested renderer tree and extract video renderer dicts."""
    results: list[dict[str, Any]] = []
    _walk(data, results, limit)
    return results


def _walk(node: Any, out: list[dict[str, Any]], limit: int) -> None:
    if len(out) >= limit:
        return
    if isinstance(node, dict):
        if "videoId" in node and "title" in node:
            out.append(node)
            return
        for v in node.values():
            _walk(v, out, limit)
    elif isinstance(node, list):
        for item in node:
            if len(out) >= limit:
                return
            _walk(item, out, limit)


# ---------------------------------------------------------------------------
# Normalization — handles both scrapetube and InnerTube renderer shapes
# ---------------------------------------------------------------------------


def _extract_text(value: Any) -> str:
    """Unwrap YouTube's nested text objects to a plain string."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        if "simpleText" in value:
            return str(value["simpleText"]).strip()
        runs = value.get("runs")
        if isinstance(runs, list):
            return "".join(str(r.get("text", "")) for r in runs).strip()
    return ""


def _parse_number(text: str) -> int:
    """Parse '1,234,567 views' or '1.2M' → int."""
    text = text.lower().replace(",", "").strip()
    m = re.search(r"([\d.]+)\s*([kmb]?)", text)
    if not m:
        return 0
    num = float(m.group(1))
    suffix = m.group(2)
    return int(num * {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}.get(suffix, 1))


def _parse_duration(value: Any) -> int:
    """Parse seconds (int/str) or 'H:MM:SS' / 'M:SS' text → seconds."""
    if isinstance(value, (int, float)):
        return int(value)
    text = _extract_text(value) if isinstance(value, dict) else str(value or "")
    if ":" in text:
        parts = text.strip().split(":")
        try:
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except ValueError:
            pass
    try:
        return int(text)
    except (ValueError, TypeError):
        return 0


def normalize_yt_video(
    raw: dict[str, Any],
    *,
    source_strategy: str,
) -> DiscoveredContent | None:
    """Map a scrapetube / InnerTube video renderer dict to DiscoveredContent."""
    video_id = str(raw.get("videoId") or raw.get("id") or "").strip()
    if not video_id:
        return None

    title = _extract_text(raw.get("title") or raw.get("fulltitle") or "")
    if not title:
        return None

    # Channel name — try scrapetube fields first, then yt-dlp / InnerTube fields
    channel = _extract_text(
        raw.get("ownerText")
        or raw.get("shortBylineText")
        or raw.get("longBylineText")
        or raw.get("channel")
        or raw.get("uploader")
        or raw.get("channelTitle")
        or ""
    )

    # View count — scrapetube uses viewCountText, yt-dlp uses view_count (int)
    view_count = 0
    for vc_key in ("viewCountText", "viewCount", "view_count"):
        vc = raw.get(vc_key)
        if vc is None:
            continue
        if isinstance(vc, int):
            view_count = vc
            break
        text = _extract_text(vc) if isinstance(vc, dict) else str(vc)
        if text:
            view_count = _parse_number(text)
            break

    # Duration — scrapetube: lengthText (simpleText "12:34"); yt-dlp: duration (int)
    duration = _parse_duration(
        raw.get("lengthText") or raw.get("lengthSeconds") or raw.get("duration")
    )

    # Thumbnail — prefer highest resolution
    cover_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
    thumbs_raw = raw.get("thumbnail") or {}
    if isinstance(thumbs_raw, dict):
        thumbs = thumbs_raw.get("thumbnails") or []
        if thumbs and isinstance(thumbs[-1], dict):
            cover_url = str(thumbs[-1].get("url", cover_url))
    elif isinstance(thumbs_raw, list) and thumbs_raw:
        cover_url = str(thumbs_raw[-1].get("url", cover_url))

    # Description snippet
    description = _extract_text(
        raw.get("descriptionSnippet") or raw.get("description") or ""
    )[:300]

    return DiscoveredContent(
        content_id=video_id,
        content_url=f"https://www.youtube.com/watch?v={video_id}",
        source_platform="youtube",
        title=title,
        author_name=channel,
        up_name=channel,
        cover_url=cover_url,
        duration=duration,
        view_count=view_count,
        description=description,
        source_strategy=source_strategy,
    )


# ---------------------------------------------------------------------------
# Async client
# ---------------------------------------------------------------------------


@dataclass
class YtScraperClient:
    """Async YouTube discovery client backed by scrapetube + InnerTube API."""

    region_code: str = _DEFAULT_REGION
    _executor: Any = field(default=None, init=False, repr=False)

    async def search_videos(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(_scrapetube_search, query, limit))

    async def get_trending(self, *, limit: int = 50) -> list[dict[str, Any]]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, partial(_innertube_trending, self.region_code, limit)
        )

    async def get_channel_videos(self, channel_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(_scrapetube_channel, channel_id, limit))
