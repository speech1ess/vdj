# 2025/05/08
# @authors: <GROK> & <speech1ess>

from typing import Any

from core.models.audiofile import AudioFile
from core.repositories.base_rep import BaseRepository


class AudioFileRepository(BaseRepository):
    """Высокопроизводительный репозиторий для персистентности AudioFile."""

    def __init__(self, configurator: Any, cachemanager: Any = None) -> None:
        # Устранен баг с передачей удаленного софварно аргумента log_callback
        super().__init__(configurator, cachemanager)

    def _save_audiofiles(self, db: Any, audiofile_cache: dict[str, Any]) -> dict[str, int]:
        """
        Сохраняет аудиофайлы из кэша в базу, проверяя дубликаты по file_path и hash.
        Оптимизировано под высокий throughput и кроссплатформенность (Windows/Linux).
        """
        self.logger.debug(f"Пакетное сохранение {len(audiofile_cache)} аудиофайлов.")
        audiofile_ids: dict[str, int] = {}
        original_ids = self.cacheops.get_ids(audiofile_cache, "audiofile")

        composite_keys = []
        for file_path, audiofile in audiofile_cache.items():
            file_hash = audiofile.hash or "null"
            # АРХИТЕКТУРНОЕ ИСПРАВЛЕНИЕ ДЛЯ WINDOWS:
            # Заменяем двоеточие в букве диска (напр. 'C:' -> 'C_DRIVE') или экранируем,
            # чтобы BaseRepository._check_by_composite не ломал сплит по двоеточию.
            safe_path = file_path.replace(":", "_DRIVE_") if ":" in file_path else file_path
            composite_keys.append(f"{safe_path}:{file_hash}")

        if not composite_keys:
            self.logger.debug("Кэш аудиофайлов пуст, нечего сохранять.")
            return audiofile_ids

        # Проверка существования батча за один SQL-запрос (минимизируем round-trips к БД)
        existing = self._check_exist(db, AudioFile, composite_keys, ["file_path", "hash"])
        self.logger.debug(f"Найдено существующих записей AudioFile в БД: {len(existing)}")

        for file_path, audiofile in audiofile_cache.items():
            file_hash = audiofile.hash or "null"
            safe_path = file_path.replace(":", "_DRIVE_") if ":" in file_path else file_path
            key = f"{safe_path}:{file_hash}"

            # ОПТИМИЗАЦИЯ ПАМЯТИ И CPU:
            # Избегаем тяжелого и медленного deepcopy.
            # Мутируем ссылки управляемо, временно отключая обратную связь со списком треков.
            original_tracks = audiofile.tracks
            audiofile.tracks = []

            try:
                file_id, updated = self._save_or_update(
                    db,
                    audiofile,
                    key,
                    existing,
                    exclude_fields=["file_path", "id", "hash", "date_added"],
                )
            finally:
                # Всегда возвращаем треки на место в объекте кэша
                audiofile.tracks = original_tracks

            audiofile_ids[str(file_path)] = file_id
            audiofile.id = file_id
            self.logger.debug(f"{'Обновлен': 'Сохранен'} аудиофайл: {file_path} [ID: {file_id}]")

        # Синхронизация промежуточного кэша
        self.cacheops.update_cache(audiofile_cache, "audiofile", audiofile_ids, original_ids)
        return audiofile_ids

    def save_audiofiles_batch(self, db: Any) -> dict[str, int]:
        """Пакетное сохранение аудиофайлов из кэша с фиксацией транзакции (Unit of Work)."""
        audiofile_cache, _ = self.cache.get_cache("audiofile")
        if not audiofile_cache:
            return {}

        audiofile_ids = self._save_audiofiles(db, audiofile_cache)
        db.commit()  # Единая транзакция на весь пакет (обеспечивает максимальный I/O throughput)

        return audiofile_ids
