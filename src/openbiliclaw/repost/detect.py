"""Repost detection — two parallel detectors, one per direction.

Each returns a :class:`RepostSignal` (a small, testable value object)
rather than a bare bool, so callers can log *why* something was flagged
and tune thresholds. Both detectors are pure functions of their text
inputs — no network, no state.

Design symmetry: both directions follow the same signal ladder:

    strong   : an explicit cross-platform link or id in the description
               → decisive on its own
    structural: the title's language profile is consistent with the
               claimed origin (English-heavy for A, CJK-heavy for B)
    lexical  : origin-specific keywords (translation/AI-dub for A,
               bilibili-culture markers for B)
    social   : repost-accusation keywords in comments (needs corroboration)

The asymmetry lives only in the vocabularies (see vocab.py), not in
the shape of the logic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from . import text, vocab

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RepostSignal:
    """Outcome of a repost-detection pass."""

    detected: bool
    confidence: float = 0.0  # rough [0,1]; strong signals → ~1.0
    reasons: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.detected


def _any_kw(haystack: str, keywords: tuple[str, ...]) -> str | None:
    """Return the first keyword found in *haystack* (lowered), else None."""
    low = haystack.lower()
    for kw in keywords:
        if kw.lower() in low:
            return kw
    return None


# ── Direction A: bilibili video reposted FROM youtube ──────────────


def detect_bilibili_from_youtube(
    title: str,
    *,
    description: str = "",
    comments: list[str] | None = None,
) -> RepostSignal:
    """Is this Bilibili video likely a 搬运 of a YouTube original?

    Signal ladder (first match wins, in decreasing strength):
      0. a YouTube link in the description           → decisive
      1. title is >35% Latin (mostly English)        → strong
      2. foreign brand mention + some Latin           → strong
      3. repost keyword + English terms / YT mention  → moderate
      4. ≥2 meaningful English phrases + some Latin    → moderate
      5. AI-dub keyword in title or description        → moderate
      6. ≥1 (yt-mentioning) or ≥2 repost comments      → weak/social
    """
    if not title:
        return RepostSignal(False)

    reasons: list[str] = []

    # 0. Strong: YouTube link in description. Checked before the
    # title-length guard — a link in the description is decisive even
    # when the title itself is too short to carry signal.
    if text.find_youtube_id(description or ""):
        return RepostSignal(True, 1.0, ["描述含 YouTube 链接"])

    if len(title) < 5:
        return RepostSignal(False)

    lr = text.latin_ratio(title)
    english_terms = text.extract_english_terms(title)
    meaningful = [t for t in english_terms if len(t) >= 6]
    has_meaningful = len(meaningful) >= 2 or (
        len(meaningful) == 1 and len(meaningful[0]) >= 10
    )

    # 1. High Latin ratio — but only when the title isn't also
    # CJK-heavy. "我用Python写推荐系统" is ~37% Latin yet plainly a
    # Chinese-primary title with one embedded English noun; a genuine
    # foreign repost title ("How Transformers Work") is Latin with
    # almost no CJK. Requiring low CJK here kills that false-positive
    # class without weakening detection of actually-English titles.
    if lr > 0.35 and text.cjk_ratio(title) < 0.20:
        return RepostSignal(True, 0.8, [f"标题英文占比高({lr:.0%})"])

    # 2. Foreign brand + some Latin.
    brand = _any_kw(title, vocab.A_FOREIGN_BRANDS)
    if brand and lr > 0.05:
        return RepostSignal(True, 0.75, [f"外媒/频道名:{brand}"])

    # 3. Repost keyword + English presence.
    combined = f"{title} {description}"
    repost_kw = _any_kw(combined, vocab.A_REPOST_KEYWORDS)
    if repost_kw and (
        len(english_terms) >= 1 or lr > 0.10 or "youtu" in (description or "").lower()
    ):
        return RepostSignal(True, 0.65, [f"搬运/字幕关键词:{repost_kw}"])

    # 4. Strong English phrases.
    if has_meaningful and lr > 0.15:
        return RepostSignal(True, 0.6, ["标题含完整英文短语"])

    # 5. AI-dub signals.
    ai_kw = _any_kw(title, vocab.A_AI_DUB_KEYWORDS) or _any_kw(
        description, vocab.A_AI_DUB_KEYWORDS
    )
    if ai_kw:
        return RepostSignal(True, 0.6, [f"AI配音/机翻关键词:{ai_kw}"])
    desc_sig = _any_kw(description, vocab.A_AI_DUB_DESC_SIGNALS)
    if desc_sig:
        return RepostSignal(True, 0.55, [f"描述含来源标记:{desc_sig}"])

    # 6. Social: comment accusations.
    signal = _comment_signal(
        comments, vocab.A_REPOST_COMMENT_KEYWORDS, ("youtube", "youtu.be", "油管", "YT")
    )
    if signal:
        reasons.append(signal)
        return RepostSignal(True, 0.5, reasons)

    return RepostSignal(False)


# ── Direction B: youtube video reposted FROM bilibili ──────────────


def detect_youtube_from_bilibili(
    title: str,
    *,
    description: str = "",
    comments: list[str] | None = None,
) -> RepostSignal:
    """Is this YouTube video likely a re-upload of a Bilibili original?

    Signal ladder (first match wins, in decreasing strength):
      0. a bilibili.com/b23.tv link or BV id in description → decisive
      1. explicit "搬运自B站 / 转自哔哩哔哩 / 已获授权" attribution → strong
      2. CJK-dominant title + a bilibili-culture keyword       → moderate
      3. CJK-dominant title + ≥2 bilibili-culture keywords      → moderate
      4. ≥1 (bilibili-mentioning) or ≥2 repost comments         → weak/social

    The key difference from the old "has any Chinese character"
    detector: Chinese text alone is NEVER sufficient (YouTube is full
    of legitimate original Chinese creators). CJK-dominance is treated
    as a *necessary precondition* that must co-occur with an actual
    bilibili-origin signal.
    """
    if not title:
        return RepostSignal(False)

    desc = description or ""

    # 0. Strong: bilibili link or BV id in description / title. Checked
    # before the title-length guard — decisive regardless of title.
    if text.has_bilibili_link(desc) or text.find_bilibili_id(desc):
        return RepostSignal(True, 1.0, ["描述含 Bilibili 链接/BV号"])
    if text.find_bilibili_id(title):
        return RepostSignal(True, 1.0, ["标题含 BV号"])

    if len(title) < 4:
        return RepostSignal(False)

    # 1. Strong: explicit source attribution in description.
    attrib = _any_kw(desc, vocab.B_BILI_ORIGIN_DESC_SIGNALS)
    if attrib:
        return RepostSignal(True, 0.85, [f"描述含来源声明:{attrib}"])

    # Structural precondition for the weaker lexical signals: the title
    # must be Chinese-dominant. A mostly-English title with the word
    # "bilibili" in it is more likely *about* bilibili than *from* it.
    title_cjk = text.cjk_ratio(title)
    chinese_dominant = title_cjk > 0.30

    combined_low = f"{title} {desc}".lower()
    origin_hits = [kw for kw in vocab.B_BILI_ORIGIN_KEYWORDS if kw.lower() in combined_low]

    # 2/3. CJK-dominant + bilibili-culture keyword(s).
    if chinese_dominant and origin_hits:
        if len(origin_hits) >= 2:
            return RepostSignal(
                True, 0.7, [f"中文标题 + B站文化词×{len(origin_hits)}:{','.join(origin_hits[:3])}"]
            )
        return RepostSignal(True, 0.55, [f"中文标题 + B站文化词:{origin_hits[0]}"])

    # 4. Social: comment accusations.
    signal = _comment_signal(
        comments,
        vocab.B_BILI_ORIGIN_COMMENT_KEYWORDS,
        ("bilibili", "哔哩哔哩", "b站", "b23.tv"),
    )
    if signal:
        return RepostSignal(True, 0.5, [signal])

    return RepostSignal(False)


# ── shared social-signal helper ────────────────────────────────────


def _comment_signal(
    comments: list[str] | None,
    keywords: tuple[str, ...],
    platform_markers: tuple[str, ...],
) -> str | None:
    """Detect repost accusations in comments.

    A single comment that pairs a repost keyword with an explicit
    platform mention (e.g. "原视频在YouTube") is strong enough alone.
    Otherwise two independently-suspicious comments are required.
    Returns a reason string on a hit, else None.
    """
    if not comments:
        return None
    hits = 0
    for comment in comments:
        low = comment.lower()
        kw = None
        for k in keywords:
            if k.lower() in low:
                kw = k
                break
        if kw is None:
            continue
        mentions_platform = any(m.lower() in low for m in platform_markers)
        if mentions_platform:
            return f"评论指认搬运(含平台名):{kw}"
        hits += 1
        if hits >= 2:
            return f"≥2 条评论指认搬运:{kw}"
    return None
