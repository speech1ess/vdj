# core/models/enums.py

from enum import Enum


# Тональности
class MusicalKey(Enum):
    C = "C"
    C_sharp = "C#"
    C_sharp_alt = "C_sharp"
    D = "D"
    D_sharp = "D#"
    D_sharp_alt = "D_sharp"
    E = "E"
    F = "F"
    F_sharp = "F#"
    F_sharp_alt = "F_sharp"
    G = "G"
    G_sharp = "G#"
    G_sharp_alt = "G_sharp"
    A = "A"
    A_sharp = "A#"
    A_sharp_alt = "A_sharp"
    B = "B"


# Аудиоформаты
class AudioFormat(Enum):
    MP3 = "MP3"
    FLAC = "FLAC"
    AIFF = "AIFF"
    AIF = "AIF"
