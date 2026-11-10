"""Laden und Speichern von Audiodateien (WAV, MP3, OGG, FLAC)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from .config import SAMPLE_RATE

IMPORT_FILTER = "Audiodateien (*.wav *.mp3 *.ogg *.flac);;Alle Dateien (*)"
EXPORT_FILTERS = {"WAV (*.wav)": ".wav", "MP3 (*.mp3)": ".mp3", "OGG Vorbis (*.ogg)": ".ogg"}
_WRITE_OPTIONS = {
    ".wav": {"format": "WAV", "subtype": "PCM_24"},
    ".flac": {"format": "FLAC", "subtype": "PCM_24"},
    ".mp3": {"format": "MP3", "subtype": "MPEG_LAYER_III"},
    ".ogg": {"format": "OGG", "subtype": "VORBIS"},
}


def load(path: str | Path) -> np.ndarray:
    """Liest eine Datei und liefert Mono-float32 in der Projekt-Abtastrate."""
    data, rate = sf.read(str(path), dtype="float32", always_2d=True)
    mono = data.mean(axis=1)
    if rate != SAMPLE_RATE:
        divisor = np.gcd(int(rate), SAMPLE_RATE)
        mono = resample_poly(mono, SAMPLE_RATE // divisor, int(rate) // divisor)
    return np.ascontiguousarray(mono, dtype=np.float32)


def save(path: str | Path, audio: np.ndarray) -> Path:
    """Schreibt ``audio`` im Format der Dateiendung (Standard: WAV)."""
    path = Path(path)
    if path.suffix.lower() not in _WRITE_OPTIONS:
        path = path.with_suffix(".wav")
    options = _WRITE_OPTIONS[path.suffix.lower()]
    clipped = np.clip(audio, -1.0, 1.0).astype(np.float32)
    # Blockweise schreiben: libsndfile verträgt bei OGG/MP3 keine sehr großen Einzelpuffer.
    with sf.SoundFile(str(path), "w", samplerate=SAMPLE_RATE, channels=1, **options) as handle:
        for start in range(0, len(clipped), SAMPLE_RATE):
            handle.write(clipped[start : start + SAMPLE_RATE])
    return path


def resample(audio: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate:
        return audio
    divisor = np.gcd(src_rate, dst_rate)
    return resample_poly(audio, dst_rate // divisor, src_rate // divisor).astype(np.float32)
