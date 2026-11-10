"""Echtzeit-Pitch- und Formant-Shifter für den Live-Mikrofonbetrieb.

Der WORLD-Vocoder liefert die beste Qualität, braucht aber die ganze
Aufnahme. Für das Live-Mikrofon arbeitet deshalb ein Phase-Vocoder mit
cepstraler Hüllkurvenschätzung: Die spektrale Hüllkurve (Formanten) wird vom
Anregungssignal getrennt, beide werden unabhängig verschoben und wieder
zusammengesetzt. Latenz: eine Fensterlänge (ca. 43 ms bei 2048 Samples).
"""

from __future__ import annotations

import numpy as np

from .effects.base import StreamingOLA


class LiveShifter:
    def __init__(self, sample_rate: int, n_fft: int = 2048):
        self.sr = sample_rate
        self.n_fft = n_fft
        self.hop = n_fft // 4
        self._ola = StreamingOLA(n_fft)
        self._bins = np.arange(n_fft // 2 + 1)
        self._expected = 2 * np.pi * self.hop * self._bins / n_fft
        self._last_phase = np.zeros(len(self._bins))
        self._sum_phase = np.zeros(len(self._bins))
        self._rng = np.random.default_rng(1)
        # Lifter-Grenze: Hüllkurve = Quefrenzen unterhalb der kürzesten Stimmperiode.
        self._lifter = int(sample_rate / 700.0)
        self.pitch_ratio = 1.0
        self.formant_ratio = 1.0
        self.whisper = 0.0

    def set_voice(self, voice: dict) -> None:
        self.pitch_ratio = 2.0 ** (voice.get("pitch", 0.0) / 12.0)
        self.formant_ratio = 2.0 ** (voice.get("formant", 0.0) / 12.0)
        self.whisper = float(voice.get("breath", 0.0))

    @property
    def active(self) -> bool:
        return self.pitch_ratio != 1.0 or self.formant_ratio != 1.0 or self.whisper > 0.0

    def process(self, x: np.ndarray) -> np.ndarray:
        if not self.active:
            return x
        # Beim Umskalieren der Anregung ändert sich die Energie mit der Tonhöhe – ausgleichen.
        scale = self.hop / (0.375 * self.n_fft) * 1.25 / np.sqrt(self.pitch_ratio)
        return self._ola.process(x, self.hop, self._frame) * scale

    def _envelope(self, log_mag: np.ndarray) -> np.ndarray:
        cepstrum = np.fft.irfft(log_mag)
        cepstrum[self._lifter : -self._lifter] = 0.0
        return np.exp(np.fft.rfft(cepstrum).real)

    def _frame(self, frame: np.ndarray) -> np.ndarray:
        spectrum = np.fft.rfft(frame)
        mag = np.abs(spectrum)
        phase = np.angle(spectrum)
        n_bins = len(mag)

        # Analyse: tatsächliche Frequenz jedes Bins aus dem Phasenfortschritt.
        delta = phase - self._last_phase - self._expected
        self._last_phase = phase
        delta -= 2 * np.pi * np.round(delta / (2 * np.pi))
        true_bin = self._bins + delta * self.n_fft / (2 * np.pi * self.hop)

        envelope = self._envelope(np.log(mag + 1e-9))
        excitation = mag / envelope

        # Tonhöhe: Anregung entlang der Frequenzachse umskalieren.
        src = self._bins / self.pitch_ratio
        valid = src <= n_bins - 1
        lo = np.minimum(src.astype(np.int64), n_bins - 2)
        w = np.clip(src - lo, 0.0, 1.0)
        shifted = np.where(valid, excitation[lo] * (1 - w) + excitation[lo + 1] * w, 0.0)
        nearest = np.minimum(np.rint(src).astype(np.int64), n_bins - 1)
        shifted_bin = true_bin[nearest] * self.pitch_ratio

        # Formanten: Hüllkurve unabhängig davon strecken oder stauchen.
        env_src = np.minimum(self._bins / self.formant_ratio, n_bins - 1.0)
        env_lo = np.minimum(env_src.astype(np.int64), n_bins - 2)
        env_w = env_src - env_lo
        out_env = envelope[env_lo] * (1 - env_w) + envelope[env_lo + 1] * env_w

        self._sum_phase += 2 * np.pi * self.hop * shifted_bin / self.n_fft
        self._sum_phase %= 2 * np.pi
        out_phase = self._sum_phase
        if self.whisper > 0:
            # Flüstern: Anregung einebnen und Phasen verwürfeln -> geformtes Rauschen.
            flat = np.mean(shifted) * 1.5
            shifted = shifted * (1 - self.whisper) + flat * self.whisper
            out_phase = out_phase + self.whisper * self._rng.uniform(-np.pi, np.pi, n_bins)

        out = np.fft.irfft(shifted * out_env * np.exp(1j * out_phase))
        return out * self._ola.window
