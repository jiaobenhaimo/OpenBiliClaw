"""Tests for the Soul profile models."""

from openbiliclaw.soul.profile import (
    AwarenessNote,
    InsightHypothesis,
    InterestTag,
    SoulProfile,
)


class TestSoulProfile:
    """Test SoulProfile data model."""

    def test_empty_profile_context(self) -> None:
        profile = SoulProfile()
        context = profile.to_llm_context()
        assert "尚未建立" in context

    def test_profile_with_portrait(self) -> None:
        profile = SoulProfile(
            personality_portrait="一个好奇心很强的技术爱好者",
            core_traits=["好奇", "理性"],
        )
        context = profile.to_llm_context()
        assert "好奇心很强" in context
        assert "好奇" in context

    def test_profile_with_insights(self) -> None:
        profile = SoulProfile(
            active_insights=[
                InsightHypothesis(
                    hypothesis="他看游戏视频是为了放松",
                    confidence=0.8,
                ),
            ]
        )
        context = profile.to_llm_context()
        assert "放松" in context
        assert "80%" in context

    def test_profile_with_awareness(self) -> None:
        profile = SoulProfile(
            recent_awareness=[
                AwarenessNote(
                    date="2026-03-07",
                    observation="今天搜索了三次摄影相关内容",
                ),
            ]
        )
        context = profile.to_llm_context()
        assert "摄影" in context


class TestInterestTag:
    """Test InterestTag model."""

    def test_default_weight(self) -> None:
        tag = InterestTag(name="AI", category="科技")
        assert tag.weight == 1.0

    def test_custom_weight(self) -> None:
        tag = InterestTag(name="游戏", category="娱乐", weight=0.3)
        assert tag.weight == 0.3
