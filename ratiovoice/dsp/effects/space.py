"""Raum- und Zeiteffekte: Delay, Echo, Reverb."""

from __future__ import annotations

import numpy as np
import pedalboard as pb
from scipy.signal import lfilter

from ...params import Param
from .base import Effect, PedalboardEffect


class Delay(PedalboardEffect):
    """Kurzes Delay für Dopplung und Slapback."""

    id = "delay"
    label = "Delay"
    tail_seconds = 1.0
    params = (
        Param("time", "Zeit", 5, 300, 90, "ms", 1),
        Param("feedback", "Feedback", 0, 0.9, 0.2),
        Param("mix", "Mix", 0, 1, 0.3),
    )

    def make_plugin(self):
        return pb.Delay()

    def apply(self, plugin):
        v = self.values
        plugin.delay_seconds = v["time"] / 1000.0
        plugin.feedback = v["feedback"]
        plugin.mix = v["mix"]


class Echo(Effect):
    """Lange, dunkler werdende Wiederholungen (Rückkopplung mit Tiefpass)."""

    id = "echo"
    label = "Echo"
    tail_seconds = 3.0
    params = (
        Param("time", "Zeit", 100, 1500, 380, "ms", 1),
        Param("feedback", "Wiederholungen", 0, 0.9, 0.45),
        Param("damping", "Dämpfung", 0, 1, 0.4),
        Param("mix", "Mix", 0, 1, 0.35),
    )

    def __init__(self, sample_rate):
        self._buf = np.zeros(sample_rate * 2)
        self._write = 0
        self._zi = np.zeros(1)
        super().__init__(sample_rate)

    def process(self, x):
        v = self.values
        size = len(self._buf)
        delay = int(v["time"] / 1000.0 * self.sr)
        pole = 0.85 * v["damping"]
        out = np.empty(len(x))
        i = 0
        while i < len(x):
            m = min(len(x) - i, delay)
            pos = self._write + np.arange(m)
            delayed = self._buf[(pos - delay) % size]
            damped, self._zi = lfilter([1.0 - pole], [1.0, -pole], delayed, zi=self._zi)
            self._buf[pos % size] = x[i : i + m] + v["feedback"] * damped
            out[i : i + m] = x[i : i + m] + v["mix"] * delayed
            self._write = (self._write + m) % size
            i += m
        return out


class Reverb(PedalboardEffect):
    id = "reverb"
    label = "Reverb"
    tail_seconds = 3.0
    params = (
        Param("size", "Raumgröße", 0, 1, 0.5),
        Param("damping", "Dämpfung", 0, 1, 0.5),
        Param("mix", "Mix", 0, 1, 0.25),
    )

    def make_plugin(self):
        return pb.Reverb(width=1.0)

    def apply(self, plugin):
        v = self.values
        plugin.room_size = v["size"]
        plugin.damping = v["damping"]
        plugin.wet_level = v["mix"]
        plugin.dry_level = 1.0 - 0.6 * v["mix"]
