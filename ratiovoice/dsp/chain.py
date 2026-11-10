"""Effektkette: geordnete Liste von Effekten plus Schutz-Limiter.

Die Kette wird als einfache Datenstruktur beschrieben (``spec``), damit sie
sich in Presets speichern und per Undo/Redo wiederherstellen lässt::

    [{"id": "eq", "on": True, "params": {"lowcut": 300}}, ...]
"""

from __future__ import annotations

import threading

import numpy as np
from ..params import sanitize
from . import effects


def normalize_spec(spec: list[dict] | None) -> list[dict]:
    """Bringt eine Kettenbeschreibung in vollständige, gültige Form."""
    result = []
    for entry in spec or []:
        cls = effects.EFFECTS.get(entry.get("id"))
        if cls is None:
            continue
        result.append({"id": cls.id, "on": bool(entry.get("on", True)), "params": sanitize(cls.params, entry.get("params"))})
    return result


_KNEE = 0.8


def soft_limit(x: np.ndarray) -> np.ndarray:
    """Schutz vor Übersteuerung: unterhalb von 0,8 unverändert, darüber weich auf < 1 begrenzt."""
    mag = np.abs(x)
    if mag.max(initial=0.0) <= _KNEE:
        return x
    over = np.tanh((mag - _KNEE) / (1.0 - _KNEE)) * (1.0 - _KNEE) + _KNEE
    return np.where(mag > _KNEE, np.sign(x) * over, x).astype(np.float32)


class Chain:
    def __init__(self, sample_rate: int):
        self.sr = sample_rate
        self._lock = threading.Lock()
        self._effects: list[effects.Effect] = []
        self._enabled: list[bool] = []

    def configure(self, spec: list[dict]) -> None:
        """Übernimmt eine Kettenbeschreibung; bestehende Effekte behalten ihren Zustand."""
        with self._lock:
            new_effects = []
            for index, entry in enumerate(spec):
                reuse = index < len(self._effects) and self._effects[index].id == entry["id"]
                fx = self._effects[index] if reuse else effects.create(entry["id"], self.sr)
                fx.set_params(entry["params"])
                new_effects.append(fx)
            self._effects = new_effects
            self._enabled = [entry.get("on", True) for entry in spec]

    @property
    def latency(self) -> int:
        return sum(fx.latency for fx, on in zip(self._effects, self._enabled) if on)

    @property
    def tail_seconds(self) -> float:
        return max((fx.tail_seconds for fx, on in zip(self._effects, self._enabled) if on), default=0.0)

    def process(self, x: np.ndarray) -> np.ndarray:
        with self._lock:
            y = x
            for fx, on in zip(self._effects, self._enabled):
                if on:
                    y = fx.process(y)
            return soft_limit(np.nan_to_num(np.asarray(y, dtype=np.float32), copy=False))


def render(audio: np.ndarray, spec: list[dict], sample_rate: int, block: int = 4096) -> np.ndarray:
    """Rechnet die Effektkette offline über ein ganzes Signal (für Export und Anzeige)."""
    chain = Chain(sample_rate)
    chain.configure(spec)
    latency = chain.latency
    tail = int(chain.tail_seconds * sample_rate)
    padded = np.concatenate([audio.astype(np.float32), np.zeros(latency + tail, dtype=np.float32)])
    out = np.concatenate([chain.process(padded[i : i + block]) for i in range(0, len(padded), block)])
    out = out[latency:]
    if tail:
        # Ausklang nur so lange behalten, wie er hörbar ist.
        loud = np.flatnonzero(np.abs(out[len(audio) :]) > 1e-4)
        out = out[: len(audio) + (loud[-1] + 1 if len(loud) else 0)]
    return out
