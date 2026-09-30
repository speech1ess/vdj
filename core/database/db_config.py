from typing import Any

# Использование строгой типизации для seed-данных.
# Вместо CSV-строк используем нативные списки (согласуется с нашей новой JSON-моделью Genre).

BASE_GENRES: list[dict[str, Any]] = [
    {"name": "Rock"},
    {"name": "Techno"},
    {"name": "House"},
    {"name": "Jazz", "aliases": ["джаз"]},
    {"name": "Pop", "aliases": ["поп", "popular", "pop music"]},
    {"name": "Dance", "aliases": ["танцевальная музыка", "танцевальная", "dance music"]},
    {
        "name": "Electronic",
        "aliases": ["electronica", "электронная музыка", "электроника", "электронная"],
    },
    {"name": "Unknown", "aliases": ["неизвестный жанр", "unknown genre"]},
    {"name": "Hip-Hop", "aliases": ["hiphop", "hip hop"]},
    {"name": "Trip-Hop", "aliases": ["трип-хоп", "trip hop"]},
    {"name": "Ambient", "aliases": ["амбиент", "эмбиент", "ambient music"]},
    {
        "name": "Drum & Bass",
        "aliases": [
            "d&b",
            "drum&bass",
            "drum'n'bass",
            "dnb",
            "drum n bass",
            "drum and bass",
            "drum-n-bass",
        ],
        "is_composite": True,
    },
    {
        "name": "Rhythm & Blues",
        "aliases": ["r'n'b", "r & b", "rhythm and blues", "rhythm n blues", "rhythm'n'blues"],
        "is_composite": True,
    },
    {
        "name": "Rock & Roll",
        "aliases": ["rock'n'roll", "рок-н-ролл", "rock and roll", "rock n roll"],
        "is_composite": True,
    },
]

SUB_GENRES: list[dict[str, str]] = [
    {"name": "Alternative Rock", "parent_name": "Rock"},
    {"name": "Underground Hip-Hop", "parent_name": "Hip-Hop"},
    {"name": "Deep House", "parent_name": "House"},
    {"name": "Post-Rock", "parent_name": "Rock"},
    {"name": "Progressive Techno", "parent_name": "Techno"},
    {"name": "Minimal Techno", "parent_name": "Techno"},
    {"name": "Acid Jazz", "parent_name": "Jazz"},
    {"name": "Liquid Drum & Bass", "parent_name": "Drum & Bass"},
]

# Архитектурное исправление: Используем frozenset вместо list.
# Это дает O(1) time complexity при проверке вхождений в нормализаторах.
MODIFIERS: frozenset[str] = frozenset(
    [
        "underground",
        "alternative",
        "deep",
        "post",
        "uk",
        "us",
        "progressive",
        "dark",
        "minimal",
        "acid",
        "chill",
        "future",
        "liquid",
    ]
)
