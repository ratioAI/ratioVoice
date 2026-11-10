"""Prüft die Stimm-Engine und die Profile an echten Sprachaufnahmen.

Aufruf:  python -m pytest tests            (automatische Prüfung)
         python tests/test_engine.py out   (zusätzlich alle Profile als WAV nach ./out rendern)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pyworld as pw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ratiovoice import audio_io  # noqa: E402
from ratiovoice.config import SAMPLE_RATE  # noqa: E402
from ratiovoice.dsp import voice_engine as ve  # noqa: E402
from ratiovoice.dsp.chain import render  # noqa: E402
from ratiovoice.dsp.live_shifter import LiveShifter  # noqa: E402
from ratiovoice.profiles.library import PROFILES  # noqa: E402

DATA = Path(__file__).parent / "data"
_cache: dict = {}


def speech() -> np.ndarray:
    if "x" not in _cache:
        parts = [audio_io.load(DATA / "sprache_1.wav"), audio_io.load(DATA / "sprache_2.flac")]
        x = np.concatenate(parts)
        _cache["x"] = x / np.abs(x).max() * 0.7
    return _cache["x"]


def analysis() -> ve.VoiceAnalysis:
    if "a" not in _cache:
        _cache["a"] = ve.analyze(speech(), SAMPLE_RATE)
    return _cache["a"]


def measure(audio: np.ndarray) -> dict:
    """Median-Tonhöhe, Dauer und mittlere spektrale Hüllkurve der stimmhaften Frames."""
    x = audio.astype(np.float64)
    f0, t = pw.harvest(x, SAMPLE_RATE, f0_floor=35, f0_ceil=1100)
    voiced = f0 > 0
    sp = pw.cheaptrick(x, f0, t, SAMPLE_RATE)
    return {
        "f0": float(np.median(f0[voiced])),
        "envelope": np.log(sp[voiced]).mean(axis=0),
        "seconds": len(audio) / SAMPLE_RATE,
    }


def semitones(a: float, b: float) -> float:
    return float(12 * np.log2(a / b))


def formant_shift(reference: dict, other: dict) -> float:
    """Verschiebung der Hüllkurve in Halbtönen (Korrelation auf logarithmischer Frequenzachse)."""
    freqs = np.linspace(0, SAMPLE_RATE / 2, len(reference["envelope"]))
    grid = np.geomspace(250, 6000, 600)
    ref = np.interp(grid, freqs, reference["envelope"])
    oth = np.interp(grid, freqs, other["envelope"])
    step = 12 * np.log2(grid[1] / grid[0])
    best = (-2.0, 0.0)
    for lag in range(-150, 151):
        a, b = (ref[: 600 - lag], oth[lag:]) if lag >= 0 else (ref[-lag:], oth[: 600 + lag])
        best = max(best, (np.corrcoef(a, b)[0, 1], lag * step))
    return best[1]


def render_profile(profile: dict) -> np.ndarray:
    settings = profile["settings"]
    return render(ve.synthesize(analysis(), settings["voice"]), settings["chain"], SAMPLE_RATE)


def features(audio: np.ndarray) -> np.ndarray:
    """Tempo-unabhängiger Klang-Fingerabdruck: Spektrum, Dynamik, Tonhöhe, Rauschanteil."""
    n_fft, hop = 2048, 512
    frames = np.lib.stride_tricks.sliding_window_view(audio, n_fft)[::hop] * np.hanning(n_fft)
    mag = np.abs(np.fft.rfft(frames, axis=1))
    edges = np.geomspace(80, 16000, 33) / (SAMPLE_RATE / 2) * (n_fft // 2)
    bands = np.stack([mag[:, int(a) : max(int(b), int(a) + 1)].mean(axis=1) for a, b in zip(edges, edges[1:])], axis=1)
    level = 20 * np.log10(bands + 1e-6)
    active = level.max(axis=1) > level.max() - 40
    level = level[active] - level[active].mean()
    flatness = np.exp(np.log(mag[active] + 1e-9).mean(axis=1)) / (mag[active].mean(axis=1) + 1e-9)
    m = measure(audio)
    return np.concatenate([
        level.mean(axis=0) / 6.0,
        level.std(axis=0) / 6.0,
        [12 * np.log2(m["f0"] / 100.0) / 3.0, flatness.mean() * 20, np.log2(m["seconds"]) * 6],
    ])


def test_pitch_and_formant_are_independent():
    base = measure(speech())
    voice = ve.default_voice()

    low = measure(ve.synthesize(analysis(), {**voice, "pitch": -8}))
    assert abs(semitones(low["f0"], base["f0"]) + 8) < 0.5, "Tonhöhe muss um 8 HT sinken"
    assert abs(formant_shift(base, low)) < 0.6, "Formanten müssen bleiben"
    assert abs(low["seconds"] - base["seconds"]) < 0.01, "Dauer muss gleich bleiben"

    dark = measure(ve.synthesize(analysis(), {**voice, "formant": -5}))
    assert abs(semitones(dark["f0"], base["f0"])) < 0.5, "Tonhöhe muss bleiben"
    assert abs(formant_shift(base, dark) + 5) < 0.6, "Formanten müssen um 5 HT sinken"

    slow = measure(ve.synthesize(analysis(), {**voice, "speed": 0.75}))
    assert abs(slow["seconds"] / base["seconds"] - 1 / 0.75) < 0.01
    assert abs(semitones(slow["f0"], base["f0"])) < 0.5, "Time-Stretching darf die Tonhöhe nicht ändern"


def test_neutral_settings_are_bit_exact():
    assert np.array_equal(ve.synthesize(analysis(), ve.default_voice()), speech())


def _semitone_error(audio: np.ndarray) -> float:
    f0, _ = pw.harvest(audio.astype(np.float64), SAMPLE_RATE)
    midi = 69 + 12 * np.log2(f0[f0 > 0] / 440.0)
    return float(np.median(np.abs(midi - np.round(midi))))


def test_autotune_hits_scale_notes():
    tuned = {**ve.default_voice(), "tune": 1.0, "tune_speed": 1.0}
    # Die erzeugte Tonhöhenkurve liegt exakt auf Halbtönen ...
    curve = ve._shape_f0(analysis().f0.copy(), tuned)
    midi = 69 + 12 * np.log2(curve[curve > 0] / 440.0)
    assert np.abs(midi - np.round(midi)).max() < 1e-6
    # ... und auch im Audiosignal ist die Sprache messbar näher an den Tonstufen
    # (die Messung selbst glättet die Sprünge, daher kein exakter Vergleich).
    assert _semitone_error(ve.synthesize(analysis(), tuned)) < 0.75 * _semitone_error(speech())


def test_live_shifter_shifts_pitch():
    shifter = LiveShifter(SAMPLE_RATE)
    shifter.set_voice({"pitch": 5, "formant": 0})
    x = speech().astype(np.float64)
    out = np.concatenate([shifter.process(x[i : i + 512]) for i in range(0, len(x), 512)])
    assert len(out) == len(x)
    shift = semitones(measure(out)["f0"], measure(speech())["f0"])
    assert abs(shift - 5) < 1.0, f"Live-Shifter liefert {shift:.2f} statt 5 HT"


def test_all_profiles_sound_different():
    rendered = {p["name"]: render_profile(p) for p in PROFILES}
    for name, audio in rendered.items():
        assert np.isfinite(audio).all(), name
        rms = np.sqrt(np.mean(audio**2))
        assert 0.02 < rms < 0.5, f"{name}: Lautstärke außerhalb des sinnvollen Bereichs ({rms:.3f})"
        assert np.abs(audio).max() <= 1.0, name
    names = ["Original"] + list(rendered)
    feats = np.stack([features(speech())] + [features(a) for a in rendered.values()])
    dist = np.linalg.norm(feats[:, None] - feats[None], axis=2)
    np.fill_diagonal(dist, np.inf)
    _cache["report"] = (names, dist, rendered)
    closest = np.unravel_index(np.argmin(dist), dist.shape)
    assert dist.min() > 1.0, f"Zu ähnlich: {names[closest[0]]} / {names[closest[1]]} ({dist.min():.2f})"


if __name__ == "__main__":
    test_neutral_settings_are_bit_exact()
    test_pitch_and_formant_are_independent()
    test_autotune_hits_scale_notes()
    test_live_shifter_shifts_pitch()
    try:
        test_all_profiles_sound_different()
    finally:
        names, dist, rendered = _cache["report"]
        print(f"{'Profil':38s} {'RMS':>6s} {'Peak':>5s} {'Abstand':>8s}  ähnlichstes Profil")
        for i, name in enumerate(names[1:], start=1):
            audio = rendered[name]
            j = int(np.argmin(dist[i]))
            print(f"{name:38s} {np.sqrt(np.mean(audio**2)):6.3f} {np.abs(audio).max():5.2f} {dist[i, j]:8.2f}  {names[j]}")
        if len(sys.argv) > 1:
            out = Path(sys.argv[1])
            out.mkdir(parents=True, exist_ok=True)
            for i, name in enumerate(names[1:], start=1):
                audio_io.save(out / f"{i:02d}_{name.replace('/', '-').replace(' ', '_')}.wav", rendered[name])
    print("Alle Prüfungen bestanden.")
