"""Verzerrende und färbende Effekte."""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, lfilter

from ...params import Param
from .base import Effect
from .tone import SosFilter, db_to_gain


class Saturation(Effect):
    """Sanfte Röhren-/Band-Sättigung mit geradzahligen Obertönen."""

    id = "saturation"
    label = "Saturation"
    params = (
        Param("drive", "Drive", 0, 1, 0.4),
        Param("warmth", "Wärme", 0, 1, 0.5),
        Param("mix", "Mix", 0, 1, 1.0),
    )

    def process(self, x):
        v = self.values
        gain = 1.0 + 9.0 * v["drive"]
        bias = 0.35 * v["warmth"]
        wet = (np.tanh(gain * x + bias) - np.tanh(bias)) / np.tanh(gain) * (0.6 + 0.4 / gain) * 1.4
        return self.blend(x, wet, v["mix"])


class Distortion(Effect):
    id = "distortion"
    label = "Distortion"
    params = (
        Param("drive", "Drive", 0, 48, 18, "dB", 0.5),
        Param("mode", "Charakter", choices=("Weich", "Hart", "Fold")),
        Param("tone", "Tone", 500, 16000, 6000, "Hz", 1, log=True),
        Param("mix", "Mix", 0, 1, 1.0),
    )

    def configure(self):
        if not hasattr(self, "_tone"):
            self._tone = SosFilter()
        self._tone.set(butter(2, self.values["tone"], "lowpass", fs=self.sr, output="sos"))

    def process(self, x):
        v = self.values
        gain = db_to_gain(v["drive"])
        driven = gain * x
        mode = int(v["mode"])
        if mode == 0:
            wet = np.tanh(driven)
        elif mode == 1:
            wet = np.clip(driven, -1.0, 1.0)
        else:
            wet = np.sin(driven * np.pi / 2)
        wet = self._tone.process(wet) * gain**-0.35
        return self.blend(x, wet, v["mix"])


class Bitcrusher(Effect):
    """Reduziert Bittiefe und Abtastrate (Sample & Hold)."""

    id = "bitcrusher"
    label = "Bitcrusher"
    params = (
        Param("bits", "Bittiefe", 2, 16, 8, "Bit", 1),
        Param("rate", "Abtastrate", 500, 48000, 11000, "Hz", 1, log=True),
        Param("mix", "Mix", 0, 1, 1.0),
    )

    def __init__(self, sample_rate):
        self._count = 0
        self._held = 0.0
        super().__init__(sample_rate)

    def process(self, x):
        v = self.values
        factor = max(self.sr / v["rate"], 1.0)
        n = len(x)
        group = np.floor((self._count + np.arange(n)) / factor)
        prev = np.floor((self._count - 1) / factor) if self._count else -1.0
        is_new = np.diff(group, prepend=prev) > 0
        idx = np.maximum.accumulate(np.where(is_new, np.arange(n), -1))
        wet = np.where(idx >= 0, x[np.maximum(idx, 0)], self._held)
        self._held = float(wet[-1]) if n else self._held
        self._count += n
        levels = 2.0 ** (v["bits"] - 1)
        wet = np.round(wet * levels) / levels
        return self.blend(x, wet, v["mix"])


class RingModulator(Effect):
    id = "ringmod"
    label = "Ring Modulation"
    params = (
        Param("freq", "Frequenz", 10, 3000, 120, "Hz", 1, log=True),
        Param("mix", "Mix", 0, 1, 0.6),
    )

    def __init__(self, sample_rate):
        self._phase = 0.0
        super().__init__(sample_rate)

    def process(self, x):
        step = 2 * np.pi * self.values["freq"] / self.sr
        phase = self._phase + step * np.arange(len(x))
        self._phase = (self._phase + step * len(x)) % (2 * np.pi)
        return self.blend(x, x * np.sin(phase), self.values["mix"])


class Tremolo(Effect):
    id = "tremolo"
    label = "Tremolo"
    params = (
        Param("rate", "Tempo", 0.2, 20, 5, "Hz", 0.1),
        Param("depth", "Tiefe", 0, 1, 0.5),
    )

    def __init__(self, sample_rate):
        self._phase = 0.0
        super().__init__(sample_rate)

    def process(self, x):
        step = 2 * np.pi * self.values["rate"] / self.sr
        phase = self._phase + step * np.arange(len(x))
        self._phase = (self._phase + step * len(x)) % (2 * np.pi)
        return x * (1.0 - self.values["depth"] * (0.5 + 0.5 * np.sin(phase)))


class Noise(Effect):
    """Funkrauschen bzw. Knistern, das dem Signal unterlegt wird."""

    id = "noise"
    label = "Rauschen"
    params = (
        Param("level", "Pegel", -70, -10, -40, "dB", 0.5),
        Param("kind", "Art", choices=("Funkrauschen", "Knistern")),
    )

    def __init__(self, sample_rate):
        self._rng = np.random.default_rng(3)
        self._band = SosFilter()
        self._band.set(butter(2, [700, 5000], "bandpass", fs=sample_rate, output="sos"))
        self._zi = np.zeros(1)
        super().__init__(sample_rate)

    def process(self, x):
        n = len(x)
        noise = self._band.process(self._rng.standard_normal(n)) * 1.6
        if int(self.values["kind"]) == 1:
            clicks = (self._rng.random(n) < 0.0012) * self._rng.standard_normal(n) * 14.0
            clicks, self._zi = lfilter([0.35], [1.0, -0.65], clicks, zi=self._zi)
            noise = 0.35 * noise + clicks
        return x + noise * db_to_gain(self.values["level"])
