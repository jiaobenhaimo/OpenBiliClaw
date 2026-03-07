"""Search-based content discovery strategy."""

from __future__ import annotations

from typing import TYPE_CHECKING

from openbiliclaw.discovery.engine import DiscoveredContent, DiscoveryStrategy

if TYPE_CHECKING:
    from openbiliclaw.soul.profile import SoulProfile


class SearchStrategy(DiscoveryStrategy):
    """Discover content by generating search queries from user interests."""

    @property
    def name(self) -> str:
        return "search"

    async def discover(
        self, profile: SoulProfile, limit: int = 20
    ) -> list[DiscoveredContent]:
        """Generate search queries based on user soul and execute them.

        Strategy:
        1. Extract key interests from the soul profile
        2. Generate creative search keyword combinations
        3. Execute searches via Bilibili API
        4. Score results against the soul profile

        Args:
            profile: User soul profile.
            limit: Maximum results.

        Returns:
            Discovered content list.
        """
        # TODO: Implement LLM-powered search query generation
        # TODO: Execute searches via bilibili client
        # TODO: Score and filter results
        return []


class TrendingStrategy(DiscoveryStrategy):
    """Discover content from trending/ranking pages."""

    @property
    def name(self) -> str:
        return "trending"

    async def discover(
        self, profile: SoulProfile, limit: int = 20
    ) -> list[DiscoveredContent]:
        """Scan trending and ranking content, filter by soul relevance.

        Args:
            profile: User soul profile.
            limit: Maximum results.

        Returns:
            Discovered content list.
        """
        # TODO: Fetch trending/ranking from relevant categories
        # TODO: Filter by soul-based relevance
        return []


class RelatedChainStrategy(DiscoveryStrategy):
    """Discover content by following related recommendation chains."""

    @property
    def name(self) -> str:
        return "related_chain"

    async def discover(
        self, profile: SoulProfile, limit: int = 20
    ) -> list[DiscoveredContent]:
        """Start from known good content and explore related chains.

        Args:
            profile: User soul profile.
            limit: Maximum results.

        Returns:
            Discovered content list.
        """
        # TODO: Start from recently liked/high-rated content
        # TODO: Follow related recommendations iteratively
        # TODO: Score each step against soul profile
        return []


class ExploreStrategy(DiscoveryStrategy):
    """Cross-domain surprise discovery — find the unexpected."""

    @property
    def name(self) -> str:
        return "explore"

    async def discover(
        self, profile: SoulProfile, limit: int = 20
    ) -> list[DiscoveredContent]:
        """Deliberately explore domains the user hasn't tried.

        Uses the soul profile's deep needs and latent interests
        to hypothesize about what new domains might resonate.

        Args:
            profile: User soul profile.
            limit: Maximum results.

        Returns:
            Discovered content list.
        """
        # TODO: Use LLM to hypothesize new domain interests from soul
        # TODO: Search those domains
        # TODO: Score with extra weight for novelty
        return []
