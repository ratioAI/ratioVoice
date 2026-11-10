"""Klangformung und Dynamik: Gate, Equalizer, Kompressor, Ausgangspegel."""

from __future__ import annotations

import numpy as np
import pedalboard as pb
from scipy.signal import butter, sosfilt

from ...params import Param
from .base import Effect, PedalboardEffect


def db_to_gain(db: float) -> float:
    return 10.0 ** (db / 20.0)


def _biquad(kind: str, freq: float, sr: int, gain_db: float = 0.0, q: float = 0.707) -> np.ndarray:
    """Biquad-Koeffizienten nach dem RBJ Audio EQ Cookbook als SOS-Zeile."""
    a = 10.0 ** (gain_db / 40.0)
    w0 = 2 * np.pi * min(freq, sr * 0.45) / sr
    cos, sin = np.cos(w0), np.sin(w0)
    alpha = sin / (2 * q)
    if kind == "peak":
        b = [1 + alpha * a, -2 * cos, 1 - alpha * a]
        den = [1 + alpha / a, -2 * cos, 1 - alpha / a]
    else:
        root = 2 * np.sqrt(a) * alpha
        sign = 1.0 if kind == "lowshelf" else -1.0
        b = [
            a * ((a + 1) - sign * (a - 1) * cos + root),
            sign * 2 * a * ((a - 1) - sign * (a + 1) * cos),
            a * ((a + 1) - sign * (a - 1) * cos - root),
        ]
        den = [
            (a + 1) + sign * (a - 1) * cos + root,
            -sign * 2 * ((a - 1) + sign * (a + 1) * cos),
            (a + 1) + sign * (a - 1) * cos - root,
        ]
    return np.array([b[0], b[1], b[2], den[0], den[1], den[2]]) / den[0]


class SosFilter:
    """Kaskade von Biquads mit Zustand; Koeffizienten können live getauscht werden."""

    def __init__(self):
        self._sos = None
        self._zi = None

    def set(self, sos: np.ndarray | None) -> None:
        if sos is None or len(sos) == 0:
            self._sos = self._zi = None
            return
        if self._zi is None or self._zi.shape[0] != sos.shape[0]:
            self._zi = np.zeros((sos.shape[0], 2))
        self._sos = sos

    def process(self, x: np.ndarray) -> np.ndarray:
        if self._sos is None:
            return x
        y, self._zi = sosfilt(self._sos, x, zi=self._zi)
        return y


class Gate(PedalboardEffect):
    id = "gate"
    label = "Noise Gate"
    params = (Param("threshold", "Schwelle", -80, -10, -45, "dB", 1),)

    def make_plugin(self):
        return pb.NoiseGate(ratio=8, attack_ms=2, release_ms=120)

    def apply(self, plugin):
        plugin.threshold_db = self.values["threshold"]


class Equalizer(Effect):
    id = "eq"
    label = "Equalizer"
    params = (
        Param("lowcut", "Low Cut", 20, 2000, 20, "Hz", 1, log=True),
        Param("low", "Bässe", -18, 18, 0, "dB", 0.5),
        Param("mid", "Mitten", -18, 18, 0, "dB", 0.5),
        Param("mid_freq", "Mitten-Frequenz", 200, 6000, 1200, "Hz", 1, log=True),
        Param("high", "Höhen", -18, 18, 0, "dB", 0.5),
        Param("highcut", "High Cut", 800, 20000, 20000, "Hz", 1, log=True),
    )

    def configure(self):
        if not hasattr(self, "_filter"):
            self._filter = SosFilter()
        v, sections = self.values, []
        if v["lowcut"] > 25:
            sections.append(butter(4, v["lowcut"], "highpass", fs=self.sr, output="sos"))
        if v["low"]:
            sections.append(_biquad("lowshelf", 180, self.sr, v["low"])[None])
        if v["mid"]:
            sections.append(_biquad("peak", v["mid_freq"], self.sr, v["mid"], q=0.9)[None])
        if v["high"]:
            sections.append(_biquad("highshelf", 5500, self.sr, v["high"])[None])
        if v["highcut"] < 19500:
            sections.append(butter(4, v["highcut"], "lowpass", fs=self.sr, output="sos"))
        self._filter.set(np.concatenate(sections) if sections else None)

    def process(self, x):
        return self._filter.process(x)


class Compressor(PedalboardEffect):
    id = "compressor"
    label = "Kompressor"
    params = (
        Param("threshold", "Schwelle", -50, 0, -20, "dB", 0.5),
        Param("ratio", "Ratio", 1, 20, 4, ":1", 0.1),
        Param("attack", "Attack", 0.5, 100, 5, "ms", 0.5),
        Param("release", "Release", 20, 800, 120, "ms", 1),
        Param("makeup", "Aufholverstärkung", 0, 24, 4, "dB", 0.5),
    )

    def make_plugin(self):
        return pb.Compressor()

    def apply(self, plugin):
        v = self.values
        plugin.threshold_db = v["threshold"]
        plugin.ratio = v["ratio"]
        plugin.attack_ms = v["attack"]
        plugin.release_ms = v["release"]

    def process(self, x):
        return super().process(x) * db_to_gain(self.values["makeup"])


class Output(Effect):
    id = "output"
    label = "Ausgangspegel"
    params = (Param("gain", "Pegel", -24, 24, 0, "dB", 0.5),)

    def process(self, x):
        return x * db_to_gain(self.values["gain"])
