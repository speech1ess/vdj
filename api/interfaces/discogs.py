from typing import Any, Optional, dict

from core.services.logging import get_logger

logger = get_logger("PlaylistAI.DiscogsAPI")


class DiscogsAPI:
    """
    Интеграционный шлюз к Discogs API.
    [Stub] Заглушка на период bootstrapping-фазы.
    """

    def __init__(self, token: Optional[str] = None) -> None:
        self.token = token
        logger.warning("DiscogsAPI initialized in STUB mode. Real network calls are disabled.")

    def search_release(self, query: str) -> dict[str, Any]:
        logger.info(f"Stub search executed for query: {query}")
        return {}
