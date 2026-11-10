"""Rechenprozess für alles, was nicht in Echtzeit laufen muss.

Analyse, Stimm-Synthese, KI-Umwandlung und das Offline-Rendern laufen in
einem eigenen Prozess. So blockieren sie weder die Oberfläche noch den
Audio-Callback (Pythons GIL gilt nur pro Prozess).

Der Prozess hält den Zustand der aktuellen Aufnahme (Analyse, zuletzt
synthetisierte Stimme), damit bei Regleränderungen nur die Reglerwerte
übertragen werden müssen.
"""

from __future__ import annotations

import multiprocessing as mp
from concurrent.futures import Future, ProcessPoolExecutor

import numpy as np

from .config import SAMPLE_RATE

_state: dict = {}


def _analyze(audio: np.ndarray) -> int:
    from .dsp import voice_engine

    _state["analysis"] = voice_engine.analyze(audio, SAMPLE_RATE)
    _state.pop("voiced", None)
    return len(audio)


def _synthesize(voice: dict) -> np.ndarray:
    from .dsp import voice_engine

    _state["voiced"] = voice_engine.synthesize(_state["analysis"], voice)
    return _state["voiced"]


def _render(spec: list[dict]) -> np.ndarray:
    from .dsp.chain import render

    return render(_state["voiced"], spec, SAMPLE_RATE)


def _convert(audio: np.ndarray, model: str, transpose: int) -> np.ndarray:
    from .ai.rvc import RvcConverter

    cached = _state.get("converter")
    if cached is None or cached[0] != model:
        cached = _state["converter"] = (model, RvcConverter(model))
    return cached[1].convert(audio, transpose)


class Worker:
    """Dünne Hülle um einen Ein-Prozess-Pool; Aufträge laufen strikt nacheinander."""

    def __init__(self):
        self._pool = ProcessPoolExecutor(max_workers=1, mp_context=mp.get_context("spawn"))

    def analyze(self, audio: np.ndarray) -> Future:
        return self._pool.submit(_analyze, audio)

    def synthesize(self, voice: dict) -> Future:
        return self._pool.submit(_synthesize, voice)

    def render(self, spec: list[dict]) -> Future:
        return self._pool.submit(_render, spec)

    def convert(self, audio: np.ndarray, model: str, transpose: int) -> Future:
        return self._pool.submit(_convert, audio, model, transpose)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
