"""Modulationseffekte: Chorus, Flanger, Phaser."""

from __future__ import annotations

import pedalboard as pb

from ...params import Param
from .base import PedalboardEffect


class Chorus(PedalboardEffect):
    id = "chorus"
    label = "Chorus"
    params = (
        Param("rate", "Tempo", 0.05, 8, 1.0, "Hz", 0.05),
        Param("depth", "Tiefe", 0, 1, 0.3),
        Param("delay", "Verzögerung", 5, 40, 12, "ms", 0.5),
        Param("mix", "Mix", 0, 1, 0.5),
    )

    def make_plugin(self):
        return pb.Chorus(feedback=0.0)

    def apply(self, plugin):
        v = self.values
        plugin.rate_hz = v["rate"]
        plugin.depth = v["depth"]
        plugin.centre_delay_ms = v["delay"]
        plugin.mix = v["mix"]


class Flanger(PedalboardEffect):
    """Kurzes, moduliertes Delay mit Rückkopplung (Kammfilter-Sweep)."""

    id = "flanger"
    label = "Flanger"
    params = (
        Param("rate", "Tempo", 0.05, 6, 0.4, "Hz", 0.05),
        Param("depth", "Tiefe", 0, 1, 0.6),
        Param("feedback", "Feedback", 0, 0.92, 0.6),
        Param("mix", "Mix", 0, 1, 0.5),
    )

    def make_plugin(self):
        return pb.Chorus(centre_delay_ms=2.5)

    def apply(self, plugin):
        v = self.values
        plugin.rate_hz = v["rate"]
        plugin.depth = v["depth"]
        plugin.feedback = v["feedback"]
        plugin.mix = v["mix"]


class Phaser(PedalboardEffect):
    id = "phaser"
    label = "Phaser"
    params = (
        Param("rate", "Tempo", 0.05, 8, 0.6, "Hz", 0.05),
        Param("depth", "Tiefe", 0, 1, 0.6),
        Param("freq", "Mittenfrequenz", 200, 5000, 1200, "Hz", 1, log=True),
        Param("feedback", "Feedback", 0, 0.92, 0.4),
        Param("mix", "Mix", 0, 1, 0.5),
    )

    def make_plugin(self):
        return pb.Phaser()

    def apply(self, plugin):
        v = self.values
        plugin.rate_hz = v["rate"]
        plugin.depth = v["depth"]
        plugin.centre_frequency_hz = v["freq"]
        plugin.feedback = v["feedback"]
        plugin.mix = v["mix"]
