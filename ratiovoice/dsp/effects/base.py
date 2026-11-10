"""Basisklassen für Streaming-Effekte.

Alle Effekte verarbeiten Mono-Blöcke (float32) beliebiger Länge und behalten
ihren Zustand zwischen den Aufrufen. Dadurch läuft dieselbe Implementierung
in der Echtzeit-Wiedergabe, im Live-Mikrofonbetrieb und beim Export.
"""

from __future__ import annotations

import numpy as np

from ...params import Param, sanitize


class Effect:
    """Ein Glied der Effektkette."""

    id: str = ""
    label: str = ""
    params: tuple[Param, ...] = ()
    latency: int = 0  # Verzögerung in Samples (wird beim Export ausgeglichen)
    tail_seconds: float = 0.0  # Ausklang nach Signalende (Hall, Echo)

    def __init__(self, sample_rate: int):
        self.sr = sample_rate
        self.values: dict[str, float] = {}
        self.set_params({})

    def set_params(self, values: dict | None) -> None:
        new = sanitize(self.params, values)
        if new != self.values:
            self.values = new
            self.configure()

    def configure(self) -> None:
        """Wird nach jeder Parameteränderung aufgerufen (Koeffizienten berechnen)."""

    def process(self, x: np.ndarray) -> np.ndarray:
        raise NotImplementedError

    @staticmethod
    def blend(dry: np.ndarray, wet: np.ndarray, mix: float) -> np.ndarray:
        return dry * (1.0 - mix) + wet * mix


class PedalboardEffect(Effect):
    """Effekt, der ein Plugin aus Spotifys ``pedalboard`` (JUCE-DSP) kapselt."""

    def make_plugin(self):
        raise NotImplementedError

    def apply(self, plugin) -> None:
        raise NotImplementedError

    def configure(self) -> None:
        if not hasattr(self, "_plugin"):
            self._plugin = self.make_plugin()
        self.apply(self._plugin)

    def process(self, x: np.ndarray) -> np.ndarray:
        y = self._plugin(x.reshape(1, -1), self.sr, reset=False).reshape(-1)
        if len(y) != len(x):  # Sicherheitsnetz, sollte bei diesen Plugins nie eintreten
            y = np.resize(y, len(x))
        return y


class StreamingOLA:
    """Überlappende Frame-Verarbeitung (STFT) für blockweises Streaming.

    ``process`` liefert genau so viele Samples zurück, wie hineingegeben
    wurden; das Ergebnis ist um ``n_fft`` Samples verzögert.
    """

    def __init__(self, n_fft: int):
        self.n_fft = n_fft
        self.window = np.hanning(n_fft + 1)[:-1]
        self._in = np.zeros(0)
        self._acc = np.zeros(n_fft)
        self._out = np.zeros(n_fft)

    def process(self, x: np.ndarray, hop: int, frame_fn) -> np.ndarray:
        self._in = np.concatenate([self._in, x])
        produced = [self._out]
        n = self.n_fft
        while len(self._in) >= n:
            self._acc += frame_fn(self._in[:n] * self.window)
            produced.append(self._acc[:hop].copy())
            self._acc = np.concatenate([self._acc[hop:], np.zeros(hop)])
            self._in = self._in[hop:]
        out = np.concatenate(produced) if len(produced) > 1 else self._out
        self._out = out[len(x) :]
        return out[: len(x)]


class DelayLine:
    """Feste Verzögerung, um ein trockenes Signal an latenzbehaftete Effekte anzugleichen."""

    def __init__(self, delay: int):
        self._buf = np.zeros(delay)

    def process(self, x: np.ndarray) -> np.ndarray:
        joined = np.concatenate([self._buf, x])
        self._buf = joined[len(x) :]
        return joined[: len(x)]
