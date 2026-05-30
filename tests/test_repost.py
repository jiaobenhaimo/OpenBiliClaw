"""Tests for the bidirectional repost package.

These exist specifically because PR #53 rejected the old yt_replacer
module for being 916 lines with zero test coverage. The module is now
a package with separated concerns, each independently testable.

Run a single test inline (pytest may be unavailable in some envs):
    python -m pytest tests/test_repost.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from openbiliclaw.repost import (
    detect_bilibili_from_youtube as dA,
    detect_youtube_from_bilibili as dB,
    is_likely_bilibili_origin,
    is_likely_repost,
)
from openbiliclaw.repost import text
from openbiliclaw.repost.cache import MISS, RepostCache


# ── text utilities ─────────────────────────────────────────────────


def test_find_youtube_id_variants() -> None:
    assert text.find_youtube_id("see https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert text.find_youtube_id("https://youtu.be/dQw4w9WgXcQ now") == "dQw4w9WgXcQ"
    assert text.find_youtube_id("youtube.com/watch?v=abcDEF12345") == "abcDEF12345"
    assert text.find_youtube_id("no link here") is None


def test_find_bilibili_id_variants() -> None:
    assert text.find_bilibili_id("bilibili.com/video/BV1xx411c7mD") == "BV1xx411c7mD"
    assert text.find_bilibili_id("bare BV1xx411c7mD token") == "BV1xx411c7mD"
    assert text.find_bilibili_id("nothing") is None


def test_latin_and_cjk_ratio() -> None:
    assert text.latin_ratio("hello") == 1.0
    assert text.latin_ratio("你好") == 0.0
    assert 0.0 < text.cjk_ratio("hello你好") < 1.0
    assert text.cjk_ratio("你好世界") == 1.0


def test_title_similarity_strips_punctuation() -> None:
    a = "【翻译】How Transformers Work!!!"
    b = "How Transformers Work"
    assert text.title_similarity(a, b) > 0.7


def test_extract_english_terms() -> None:
    terms = text.extract_english_terms("【中字】15 Chord Progressions for Emotions")
    assert any("Chord Progressions" in t for t in terms)


def test_build_search_query_prefers() -> None:
    title = "【熟肉】Deep Learning Explained 深度学习讲解"
    eng = text.build_search_query(title, prefer="english")
    assert "Deep Learning Explained" in eng
    native = text.build_search_query("纯中文标题没有英文", prefer="native")
    assert native == "纯中文标题没有英文"


# ── Direction A detector (bilibili ← youtube) ──────────────────────


def test_dirA_youtube_link_in_description_is_decisive() -> None:
    sig = dA("短", description="原视频 https://youtube.com/watch?v=dQw4w9WgXcQ")
    assert sig.detected and sig.confidence == 1.0


def test_dirA_english_heavy_title() -> None:
    assert dA("How Large Language Models Actually Work").detected


def test_dirA_translation_keyword() -> None:
    assert dA("【中字】a short clip about cats", description="").detected


def test_dirA_ai_dub_keyword_chinese_title() -> None:
    # Fully Chinese title, but AI-dub keyword → still a repost.
    assert dA("AI配音 这个发现太震撼").detected


def test_dirA_negatives() -> None:
    assert not dA("【自制】我用Python写推荐系统").detected
    assert not dA("今天的vlog 上海一日游记录").detected
    assert not dA("原创动画短片 第一集").detected


def test_dirA_comment_signal_needs_platform_or_corroboration() -> None:
    # one bare repost comment → not enough
    assert not dA("某游戏实况", comments=["搬运的"]).detected
    # one comment naming youtube → enough
    assert dA("某游戏实况", comments=["原视频在youtube上"]).detected
    # two bare repost comments → enough
    assert dA("某游戏实况", comments=["搬运的", "这是搬运"]).detected


# ── Direction B detector (youtube ← bilibili) ──────────────────────


def test_dirB_bilibili_link_in_description_is_decisive() -> None:
    sig = dB("any", description="转自 bilibili.com/video/BV1xx411c7mD")
    assert sig.detected and sig.confidence == 1.0


def test_dirB_bv_id_in_title() -> None:
    assert dB("精彩集锦 BV1xx411c7mD").detected


def test_dirB_explicit_attribution() -> None:
    assert dB("游戏混剪合集", description="搬运自B站 已获UP主授权").detected


def test_dirB_cjk_plus_culture_keywords() -> None:
    assert dB("阿婆主带你看世界 记得一键三连").detected


def test_dirB_chinese_only_is_NOT_enough() -> None:
    # The central fix vs the old "has any Chinese char" detector:
    # plain Chinese content with no bilibili-origin signal must NOT
    # be flagged. YouTube has many original Chinese creators.
    assert not dB("今天天气很好我们去公园散步").detected
    assert not dB("美食制作教程 红烧肉的做法").detected


def test_dirB_english_dominant_with_bilibili_word_not_flagged() -> None:
    # "bilibili" appearing in a mostly-English title is more likely
    # *about* bilibili than *from* it — structural CJK gate blocks it.
    assert not dB("A review of the bilibili streaming platform").detected


def test_wrappers_match_detectors() -> None:
    assert is_likely_repost("【翻译】TED talk on creativity") is True
    assert is_likely_bilibili_origin("视频", description="bilibili.com/video/BV1xx411c7mD") is True
    assert is_likely_repost("普通的中文vlog记录") is False
    assert is_likely_bilibili_origin("just an english title") is False


# ── cache ───────────────────────────────────────────────────────────


def test_cache_miss_vs_cached_none() -> None:
    with tempfile.TemporaryDirectory() as td:
        c = RepostCache(Path(td) / "c.json")
        assert c.get("k") is MISS  # never stored
        c.set("k", None)  # store an explicit no-match
        assert c.get("k") is None  # now a cached None, not MISS
        assert "k" in c


def test_cache_roundtrips_dict() -> None:
    with tempfile.TemporaryDirectory() as td:
        c = RepostCache(Path(td) / "c.json")
        c.set("bv1", {"yt_url": "https://x", "yt_title": "T"})
        got = c.get("bv1")
        assert isinstance(got, dict) and got["yt_url"] == "https://x"


def test_cache_persists_to_disk_and_reloads() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "c.json"
        c1 = RepostCache(path)
        c1.set("bv1", {"yt_url": "https://x"})
        # New instance over the same file reads the persisted entry.
        c2 = RepostCache(path)
        assert c2.get("bv1") == {"yt_url": "https://x"}


def test_cache_clear_removes_file() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "c.json"
        c = RepostCache(path)
        c.set("k", {"a": 1})
        assert path.exists()
        c.clear()
        assert not path.exists()
        assert c.get("k") is MISS


def test_two_caches_are_independent() -> None:
    # The whole point of the refactor: directions don't share storage.
    with tempfile.TemporaryDirectory() as td:
        a = RepostCache(Path(td) / "a.json")
        b = RepostCache(Path(td) / "b.json")
        a.set("shared_key", {"side": "A"})
        b.set("shared_key", {"side": "B"})
        assert a.get("shared_key") == {"side": "A"}
        assert b.get("shared_key") == {"side": "B"}


# ── search scoring (network mocked) ─────────────────────────────────


def test_find_youtube_original_fast_path_from_description() -> None:
    from openbiliclaw.repost import search

    res = search.find_youtube_original(
        "some title", description="orig https://youtube.com/watch?v=dQw4w9WgXcQ"
    )
    assert res is not None
    assert res["url"].endswith("dQw4w9WgXcQ")


def test_find_youtube_original_scores_search_results(monkeypatch) -> None:
    from openbiliclaw.repost import search

    def fake_search(query, max_results=10):
        return [
            {"id": "aaaaaaaaaaa", "title": "Totally unrelated", "uploader": "X"},
            {"id": "bbbbbbbbbbb", "title": "How Transformers Work", "uploader": "Y"},
        ]

    monkeypatch.setattr(search, "_search_youtube", fake_search)
    res = search.find_youtube_original("How Transformers Work")
    assert res is not None and res["url"].endswith("bbbbbbbbbbb")


def test_find_bilibili_original_strips_em_tags(monkeypatch) -> None:
    from openbiliclaw.repost import search

    def fake_search(query, max_results=10):
        return [
            {"bvid": "BV1xx411c7mD", "title": "红烧肉<em>教程</em>", "author": "厨师", "pic": "//x.jpg"},
        ]

    monkeypatch.setattr(search, "_search_bilibili", fake_search)
    res = search.find_bilibili_original("红烧肉教程")
    assert res is not None
    assert res["bvid"] == "BV1xx411c7mD"
    assert "<em>" not in res["title"]
    assert res["cover_url"].startswith("https:")
