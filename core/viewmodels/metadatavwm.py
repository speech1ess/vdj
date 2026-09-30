# core/viewmodels/metadata_query_vwm.py
from api.interfaces import (
    DiscogsAPI,  # Предполагаемый сервис
    MusicBrainzAPI,  # Предполагаемый сервис
)
from core.repositories.track_rep import TrackRepository


class MetadataQueryViewModel:
    def __init__(
        self, track_repo: TrackRepository, discogs_api: DiscogsAPI, musicbrainz_api: MusicBrainzAPI
    ):
        self.track_repo = track_repo
        self.discogs_api = discogs_api
        self.musicbrainz_api = musicbrainz_api

    def query_metadata(self, type: str, state: str, name: str = None, api: str = "discogs"):
        # Фильтруем локальные данные
        if type == "трек":
            tracks = self.track_repo.get_tracks_with_missing(state)
        elif type == "альбом":
            tracks = self.track_repo.get_albums_with_missing(state)
        elif type == "артист":
            tracks = self.track_repo.get_artists_with_missing(state)

        # Запрос к API
        api_service = self.discogs_api if api == "discogs" else self.musicbrainz_api
        results = []
        for track in tracks[:10]:  # Ограничим для теста
            query = name or track.get("title", "") or track.get("artist", "")
            api_results = api_service.search(query, type=type, missing=state)
            for result in api_results:
                result["source"] = api
                results.append(result)
        return results

    def apply_metadata(self, metadata: dict):
        # Применяем метаданные к базе (логика зависит от структуры)
        pass
