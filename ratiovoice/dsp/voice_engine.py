"""Stimm-Engine auf Basis des WORLD-Vocoders.

WORLD zerlegt Sprache in drei voneinander unabhängige Komponenten:

* ``f0``  – Grundfrequenz (Tonhöhe) pro 5-ms-Frame
* ``sp``  – spektrale Hüllkurve (Formanten / Klangfarbe)
* ``ap``  – Aperiodizität (Rausch- bzw. Hauchanteil)

Weil die Komponenten getrennt vorliegen, lassen sich Tonhöhe, Formanten,
Tempo, Sprachmelodie, Hauch und Rauheit unabhängig voneinander verändern –
anders als beim klassischen Resampling, das alles gemeinsam verschiebt.

Die (teure) Analyse läuft einmal pro Aufnahme, die Synthese ist rund 25-mal
schneller als Echtzeit und wird bei jeder Regleränderung neu ausgeführt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pyworld as pw
from scipy.signal import lfilter

from ..params import Param, defaults, sanitize

FRAME_MS = 5.0
F0_FLOOR = 60.0
F0_CEIL = 800.0
_CHUNK_FRAMES = 4000  # 20 s pro Syntheseblock begrenzt den Speicherbedarf
_OVERLAP_FRAMES = 8  # 40 ms Überblendung zwischen Blöcken

SCALES = {
    0: (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11),  # chromatisch
    1: (0, 2, 4, 5, 7, 9, 11),  # Dur
    2: (0, 2, 3, 5, 7, 8, 10),  # Moll
    3: (0, 2, 4, 7, 9),  # Pentatonik
}
NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "H")

VOICE_PARAMS: tuple[Param, ...] = (
    Param("pitch", "Tonhöhe", -24, 24, 0, "HT", 0.1),
    Param("formant", "Formant", -12, 12, 0, "HT", 0.1),
    Param("speed", "Tempo", 0.5, 2.0, 1.0, "×"),
    Param("intonation", "Sprachmelodie", 0.0, 2.0, 1.0, "×"),
    Param("breath", "Hauch / Flüstern", 0.0, 1.0, 0.0),
    Param("rough", "Rauheit", 0.0, 1.0, 0.0),
    Param("tremor", "Zittern", 0.0, 1.0, 0.0),
    Param("tremor_rate", "Zitter-Tempo", 0.5, 12.0, 5.5, "Hz", 0.1),
    Param("drift", "Schwanken", 0.0, 1.0, 0.0),
    Param("tune", "Pitch Correction", 0.0, 1.0, 0.0),
    Param("tune_speed", "Korrektur-Tempo", 0.0, 1.0, 0.85),
    Param("tune_scale", "Tonleiter", choices=("Chromatisch", "Dur", "Moll", "Pentatonik")),
    Param("tune_key", "Grundton", choices=NOTE_NAMES),
)

# Parameter, die nur die Autotune-Details steuern und ohne ``tune`` wirkungslos sind.
_PASSIVE_KEYS = {"tremor_rate", "tune_speed", "tune_scale", "tune_key"}


def default_voice() -> dict[str, float]:
    return defaults(VOICE_PARAMS)


def is_neutral(voice: dict) -> bool:
    """True, wenn die Stimm-Engine das Signal unverändert durchreichen kann."""
    base = default_voice()
    return all(
        abs(voice.get(key, value) - value) < 1e-6
        for key, value in base.items()
        if key not in _PASSIVE_KEYS
    )


@dataclass
class VoiceAnalysis:
    """Kompakt gespeichertes WORLD-Analyseergebnis einer Aufnahme."""

    f0: np.ndarray  # (frames,) Hz, 0 = stimmlos
    log_sp: np.ndarray  # (frames, bins) float16, natürlicher Logarithmus
    ap_coded: np.ndarray  # (frames, bänder) float32
    sample_rate: int
    n_samples: int
    source: np.ndarray  # Originalsignal für den neutralen Durchgang

    @property
    def n_frames(self) -> int:
        return len(self.f0)

    @property
    def fft_size(self) -> int:
        return (self.log_sp.shape[1] - 1) * 2


def analyze(
    audio: np.ndarray,
    sample_rate: int,
    progress: Callable[[float], None] | None = None,
) -> VoiceAnalysis:
    """Zerlegt ``audio`` (mono) in f0, Hüllkurve und Aperiodizität."""
    x = np.ascontiguousarray(audio, dtype=np.float64)
    if len(x) < sample_rate // 10:
        x = np.pad(x, (0, sample_rate // 10 - len(x)))

    f0, times = pw.harvest(x, sample_rate, f0_floor=F0_FLOOR, f0_ceil=F0_CEIL, frame_period=FRAME_MS)
    if progress:
        progress(0.4)

    hop = int(sample_rate * FRAME_MS / 1000)
    pad_frames = 20
    log_parts, ap_parts = [], []
    for start in range(0, len(f0), _CHUNK_FRAMES):
        stop = min(start + _CHUNK_FRAMES, len(f0))
        a = max(start - pad_frames, 0)
        b = min(stop + pad_frames, len(f0))
        segment = np.ascontiguousarray(x[a * hop : min(b * hop + hop, len(x))])
        seg_f0 = np.ascontiguousarray(f0[a:b])
        seg_t = np.ascontiguousarray(times[a:b] - times[a])
        sp = pw.cheaptrick(segment, seg_f0, seg_t, sample_rate)
        ap = pw.d4c(segment, seg_f0, seg_t, sample_rate)
        inner = slice(start - a, start - a + (stop - start))
        log_parts.append(np.log(np.maximum(sp[inner], 1e-16)).astype(np.float16))
        ap_parts.append(pw.code_aperiodicity(np.ascontiguousarray(ap[inner]), sample_rate).astype(np.float32))
        if progress:
            progress(0.4 + 0.6 * stop / len(f0))

    return VoiceAnalysis(
        f0=f0,
        log_sp=np.concatenate(log_parts),
        ap_coded=np.concatenate(ap_parts),
        sample_rate=sample_rate,
        n_samples=len(audio),
        source=np.asarray(audio, dtype=np.float32),
    )


def synthesize(
    analysis: VoiceAnalysis,
    voice: dict,
    progress: Callable[[float], None] | None = None,
) -> np.ndarray:
    """Erzeugt die veränderte Stimme aus Analyse und Reglerwerten (mono, float32)."""
    v = sanitize(VOICE_PARAMS, voice)
    if is_neutral(v):
        return analysis.source.copy()

    fs = analysis.sample_rate
    hop = int(fs * FRAME_MS / 1000)

    # Zeitachse: Für jedes Ausgabe-Frame die (gebrochene) Position im Original.
    n_out = max(int(round(analysis.n_frames / v["speed"])), 2)
    src_pos = np.linspace(0.0, analysis.n_frames - 1, n_out)
    f0 = _shape_f0(_stretch_f0(analysis.f0, src_pos), v)

    formant_ratio = 2.0 ** (v["formant"] / 12.0)
    n_bins = analysis.log_sp.shape[1]
    warp_lo, warp_hi, warp_w = _warp_indices(n_bins, formant_ratio)
    tilt = _whisper_tilt(n_bins, fs, v["breath"])
    rng = np.random.default_rng(7)
    shimmer = v["rough"] * 0.22 * rng.standard_normal(n_out)

    out = np.zeros(n_out * hop + hop, dtype=np.float64)
    fade = _OVERLAP_FRAMES * hop
    for start in range(0, n_out, _CHUNK_FRAMES):
        stop = min(start + _CHUNK_FRAMES + _OVERLAP_FRAMES, n_out)
        pos = src_pos[start:stop]
        lo = np.floor(pos).astype(np.int64)
        hi = np.minimum(lo + 1, analysis.n_frames - 1)
        w = (pos - lo)[:, None]

        log_sp = analysis.log_sp[lo].astype(np.float64) * (1 - w) + analysis.log_sp[hi].astype(np.float64) * w
        if formant_ratio != 1.0:
            log_sp = log_sp[:, warp_lo] * (1 - warp_w) + log_sp[:, warp_hi] * warp_w
        log_sp += tilt + shimmer[start:stop, None]
        sp = np.exp(log_sp)

        nearest = np.rint(pos).astype(np.int64)
        ap = pw.decode_aperiodicity(
            np.ascontiguousarray(analysis.ap_coded[nearest], dtype=np.float64), fs, analysis.fft_size
        )
        if formant_ratio != 1.0:
            ap = ap[:, warp_lo] * (1 - warp_w) + ap[:, warp_hi] * warp_w
        noise = max(v["breath"], 0.45 * v["rough"])
        if noise > 0:
            ap = ap + (1.0 - ap) * noise
        ap = np.clip(ap, 1e-3, 1.0)

        chunk = pw.synthesize(
            np.ascontiguousarray(f0[start:stop]),
            np.ascontiguousarray(sp),
            np.ascontiguousarray(ap),
            fs,
            FRAME_MS,
        )
        a = start * hop
        chunk = chunk[: len(out) - a]
        if start > 0:
            ramp = np.linspace(0.0, 1.0, min(fade, len(chunk)))
            chunk[: len(ramp)] *= ramp
            out[a : a + len(ramp)] *= 1.0 - ramp
        out[a : a + len(chunk)] += chunk
        if progress:
            progress(min(stop / n_out, 1.0))

    target_len = max(int(round(analysis.n_samples / v["speed"])), 1)
    out = out[:target_len]
    # Reines Flüstern ist deutlich leiser als stimmhafte Sprache – ausgleichen.
    out *= 1.0 + 1.6 * v["breath"]
    return out.astype(np.float32)


# --------------------------------------------------------------------------
# f0-Bearbeitung
# --------------------------------------------------------------------------


def _stretch_f0(f0: np.ndarray, src_pos: np.ndarray) -> np.ndarray:
    """Zeitdehnung der f0-Kurve, ohne über stimmlose Abschnitte zu interpolieren."""
    voiced = f0 > 0
    if not voiced.any():
        return np.zeros(len(src_pos))
    frames = np.arange(len(f0))
    filled = np.interp(frames, frames[voiced], f0[voiced])
    stretched = np.interp(src_pos, frames, filled)
    is_voiced = voiced[np.rint(src_pos).astype(np.int64)]
    return np.where(is_voiced, stretched, 0.0)


def _shape_f0(f0: np.ndarray, v: dict) -> np.ndarray:
    voiced = f0 > 0
    if not voiced.any():
        return f0
    if v["breath"] >= 0.995:
        return np.zeros_like(f0)  # vollständiges Flüstern: keine Stimmbandanregung

    n = len(f0)
    t = np.arange(n) * FRAME_MS / 1000.0
    rng = np.random.default_rng(11)
    semis = 12.0 * np.log2(np.where(voiced, f0, 1.0) / 440.0) + 69.0  # MIDI-Notenwerte
    median = np.median(semis[voiced])

    semis = median + (semis - median) * v["intonation"]
    semis += v["pitch"]

    if v["tune"] > 0:
        target = _nearest_scale_note(semis, int(v["tune_scale"]), int(v["tune_key"]))
        # Korrektur-Tempo: 1 = harte Stufen (T-Pain-Effekt), kleiner = weiches Gleiten.
        alpha = 0.02 + 0.98 * v["tune_speed"] ** 2
        idx = np.flatnonzero(voiced)
        smoothed, _ = lfilter([alpha], [1.0, alpha - 1.0], target[idx], zi=[target[idx[0]] * (1 - alpha)])
        semis[idx] += v["tune"] * (smoothed - semis[idx])

    if v["tremor"] > 0:
        semis += v["tremor"] * 1.2 * np.sin(2 * np.pi * v["tremor_rate"] * t)
    if v["drift"] > 0:
        semis += v["drift"] * 3.5 * _slow_noise(n, rng, cutoff_hz=0.8)
    if v["rough"] > 0:
        semis += v["rough"] * 0.9 * rng.standard_normal(n)
        # Knarrstimme: gelegentliche Oktavsprünge nach unten (Subharmonische).
        creak = _slow_noise(n, rng, cutoff_hz=3.0) > (2.4 - 1.6 * v["rough"])
        semis[creak] -= 12.0

    hz = 440.0 * 2.0 ** ((semis - 69.0) / 12.0)
    return np.where(voiced, np.clip(hz, 35.0, 1100.0), 0.0)


def _nearest_scale_note(semis: np.ndarray, scale: int, key: int) -> np.ndarray:
    notes = np.array(SCALES.get(scale, SCALES[0]), dtype=np.float64)
    rel = semis - key
    octave = np.floor(rel / 12.0)
    within = rel - octave * 12.0
    candidates = np.concatenate([notes, [notes[0] + 12.0]])
    nearest = candidates[np.argmin(np.abs(within[:, None] - candidates[None, :]), axis=1)]
    return octave * 12.0 + nearest + key


def _slow_noise(n: int, rng: np.random.Generator, cutoff_hz: float) -> np.ndarray:
    """Tiefpassgefiltertes Rauschen mit Standardabweichung ~1."""
    alpha = 1.0 - np.exp(-2 * np.pi * cutoff_hz * FRAME_MS / 1000.0)
    noise = rng.standard_normal(n + 400)
    for _ in range(2):
        noise = lfilter([alpha], [1.0, alpha - 1.0], noise)
    noise = noise[400:]
    return noise / (np.std(noise) + 1e-9)


# --------------------------------------------------------------------------
# Hüllkurven-Bearbeitung
# --------------------------------------------------------------------------


def _warp_indices(n_bins: int, ratio: float):
    """Indizes/Gewichte, um die Hüllkurve um ``ratio`` entlang der Frequenz zu strecken."""
    src = np.arange(n_bins) / ratio
    src = np.minimum(src, n_bins - 1.0)
    lo = np.floor(src).astype(np.int64)
    hi = np.minimum(lo + 1, n_bins - 1)
    return lo, hi, src - lo


def _whisper_tilt(n_bins: int, fs: int, breath: float) -> np.ndarray:
    """Beim Flüstern fehlt die Energie der Stimmbänder im Bassbereich."""
    if breath <= 0:
        return np.zeros(n_bins)
    freqs = np.linspace(0.0, fs / 2.0, n_bins)
    attenuation_db = -18.0 * breath / (1.0 + (freqs / 450.0) ** 2)
    return attenuation_db * np.log(10.0) / 10.0  # dB (Leistung) -> ln
