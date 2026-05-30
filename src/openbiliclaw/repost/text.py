"""Pure text utilities shared by both repost directions.

No network, no state — every function here is deterministic and unit-
testable in isolation. The detection and search layers build on these.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

# Bilibili video id: "BV" followed by 10 base58-ish chars.
_BV_ID_RE = re.compile(r"\bBV[0-9A-Za-z]{10}\b")

# A bilibili.com/video/<bvid> or b23.tv short link in free text.
_BILI_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?bilibili\.com/video/(BV[0-9A-Za-z]{10})"
    r"|(?:https?://)?b23\.tv/[0-9A-Za-z]+",
)

# A youtube watch / short link in free text. Group 1 / group 2 capture
# the 11-char video id depending on which form matched.
_YT_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})"
    r"|(?:https?://)?youtu\.be/([a-zA-Z0-9_-]{11})",
)

_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")


def title_similarity(a: str, b: str) -> float:
    """Fuzzy similarity between two titles in [0.0, 1.0].

    Strips punctuation (keeping CJK, ASCII alnum, and whitespace),
    lowercases, then runs difflib's ratio. Punctuation stripping
    matters because re-uploads frequently re-bracket or re-emoji a
    title without changing its substance.
    """
    a_clean = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff\s]", "", a).strip().lower()
    b_clean = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff\s]", "", b).strip().lower()
    if not a_clean or not b_clean:
        return 0.0
    return SequenceMatcher(None, a_clean, b_clean).ratio()


def latin_ratio(text: str) -> float:
    """Fraction of characters that are ASCII letters, in [0.0, 1.0]."""
    if not text:
        return 0.0
    latin = sum(1 for ch in text if "a" <= ch.lower() <= "z")
    return latin / len(text)


def has_cjk(*texts: str) -> bool:
    """True if any of the given strings contains a CJK character."""
    return any(bool(t) and bool(_CJK_RE.search(t)) for t in texts)


def cjk_ratio(text: str) -> float:
    """Fraction of characters that are CJK, in [0.0, 1.0]."""
    if not text:
        return 0.0
    cjk = len(_CJK_RE.findall(text))
    return cjk / len(text)


def extract_english_terms(title: str) -> list[str]:
    """Extract meaningful English/Latin runs from a mixed-language title.

    E.g. ``"【翻译】15 Chord Progressions for 15 Different Emotions"``
    → ``["15 Chord Progressions for 15 Different Emotions"]``
    """
    terms: list[str] = []
    # Runs of Latin + digits + light punctuation, ≥4 chars to drop noise.
    for match in re.finditer(r"[A-Za-z][A-Za-z0-9 .!?,:;'\"\-\(\)]{3,}", title):
        chunk = match.group().strip().strip(" -:;,.\\\"'()[]")
        if len(chunk) >= 4:
            terms.append(chunk)
    # Terms starting with a digit but containing letters (1080P, 4K, 3D).
    for match in re.finditer(r"[0-9][A-Za-z0-9]{1,}", title):
        chunk = match.group().strip()
        if any(c.isalpha() for c in chunk) and chunk not in terms:
            terms.append(chunk)
    return terms


def find_youtube_id(text: str) -> str | None:
    """Return the first YouTube video id found in *text*, or None."""
    if not text:
        return None
    m = _YT_URL_RE.search(text)
    if not m:
        return None
    return m.group(1) or m.group(2)


def find_bilibili_id(text: str) -> str | None:
    """Return the first Bilibili BV id found in *text*, or None.

    Checks both a bare ``BVxxxxxxxxxx`` token and the id embedded in a
    bilibili.com/video link. (b23.tv short links don't expose the bvid
    without resolving the redirect, so they're detected as a signal
    elsewhere but don't yield an id here.)
    """
    if not text:
        return None
    url_match = _BILI_URL_RE.search(text)
    if url_match and url_match.group(1):
        return url_match.group(1)
    bare = _BV_ID_RE.search(text)
    return bare.group(0) if bare else None


def has_bilibili_link(text: str) -> bool:
    """True if *text* contains a bilibili.com/video or b23.tv link."""
    return bool(text) and bool(_BILI_URL_RE.search(text))


def build_search_query(title: str, *, prefer: str = "auto") -> str:
    """Build an effective cross-platform search query from a title.

    ``prefer``:
      - ``"english"`` — pull the longest English run (best for finding
        a YouTube original of a Chinese-titled repost).
      - ``"native"``  — use the cleaned full title (best for finding a
        Bilibili original of a Chinese-titled YouTube repost, where the
        Chinese text IS the searchable content).
      - ``"auto"``    — english terms if present, else the full title.

    Capped at 200 chars (search backends impose their own limits).
    """
    if prefer in ("auto", "english"):
        english_terms = extract_english_terms(title)
        if english_terms:
            return max(english_terms, key=len)[:200]
        if prefer == "english":
            return title[:200]
    return title[:200]
