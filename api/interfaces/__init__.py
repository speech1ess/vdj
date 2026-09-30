from typing import Any, Dict, Optional  # noqa: UP035

from core.services.logging import get_logger

logger = get_logger("PlaylistAI.APIInterfaces")


class DiscogsAPI:
    """[Stub] Интеграционный шлюз к Discogs API."""

    def __init__(self, token: Optional[str] = None) -> None:
        self.token = token
        logger.warning("DiscogsAPI initialized in STUB mode. Network calls disabled.")

    def search_release(self, query: str) -> Dict[str, Any]:
        logger.info(f"Discogs stub search: {query}")
        return {}


class MusicBrainzAPI:
    """[Stub] Интеграционный шлюз к MusicBrainz API."""

    def __init__(self, user_agent: Optional[str] = None) -> None:
        self.user_agent = user_agent
        logger.warning("MusicBrainzAPI initialized in STUB mode. Network calls disabled.")

    def search_artist(self, query: str) -> dict[str, Any]:
        logger.info(f"MusicBrainz stub search: {query}")
        return {}


__all__ = [
    "DiscogsAPI",
    "MusicBrainzAPI",
]
