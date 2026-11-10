"""Spektrale Effekte: Roboter, Vocoder, Glitch."""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, lfilter, sosfilt

from ...params import Param
from .base import DelayLine, Effect, StreamingOLA

_N_FFT = 2048


class Robot(Effect):
    """Klassische Robotisierung: Phase jedes STFT-Frames auf null setzen.

    Dadurch wird jedes Frame zu einem Impuls; die Frame-Rate bestimmt die
    (konstante) Tonhöhe, die Formanten der Sprache bleiben erhalten.
    """

    id = "robot"
    label = "Roboter"
    latency = _N_FFT
    params = (
        Param("pitch", "Tonhöhe", 40, 400, 110, "Hz", 1, log=True),
        Param("mix", "Mix", 0, 1, 1.0),
    )

    def __init__(self, sample_rate):
        self._ola = StreamingOLA(_N_FFT)
        self._dry = DelayLine(_N_FFT)
        super().__init__(sample_rate)

    def _frame(self, frame):
        pulse = np.fft.fftshift(np.fft.irfft(np.abs(np.fft.rfft(frame))))
        return pulse * self._ola.window

    def process(self, x):
        hop = int(np.clip(self.sr / self.values["pitch"], 64, _N_FFT // 2))
        wet = self._ola.process(x, hop, self._frame) * (hop / (0.375 * _N_FFT)) * 1.6
        return self.blend(self._dry.process(x), wet, self.values["mix"])


class Vocoder(Effect):
    """Kanal-Vocoder: Die Sprache formt das Spektrum eines Synthesizer-Trägers."""

    id = "vocoder"
    label = "Vocoder"
    params = (
        Param("carrier", "Träger", choices=("Sägezahn", "Puls", "Rauschen", "Akkord")),
        Param("pitch", "Tonhöhe", 40, 500, 110, "Hz", 1, log=True),
        Param("bands", "Bänder", 6, 32, 18, "", 1),
        Param("mix", "Mix", 0, 1, 1.0),
    )
    _CHORD = (1.0, 1.26, 1.498, 2.0)

    def __init__(self, sample_rate):
        self._phases = np.zeros(len(self._CHORD))
        self._rng = np.random.default_rng(5)
        self._n_bands = 0
        self._level_in = self._level_out = 1e-3
        super().__init__(sample_rate)

    def configure(self):
        n = int(self.values["bands"])
        if n == self._n_bands:
            return
        self._n_bands = n
        edges = np.geomspace(90.0, 11000.0, n + 1)
        self._sos = [butter(2, [lo, hi], "bandpass", fs=self.sr, output="sos") for lo, hi in zip(edges, edges[1:])]
        self._zi_mod = [np.zeros((s.shape[0], 2)) for s in self._sos]
        self._zi_car = [np.zeros((s.shape[0], 2)) for s in self._sos]
        self._zi_env = [np.zeros(1) for _ in self._sos]
        pole = np.exp(-2 * np.pi * 45.0 / self.sr)
        self._env_b, self._env_a = [1.0 - pole], [1.0, -pole]

    def _carrier(self, n):
        kind = int(self.values["carrier"])
        noise = self._rng.standard_normal(n)
        if kind == 2:
            return noise * 0.5
        ratios = self._CHORD if kind == 3 else self._CHORD[:1]
        ramp = np.arange(1, n + 1)
        signal = np.zeros(n)
        for i, ratio in enumerate(ratios):
            step = self.values["pitch"] * ratio / self.sr
            phase = (self._phases[i] + step * ramp) % 1.0
            self._phases[i] = phase[-1]
            signal += (phase < 0.25) * 2.0 - 0.5 if kind == 1 else 2.0 * phase - 1.0
        # Etwas Rauschen im Träger hält Zischlaute (s, sch, f) verständlich.
        return signal / len(ratios) + 0.12 * noise

    def process(self, x):
        carrier = self._carrier(len(x))
        wet = np.zeros(len(x))
        for i, sos in enumerate(self._sos):
            band, self._zi_mod[i] = sosfilt(sos, x, zi=self._zi_mod[i])
            env, self._zi_env[i] = lfilter(self._env_b, self._env_a, np.abs(band), zi=self._zi_env[i])
            car, self._zi_car[i] = sosfilt(sos, carrier, zi=self._zi_car[i])
            wet += car * env
        # Lautstärke des Ergebnisses träge an die Eingangslautstärke angleichen.
        self._level_in = 0.9 * self._level_in + 0.1 * np.sqrt(np.mean(x**2) + 1e-12)
        self._level_out = 0.9 * self._level_out + 0.1 * np.sqrt(np.mean(wet**2) + 1e-12)
        wet *= min(self._level_in / self._level_out, 50.0)
        return self.blend(x, wet, self.values["mix"])


class Glitch(Effect):
    """Stotter-Effekt: wiederholt zufällig kurze Abschnitte, teils rückwärts oder verkürzt."""

    id = "glitch"
    label = "Glitch"
    params = (
        Param("amount", "Häufigkeit", 0, 1, 0.4),
        Param("slice", "Schnipsel-Länge", 20, 400, 90, "ms", 1),
    )

    def __init__(self, sample_rate):
        self._rng = np.random.default_rng(9)
        self._history = np.zeros(0)
        self._slice = None
        self._pos = self._reps = 0
        self._roll = False
        self._until = 0
        super().__init__(sample_rate)

    def _start_stutter(self, length):
        piece = self._history[-length:].copy()
        mode = self._rng.integers(0, 3)
        if mode == 1:
            piece = piece[::-1].copy()
        fade = min(96, length // 4)
        ramp = np.linspace(0.0, 1.0, fade)
        piece[:fade] *= ramp
        piece[-fade:] *= ramp[::-1]
        self._slice, self._pos = piece, 0
        self._reps = int(self._rng.integers(2, 6))
        self._roll = mode == 2

    def process(self, x):
        length = int(self.values["slice"] / 1000.0 * self.sr)
        out = x.astype(np.float64, copy=True)
        i, n = 0, len(x)
        while i < n:
            if self._slice is None:
                if self._until <= 0:
                    self._until = length
                m = min(n - i, self._until)
                self._history = np.concatenate([self._history, x[i : i + m]])[-self.sr :]
                self._until -= m
                i += m
                if self._until == 0 and len(self._history) >= length and self._rng.random() < self.values["amount"]:
                    self._start_stutter(length)
            else:
                m = min(n - i, len(self._slice) - self._pos)
                out[i : i + m] = self._slice[self._pos : self._pos + m]
                self._pos += m
                i += m
                if self._pos >= len(self._slice):
                    self._pos = 0
                    self._reps -= 1
                    if self._roll and len(self._slice) > 600:
                        self._slice = self._slice[: len(self._slice) // 2]
                    if self._reps <= 0:
                        self._slice = None
        return out
