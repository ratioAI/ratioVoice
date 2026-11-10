"""Datenmodell der aktuellen Stimmeinstellung.

Eine Einstellung ist ein schlichtes, JSON-serialisierbares Dict::

    {"profile": "Radio-Moderator",
     "voice":   {"pitch": -2.0, "formant": -1.0, ...},
     "chain":   [{"id": "eq", "on": True, "params": {...}}, ...],
     "ai":      {"model": "", "transpose": 0}}

Dasselbe Format dient für Bibliotheksprofile, eigene Presets und Undo/Redo.
"""

from __future__ import annotations

import copy

from .dsp.chain import normalize_spec
from .dsp.voice_engine import VOICE_PARAMS
from .params import sanitize

NEUTRAL_NAME = "Original (unverändert)"


def normalize(settings: dict | None) -> dict:
    settings = settings or {}
    ai = settings.get("ai") or {}
    return {
        "profile": str(settings.get("profile", NEUTRAL_NAME)),
        "voice": sanitize(VOICE_PARAMS, settings.get("voice")),
        "chain": normalize_spec(settings.get("chain")),
        "ai": {"model": str(ai.get("model", "")), "transpose": int(ai.get("transpose", 0))},
    }


def neutral() -> dict:
    return normalize({})


def clone(settings: dict) -> dict:
    return copy.deepcopy(settings)
