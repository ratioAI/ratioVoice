"""Zentrale Konstanten und Pfade."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "RatioVoice"

# Das gesamte Projekt arbeitet intern mono mit fester Abtastrate.
# Importierte Dateien werden beim Laden darauf umgerechnet.
SAMPLE_RATE = 48_000
BLOCK_SIZE = 512

MAX_CLIP_SECONDS = 10 * 60


def user_data_dir() -> Path:
    """Ordner für Presets, Favoriten, Aufnahmen und KI-Modelle."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def recordings_dir() -> Path:
    path = user_data_dir() / "Aufnahmen"
    path.mkdir(exist_ok=True)
    return path


def models_dir() -> Path:
    path = user_data_dir() / "KI-Modelle"
    path.mkdir(exist_ok=True)
    return path
