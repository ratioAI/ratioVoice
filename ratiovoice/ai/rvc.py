"""KI-Voice-Conversion mit RVC-Modellen über ONNX Runtime.

RVC (Retrieval-based Voice Conversion) ersetzt die Klangfarbe einer Stimme
durch die eines trainierten Zielsprechers und liefert damit deutlich
überzeugendere "andere Menschen" als reine Signalverarbeitung.

Benötigte Dateien im Modellordner (siehe ``config.models_dir()``):

* ``vec-768-layer-12.onnx`` – ContentVec-Encoder (einmalig, für alle Stimmen)
* ``<Stimme>.onnx``        – beliebig viele RVC-v2-Stimmmodelle (ONNX-Export)

Die Verarbeitung läuft vollständig lokal; mit NVIDIA-Grafikkarte über CUDA.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import numpy as np
import pyworld as pw

from ..audio_io import resample
from ..config import SAMPLE_RATE, models_dir

ENCODER_NAMES = ("vec-768-layer-12.onnx", "contentvec_768l12.onnx")
_ENCODER_RATE = 16_000
_CHUNK_SECONDS = 15.0
_OVERLAP_SECONDS = 0.5
_F0_MIN, _F0_MAX = 50.0, 1100.0


class AiUnavailable(RuntimeError):
    """Die KI-Umwandlung kann nicht ausgeführt werden (Meldung ist für Nutzer formuliert)."""


def encoder_path() -> Path | None:
    for name in ENCODER_NAMES:
        path = models_dir() / name
        if path.exists():
            return path
    return None


def list_models() -> list[str]:
    """Namen aller Stimmmodelle im Modellordner (ohne den Encoder)."""
    return sorted(p.stem for p in models_dir().glob("*.onnx") if p.name not in ENCODER_NAMES)


def _session(path: Path):
    try:
        import onnxruntime as ort
    except ImportError as exc:
        raise AiUnavailable(
            "Für KI-Stimmen fehlt das Paket onnxruntime.\nInstallation: pip install onnxruntime-gpu"
        ) from exc
    preferred = ("CUDAExecutionProvider", "DmlExecutionProvider", "CPUExecutionProvider")
    providers = [p for p in preferred if p in ort.get_available_providers()]
    return ort.InferenceSession(str(path), providers=providers)


class RvcConverter:
    def __init__(self, model_name: str):
        encoder = encoder_path()
        if encoder is None:
            raise AiUnavailable(f"Der ContentVec-Encoder ({ENCODER_NAMES[0]}) fehlt im Ordner\n{models_dir()}")
        model = models_dir() / f"{model_name}.onnx"
        if not model.exists():
            raise AiUnavailable(f"Stimmmodell nicht gefunden: {model}")
        self._encoder = _session(encoder)
        self._model = _session(model)
        self._inputs = [i.name for i in self._model.get_inputs()]
        if len(self._inputs) not in (4, 6):
            raise AiUnavailable("Dieses ONNX-Modell ist kein RVC-Stimmmodell (unerwartete Eingänge).")
        feature_dim = self._model.get_inputs()[0].shape[-1]
        if isinstance(feature_dim, int) and feature_dim != 768:
            raise AiUnavailable("Es werden nur RVC-v2-Modelle (768 Merkmale) unterstützt.")
        self.uses_pitch = len(self._inputs) == 6

    def convert(
        self,
        audio: np.ndarray,
        transpose: int = 0,
        progress: Callable[[float], None] | None = None,
    ) -> np.ndarray:
        """Wandelt ``audio`` (Projekt-Abtastrate) in die Zielstimme um."""
        chunk = int(_CHUNK_SECONDS * SAMPLE_RATE)
        overlap = int(_OVERLAP_SECONDS * SAMPLE_RATE)
        out = np.zeros(len(audio), dtype=np.float32)
        starts = list(range(0, max(len(audio) - overlap, 1), chunk))
        for index, start in enumerate(starts):
            piece = audio[start : start + chunk + overlap]
            converted = self._convert_chunk(piece, transpose)[: len(piece)]
            converted = np.pad(converted, (0, len(piece) - len(converted)))
            if start > 0:
                ramp = np.linspace(0.0, 1.0, min(overlap, len(converted)), dtype=np.float32)
                converted[: len(ramp)] *= ramp
                out[start : start + len(ramp)] *= 1.0 - ramp
            out[start : start + len(piece)] += converted
            if progress:
                progress((index + 1) / len(starts))
        return out

    def _convert_chunk(self, audio: np.ndarray, transpose: int) -> np.ndarray:
        wav16 = resample(audio, SAMPLE_RATE, _ENCODER_RATE).astype(np.float32)
        features = self._encode(wav16)  # (1, frames, 768), 10 ms pro Frame
        n_frames = features.shape[1]
        feed = {
            self._inputs[0]: features,
            self._inputs[1]: np.array([n_frames], dtype=np.int64),
        }
        if self.uses_pitch:
            f0 = self._pitch(wav16, n_frames) * 2.0 ** (transpose / 12.0)
            feed[self._inputs[2]] = self._coarse_pitch(f0)[None]
            feed[self._inputs[3]] = f0.astype(np.float32)[None]
        feed[self._inputs[-2]] = np.array([0], dtype=np.int64)  # Sprecher-ID
        feed[self._inputs[-1]] = np.random.default_rng(0).standard_normal((1, 192, n_frames)).astype(np.float32)

        wav = np.asarray(self._model.run(None, feed)[0], dtype=np.float32).reshape(-1)
        # Abtastrate des Modells aus der Ausgabelänge ableiten (100 Frames pro Sekunde).
        rate = min((32_000, 40_000, 48_000), key=lambda r: abs(r - len(wav) / n_frames * 100))
        return resample(wav, rate, SAMPLE_RATE)

    def _encode(self, wav16: np.ndarray) -> np.ndarray:
        node = self._encoder.get_inputs()[0]
        shaped = wav16[None, None, :] if len(node.shape) == 3 else wav16[None, :]
        features = self._encoder.run(None, {node.name: shaped})[0]
        if features.shape[1] == 768 and features.shape[2] != 768:
            features = features.transpose(0, 2, 1)
        # ContentVec liefert 20-ms-Frames, RVC erwartet 10 ms.
        return np.repeat(features, 2, axis=1).astype(np.float32)

    @staticmethod
    def _pitch(wav16: np.ndarray, n_frames: int) -> np.ndarray:
        f0, _ = pw.harvest(
            wav16.astype(np.float64), _ENCODER_RATE, f0_floor=_F0_MIN, f0_ceil=_F0_MAX, frame_period=10.0
        )
        return np.pad(f0, (0, max(n_frames - len(f0), 0)))[:n_frames]

    @staticmethod
    def _coarse_pitch(f0: np.ndarray) -> np.ndarray:
        """Quantisiert f0 auf die 255 Mel-Stufen, die RVC als Eingabe erwartet."""
        mel_min = 1127 * np.log(1 + _F0_MIN / 700)
        mel_max = 1127 * np.log(1 + _F0_MAX / 700)
        mel = 1127 * np.log(1 + f0 / 700)
        mel = np.where(mel > 0, (mel - mel_min) * 254 / (mel_max - mel_min) + 1, mel)
        return np.rint(np.clip(mel, 1, 255)).astype(np.int64)
