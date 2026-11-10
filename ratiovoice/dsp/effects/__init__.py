"""Effekt-Registry.

Neue Effekte: Klasse von ``Effect`` ableiten, ``id``/``label``/``params``
setzen und hier in ``_EFFECT_CLASSES`` eintragen – die Oberfläche übernimmt
den Effekt automatisch.
"""

from __future__ import annotations

from .base import Effect
from .color import Bitcrusher, Distortion, Noise, RingModulator, Saturation, Tremolo
from .modulation import Chorus, Flanger, Phaser
from .space import Delay, Echo, Reverb
from .spectral import Glitch, Robot, Vocoder
from .tone import Compressor, Equalizer, Gate, Output

_EFFECT_CLASSES: tuple[type[Effect], ...] = (
    Equalizer,
    Compressor,
    Gate,
    Saturation,
    Distortion,
    Bitcrusher,
    RingModulator,
    Robot,
    Vocoder,
    Glitch,
    Chorus,
    Flanger,
    Phaser,
    Tremolo,
    Delay,
    Echo,
    Reverb,
    Noise,
    Output,
)

EFFECTS: dict[str, type[Effect]] = {cls.id: cls for cls in _EFFECT_CLASSES}


def create(effect_id: str, sample_rate: int) -> Effect:
    return EFFECTS[effect_id](sample_rate)
