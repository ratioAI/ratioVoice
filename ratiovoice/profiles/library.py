"""Die mitgelieferte Stimmenbibliothek.

Jedes Profil kombiniert Einstellungen der Stimm-Engine (``voice``) mit einer
Effektkette (``chain``). Die Werte gehen von einer durchschnittlichen
Männerstimme als Ausgangsmaterial aus; über die Regler lässt sich jedes
Profil an die eigene Stimme anpassen.
"""

from __future__ import annotations

from ..settings import normalize

HUMAN = "Menschliche Stimmen"
CREATIVE = "Kreativ & lustig"
TECH = "Technisch & elektronisch"
CATEGORIES = (HUMAN, CREATIVE, TECH)


# Pegelausgleich in dB, damit alle Profile etwa gleich laut klingen (an Sprache eingemessen).
_LEVEL_DB = {
    "Sehr tiefe, dominante Männerstimme": -3.5,
    "Hohe Männerstimme": 1.5,
    "Roboterartige menschliche Stimme": 5.5,
    "Flüsternde Stimme": 8.0,
    "Radio-Moderator": -8.0,
    "Telefonstimme": -1.5,
    "Cartoon-Stimme": 3.5,
    "Dämonische Stimme": -3.0,
    "Alien-Stimme": 9.0,
    "Riesen-Stimme": -4.0,
    "Zwergen-Stimme": -8.5,
    "Besoffene Stimme": 4.5,
    "Verzerrte Horror-Stimme": -3.0,
    "KI-Stimme": 6.0,
    "Vocoder": -1.5,
    "Telefon / Funkgerät": 4.0,
    "Walkie-Talkie": 1.5,
    "Glitch-Stimme": 2.0,
    "8-Bit-Stimme": 3.0,
    "Synthetische Stimme": 6.0,
}


def fx(effect_id: str, **params) -> dict:
    return {"id": effect_id, "on": True, "params": params}


def _profile(category: str, name: str, voice: dict | None = None, chain: list | None = None) -> dict:
    chain = list(chain or [])
    if name in _LEVEL_DB:
        chain.append(fx("output", gain=_LEVEL_DB[name]))
    settings = normalize({"profile": name, "voice": voice or {}, "chain": chain})
    return {"category": category, "name": name, "settings": settings}


PROFILES: tuple[dict, ...] = (
    # ---------------------------------------------------------------- Menschlich
    _profile(HUMAN, "Tiefe Männerstimme",
             dict(pitch=-4, formant=-2.2),
             [fx("eq", low=2.5, lowcut=50)]),
    _profile(HUMAN, "Sehr tiefe, dominante Männerstimme",
             dict(pitch=-8, formant=-4.5, intonation=0.8, speed=0.96),
             [fx("eq", low=6, mid=-2, mid_freq=500, high=1.5),
              fx("compressor", threshold=-26, ratio=5, makeup=5),
              fx("saturation", drive=0.25, warmth=0.7)]),
    _profile(HUMAN, "Hohe Männerstimme",
             dict(pitch=4, formant=1.2, intonation=1.1),
             [fx("eq", lowcut=110, high=1.5)]),
    _profile(HUMAN, "Weibliche Stimme",
             dict(pitch=9, formant=3.2, intonation=1.25, breath=0.1),
             [fx("eq", lowcut=140, low=-2, high=2)]),
    _profile(HUMAN, "Sehr hohe, kindliche Stimme",
             dict(pitch=13, formant=5.8, intonation=1.35, speed=1.06),
             [fx("eq", lowcut=220, high=2.5)]),
    _profile(HUMAN, "Alte, raue Stimme",
             dict(pitch=-1.5, formant=-0.6, rough=0.75, tremor=0.5, tremor_rate=6.2, breath=0.28, speed=0.88),
             [fx("eq", lowcut=120, mid=3, mid_freq=2200, high=-5, highcut=7500)]),
    _profile(HUMAN, "Roboterartige menschliche Stimme",
             dict(intonation=0.08, tune=1.0, tune_speed=1.0, formant=-0.5),
             [fx("ringmod", freq=55, mix=0.3),
              fx("flanger", rate=0.15, depth=0.35, feedback=0.55, mix=0.35),
              fx("eq", highcut=9000)]),
    _profile(HUMAN, "Flüsternde Stimme",
             dict(breath=1.0),
             [fx("eq", lowcut=260, high=3),
              fx("compressor", threshold=-30, ratio=3, makeup=6)]),
    _profile(HUMAN, "Radio-Moderator",
             dict(pitch=-2, formant=-1.2, intonation=1.1),
             [fx("eq", lowcut=70, low=5, mid=-3, mid_freq=450, high=4.5),
              fx("compressor", threshold=-28, ratio=6, attack=3, makeup=7),
              fx("saturation", drive=0.2, warmth=0.6),
              fx("reverb", size=0.15, damping=0.7, mix=0.06)]),
    _profile(HUMAN, "Telefonstimme",
             None,
             [fx("compressor", threshold=-24, ratio=4, makeup=5),
              fx("saturation", drive=0.3, warmth=0.2),
              fx("eq", lowcut=320, mid=5, mid_freq=1800, highcut=3400)]),

    # ------------------------------------------------------------------ Kreativ
    _profile(CREATIVE, "Cartoon-Stimme",
             dict(pitch=6, formant=4.2, intonation=1.85, speed=1.14),
             [fx("eq", lowcut=160, mid=3, mid_freq=2600),
              fx("compressor", threshold=-22, ratio=4, makeup=4)]),
    _profile(CREATIVE, "Chipmunk / Mäusestimme",
             dict(pitch=12, formant=9.5, speed=1.3, intonation=1.2),
             [fx("eq", lowcut=300, high=2)]),
    _profile(CREATIVE, "Dämonische Stimme",
             dict(pitch=-10, formant=-5, rough=0.4, intonation=0.75, speed=0.94),
             [fx("ringmod", freq=38, mix=0.35),
              fx("chorus", rate=0.35, depth=0.6, delay=22, mix=0.5),
              fx("distortion", drive=14, mode=0, tone=3800, mix=0.55),
              fx("eq", low=6, high=-3),
              fx("reverb", size=0.85, damping=0.75, mix=0.32)]),
    _profile(CREATIVE, "Alien-Stimme",
             dict(pitch=3, formant=6, intonation=1.5),
             [fx("ringmod", freq=210, mix=0.55),
              fx("phaser", rate=3.2, depth=0.8, freq=1500, feedback=0.7, mix=0.6),
              fx("flanger", rate=0.9, depth=0.7, feedback=0.75, mix=0.5),
              fx("delay", time=65, feedback=0.35, mix=0.3)]),
    _profile(CREATIVE, "Monster-Stimme",
             dict(pitch=-13, formant=-7.5, rough=0.85, speed=0.9, intonation=0.9),
             [fx("distortion", drive=20, mode=2, tone=2600, mix=0.6),
              fx("eq", low=7, mid=3, mid_freq=700, highcut=6000),
              fx("compressor", threshold=-24, ratio=6, makeup=4),
              fx("reverb", size=0.55, damping=0.6, mix=0.18)]),
    _profile(CREATIVE, "Riesen-Stimme",
             dict(pitch=-7, formant=-9, speed=0.8, intonation=0.9),
             [fx("eq", low=7, highcut=7000),
              fx("echo", time=240, feedback=0.25, damping=0.7, mix=0.18),
              fx("reverb", size=0.95, damping=0.45, mix=0.38)]),
    _profile(CREATIVE, "Zwergen-Stimme",
             dict(pitch=5, formant=8.5, speed=1.1, rough=0.2, intonation=1.15),
             [fx("eq", lowcut=240, mid=4, mid_freq=1500, high=-2),
              fx("saturation", drive=0.35, warmth=0.4)]),
    _profile(CREATIVE, "Besoffene Stimme",
             dict(speed=0.78, drift=0.8, intonation=1.4, pitch=-1.5, formant=-1, tremor=0.12, tremor_rate=2.2),
             [fx("chorus", rate=0.25, depth=0.55, delay=18, mix=0.35),
              fx("eq", high=-4, highcut=9000)]),
    _profile(CREATIVE, "Verzerrte Horror-Stimme",
             dict(pitch=-5, formant=-2, breath=0.4, rough=0.55, intonation=0.6),
             [fx("distortion", drive=30, mode=1, tone=4200, mix=0.75),
              fx("bitcrusher", bits=7, rate=9000, mix=0.45),
              fx("glitch", amount=0.22, slice=70),
              fx("flanger", rate=0.2, depth=0.8, feedback=0.8, mix=0.45),
              fx("tremolo", rate=9, depth=0.35),
              fx("reverb", size=0.8, damping=0.8, mix=0.3)]),
    _profile(CREATIVE, "Geisterstimme",
             dict(breath=0.78, pitch=2, intonation=0.55, tremor=0.3, tremor_rate=3.0, speed=0.92),
             [fx("eq", lowcut=320, high=3),
              fx("chorus", rate=0.5, depth=0.7, delay=25, mix=0.5),
              fx("tremolo", rate=3.5, depth=0.45),
              fx("echo", time=520, feedback=0.55, damping=0.5, mix=0.4),
              fx("reverb", size=1.0, damping=0.3, mix=0.6)]),

    # ---------------------------------------------------------------- Technisch
    _profile(TECH, "Roboter",
             dict(intonation=0.0),
             [fx("robot", pitch=105, mix=1.0),
              fx("bitcrusher", bits=10, rate=16000, mix=0.5),
              fx("eq", lowcut=120, mid=3, mid_freq=1400, highcut=7500)]),
    _profile(TECH, "KI-Stimme",
             dict(tune=0.55, tune_speed=0.4, intonation=0.65, formant=0.8, breath=0.08),
             [fx("compressor", threshold=-30, ratio=8, attack=2, makeup=8),
              fx("eq", lowcut=110, mid=-2, mid_freq=350, high=4),
              fx("delay", time=14, feedback=0.0, mix=0.22),
              fx("reverb", size=0.25, damping=0.4, mix=0.08)]),
    _profile(TECH, "Autotune",
             dict(tune=1.0, tune_speed=1.0, tune_scale=1, tune_key=0, intonation=1.3),
             [fx("compressor", threshold=-24, ratio=4, makeup=4),
              fx("reverb", size=0.4, damping=0.5, mix=0.14)]),
    _profile(TECH, "Vocoder",
             None,
             [fx("vocoder", carrier=3, pitch=98, bands=22, mix=1.0),
              fx("chorus", rate=0.6, depth=0.4, delay=14, mix=0.4),
              fx("reverb", size=0.45, damping=0.5, mix=0.16)]),
    _profile(TECH, "Telefon / Funkgerät",
             None,
             [fx("compressor", threshold=-30, ratio=8, makeup=8),
              fx("distortion", drive=16, mode=0, tone=3500, mix=0.8),
              fx("noise", level=-36, kind=0),
              fx("eq", lowcut=420, mid=6, mid_freq=1400, highcut=2700)]),
    _profile(TECH, "Walkie-Talkie",
             None,
             [fx("gate", threshold=-38),
              fx("compressor", threshold=-32, ratio=12, makeup=10),
              fx("distortion", drive=30, mode=1, tone=2800, mix=1.0),
              fx("bitcrusher", bits=8, rate=7000, mix=0.8),
              fx("noise", level=-27, kind=1),
              fx("eq", lowcut=650, mid=8, mid_freq=1900, highcut=2300)]),
    _profile(TECH, "Glitch-Stimme",
             dict(tune=0.6, tune_speed=1.0),
             [fx("glitch", amount=0.6, slice=85),
              fx("bitcrusher", bits=9, rate=14000, mix=0.5),
              fx("delay", time=45, feedback=0.3, mix=0.2)]),
    _profile(TECH, "8-Bit-Stimme",
             dict(tune=1.0, tune_speed=1.0, intonation=0.6),
             [fx("vocoder", carrier=1, pitch=220, bands=8, mix=0.7),
              fx("bitcrusher", bits=4, rate=5500, mix=1.0),
              fx("eq", lowcut=150, highcut=5200)]),
    _profile(TECH, "Synthetische Stimme",
             dict(intonation=0.5),
             [fx("vocoder", carrier=0, pitch=147, bands=30, mix=0.88),
              fx("phaser", rate=0.25, depth=0.5, freq=900, feedback=0.3, mix=0.35),
              fx("eq", high=3),
              fx("delay", time=120, feedback=0.25, mix=0.15)]),
)


def by_category(category: str) -> list[dict]:
    return [p for p in PROFILES if p["category"] == category]
