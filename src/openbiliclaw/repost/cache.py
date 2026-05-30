"""Persistent two-tier cache for repost lookups.

Replaces the old single module-global ``_yt_cache`` dict (which crammed
both directions into one file using a ``bili:`` key prefix) with a
proper instance-based cache. The service layer creates TWO instances —
one per direction — so the two directions never share storage.

Each instance is:
  1. an in-memory dict (fast, per-process), plus
  2. a JSON file on disk (survives restarts), reloaded when the file's
     mtime advances past what this process last saw.

A stored value of ``None`` is a real, meaningful entry: "we looked and
found no match" — cached so we don't re-run an expensive search every
time. ``get()`` therefore distinguishes "key absent" (returns the
``MISS`` sentinel) from "key present, value is None" (returns None).
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Final

logger = logging.getLogger(__name__)


class _Miss:
    """Sentinel for 'key not present', distinct from a cached None."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return "<MISS>"


MISS: Final = _Miss()


class RepostCache:
    """A namespaced, file-backed lookup cache for one repost direction."""

    def __init__(self, path: Path, *, ttl_seconds: int = 86400) -> None:
        self._path = Path(path)
        self._ttl = max(0, int(ttl_seconds))
        self._data: dict[str, dict[str, Any] | None] = {}
        self._disk_mtime: float = 0.0
        self._loaded = False

    # ── public API ────────────────────────────────────────────────

    def get(self, key: str) -> dict[str, Any] | None | _Miss:
        """Return the cached value, ``None`` (cached no-match), or ``MISS``."""
        self._ensure_loaded()
        if key not in self._data:
            return MISS
        value = self._data[key]
        return dict(value) if isinstance(value, dict) else None

    def set(self, key: str, value: dict[str, Any] | None) -> None:
        """Store *value* for *key* and persist to disk."""
        self._ensure_loaded()
        self._data[key] = dict(value) if isinstance(value, dict) else None
        self._save()

    def clear(self) -> None:
        """Drop all in-memory entries and remove the backing file."""
        self._data.clear()
        self._disk_mtime = 0.0
        self._loaded = True  # an explicit clear means we "know" it's empty
        try:
            if self._path.exists():
                self._path.unlink()
        except OSError:
            logger.debug("RepostCache: failed to unlink %s", self._path, exc_info=True)

    def __len__(self) -> int:
        self._ensure_loaded()
        return len(self._data)

    def __contains__(self, key: str) -> bool:
        self._ensure_loaded()
        return key in self._data

    # ── persistence ───────────────────────────────────────────────

    def _ensure_loaded(self) -> None:
        """Lazy-load (and reload-on-mtime-advance) the backing file."""
        if not self._path.exists():
            self._loaded = True
            return
        try:
            mtime = self._path.stat().st_mtime
        except OSError:
            self._loaded = True
            return
        if self._loaded and mtime <= self._disk_mtime:
            return
        try:
            with open(self._path, encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                # Merge rather than replace: another worker may have
                # written keys this process hasn't seen, and this
                # process may hold keys not yet flushed.
                self._data.update(loaded)
            self._disk_mtime = mtime
        except (OSError, ValueError):
            logger.debug("RepostCache: failed to load %s", self._path, exc_info=True)
        finally:
            self._loaded = True

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, ensure_ascii=False, indent=2)
            self._disk_mtime = time.time()
        except OSError:
            logger.debug("RepostCache: failed to save %s", self._path, exc_info=True)
