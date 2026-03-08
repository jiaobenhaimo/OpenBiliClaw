"""Content Discovery Engine.

Coordinates multiple discovery strategies to find content
that matches the user's soul profile.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from openbiliclaw.soul.profile import SoulProfile

logger = logging.getLogger(__name__)


class SupportsStructuredTask(Protocol):
    async def complete_structured_task(
        self,
        *,
        system_instruction: str,
        user_input: str,
        history: list[dict[str, str]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> object: ...


@dataclass
class DiscoveredContent:
    """A piece of content discovered by the engine."""

    bvid: str = ""  # Bilibili video ID
    title: str = ""
    up_name: str = ""  # UP主 name
    up_mid: int = 0  # UP主 ID
    cover_url: str = ""
    duration: int = 0  # seconds
    view_count: int = 0
    like_count: int = 0
    tags: list[str] = field(default_factory=list)
    description: str = ""
    source_strategy: str = ""  # Which strategy found this
    relevance_score: float = 0.0  # 0.0 - 1.0 (based on user soul)
    relevance_reason: str = ""  # Why this is relevant to the user


class DiscoveryStrategy(ABC):
    """Base class for content discovery strategies."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy name."""
        ...

    @abstractmethod
    async def discover(
        self, profile: SoulProfile, limit: int = 20
    ) -> list[DiscoveredContent]:
        """Execute the discovery strategy.

        Args:
            profile: Current user soul profile for relevance guidance.
            limit: Maximum number of items to return.

        Returns:
            List of discovered content items.
        """
        ...


class ContentDiscoveryEngine:
    """Orchestrates multiple discovery strategies.

    Available strategies:
    - Search: keyword-based search from user interests
    - Related: follow related recommendation chains
    - Trending: scan trending/ranking content
    - Comments: mine recommendations from comment sections
    - UPTrack: track followed/discovered UP主
    - Explore: cross-domain surprise discovery
    """

    def __init__(self, llm_service: SupportsStructuredTask | None = None) -> None:
        self._strategies: list[DiscoveryStrategy] = []
        self._llm_service = llm_service

    def register_strategy(self, strategy: DiscoveryStrategy) -> None:
        """Register a discovery strategy."""
        self._strategies.append(strategy)
        logger.info("Registered discovery strategy: %s", strategy.name)

    async def discover(
        self, profile: SoulProfile, strategies: list[str] | None = None
    ) -> list[DiscoveredContent]:
        """Run discovery with selected (or all) strategies.

        Args:
            profile: User soul profile for relevance evaluation.
            strategies: Optional list of strategy names to run.
                       If None, runs all registered strategies.

        Returns:
            Combined, deduplicated, and scored list of discovered content.
        """
        results: list[DiscoveredContent] = []

        active = self._strategies
        if strategies:
            active = [s for s in self._strategies if s.name in strategies]

        for strategy in active:
            try:
                items = await strategy.discover(profile)
                results.extend(items)
                logger.info("Strategy '%s' found %d items.", strategy.name, len(items))
            except Exception:
                logger.exception("Strategy '%s' failed.", strategy.name)

        # Deduplicate by bvid
        seen: set[str] = set()
        unique: list[DiscoveredContent] = []
        for item in results:
            if item.bvid not in seen:
                seen.add(item.bvid)
                unique.append(item)

        # Sort by relevance
        unique.sort(key=lambda x: x.relevance_score, reverse=True)
        return unique

    async def evaluate_content(
        self, content: DiscoveredContent, profile: SoulProfile
    ) -> float:
        """Evaluate how relevant a piece of content is for the user.

        The core evaluation is based on the user's Soul — their deep personality
        and interests — not just surface-level metrics.

        Args:
            content: Content to evaluate.
            profile: User's soul profile.

        Returns:
            Relevance score (0.0 - 1.0).
        """
        if self._llm_service is None:
            return 0.0

        from openbiliclaw.llm.prompts import build_content_evaluation_prompt

        messages = build_content_evaluation_prompt(
            profile_summary={
                "personality_portrait": profile.personality_portrait,
                "core_traits": profile.core_traits[:5],
                "deep_needs": profile.deep_needs[:5],
                "interests": [
                    {
                        "name": item.name,
                        "category": item.category,
                        "weight": item.weight,
                    }
                    for item in profile.preferences.interests[:10]
                ],
            },
            content_summary={
                "title": content.title,
                "up_name": content.up_name,
                "description": content.description,
                "duration": content.duration,
                "view_count": content.view_count,
                "source_strategy": content.source_strategy,
            },
        )
        try:
            response = await self._llm_service.complete_structured_task(
                system_instruction=messages[0]["content"],
                user_input=messages[1]["content"],
            )
            payload = json.loads(str(getattr(response, "content", "")).strip())
            if not isinstance(payload, dict):
                return 0.0
            score = self._clamp_score(payload.get("score", 0.0))
            reason = str(payload.get("reason", "")).strip()
        except Exception:
            logger.exception("Failed to evaluate discovered content: %s", content.bvid)
            return 0.0

        content.relevance_score = score
        content.relevance_reason = reason
        return score

    @staticmethod
    def _clamp_score(raw_value: object) -> float:
        if isinstance(raw_value, bool | int | float):
            value = float(raw_value)
        elif isinstance(raw_value, str):
            try:
                value = float(raw_value)
            except ValueError:
                value = 0.0
        else:
            value = 0.0
        return max(0.0, min(1.0, round(value, 4)))
