# MetadataExtractor — Извлечение и унификация аудиометаданных

## 📦 Назначение

Класс `MetadataExtractor` отвечает за извлечение максимально полных и унифицированных метаданных из аудиофайлов форматов MP3, FLAC, AIFF, с возможной интеграцией данных из CUE-файлов.

---

## 📂 Поддерживаемые форматы

| Формат | Поддержка | Комментарий |
|--------|-----------|-------------|
| MP3    | ✅         | ID3 (через mutagen) |
| FLAC   | ✅         | Vorbis Comments |
| AIFF   | ✅         | AIFF + ID3 |
| CUE    | ✅         | Полная поддержка, включая мультитреки |

---

## 🔧 Использование

### Инициализация

```python
extractor = MetadataExtractor()
```

### Обычное извлечение

```python
metadata = extractor.extract("/path/to/track.flac")
```

### Извлечение с учётом CUE

```python
metadata = extractor.extract_with_cue("/path/to/album.flac", cue_data, track_index=1)
```

---

## 🧠 Ключевые особенности

### ✅ Унифицированный маппинг `UNIFIED_TAGS`

Все извлечённые теги приводятся к стандартным ключам (`title`, `artist`, `album`, `track`, `genre`, `bpm`, и т.д.) независимо от формата.

### ✅ Интеграция с CUE

Поддерживается два сценария:

- Мультитрек: один файл, несколько `TRACK` в `.cue`
- Сингл-трек: отдельные файлы на каждый `TRACK`

`track_index` определяет, какой трек использовать.

### ✅ Приоритет данных из CUE

Если `cue_data` есть, она будет **приоритетнее**, кроме `duration`, который берётся из файла.

---

## 🧪 Методы

### extract(file_path: str, cue_data: Optional[dict] = None) → dict

Извлекает метаданные, optionally слияние с cue.

### extract_with_cue(file_path: str, cue_data: dict, track_index: int = 0) → dict

Полная логика объединения CUE и mutagen.

### merge_metadata(file_data, cue_data) → dict

Вспомогательный метод объединения данных по приоритету `UNIFIED_TAGS`.

---

## 🧱 Расширение

- Можно легко добавить новые форматы (`WAV`, `M4A`) через `_extract_*` методы
- `UNIFIED_TAGS` вынесен в отдельный файл и может переиспользоваться

---

## 📝 Пример структуры результата

```json
{
  "title": "Intro",
  "artist": "Some Artist",
  "album": "Best Album",
  "track": 1,
  "genre": "Electronic",
  "bpm": 128,
  "duration": 321,
  "start_time": 15.2
}
```

---

## 🧰 Зависимости

- [mutagen](https://mutagen.readthedocs.io/en/latest/) — извлечение тегов
- CUE парсится отдельно через `CueParser`

---

## 🧪 Тестирование

Для моков можно использовать `unittest.mock` с `mutagen.File` и поддельными тегами.

---

(c) PlaylistAI Metadata Engine