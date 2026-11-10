"""Echtzeit-Audio: Wiedergabe, Aufnahme und Live-Mikrofon (über PortAudio).

Wiedergabe:   Stimm-Puffer -> Effektkette (live) -> Lautsprecher
Live-Modus:   Mikrofon -> Live-Shifter -> Effektkette -> Lautsprecher
"""

from __future__ import annotations

import numpy as np

from ..config import BLOCK_SIZE, SAMPLE_RATE
from ..dsp.chain import Chain
from ..dsp.live_shifter import LiveShifter

try:
    import sounddevice as sd
except Exception as exc:  # PortAudio fehlt (z. B. auf Servern ohne Soundkarte)
    sd = None
    _IMPORT_ERROR = str(exc)

IDLE, PLAYING, RECORDING, LIVE = "idle", "playing", "recording", "live"
_EMPTY = np.zeros(0, dtype=np.float32)


class AudioError(RuntimeError):
    pass


class AudioEngine:
    def __init__(self):
        self.chain = Chain(SAMPLE_RATE)
        self.shifter = LiveShifter(SAMPLE_RATE)
        self.original = _EMPTY  # unbearbeitete Aufnahme
        self.voiced = _EMPTY  # Ergebnis der Stimm-Engine (vor der Effektkette)
        self.monitor_processed = True  # A/B: bearbeitet oder Original hören
        self.loop = False
        self.region: tuple[float, float] | None = None  # Auswahl, normiert 0..1
        self.mode = IDLE
        self.level = 0.0
        self.finished = False  # wird vom Audio-Thread gesetzt, von der UI abgeholt
        self.input_device: int | None = None
        self.output_device: int | None = None
        self._stream = None
        self._buffer = _EMPTY
        self._pos = 0
        self._tail = 0
        self._recorded: list[np.ndarray] = []

    # ------------------------------------------------------------- Geräte

    @staticmethod
    def available() -> bool:
        return sd is not None

    @staticmethod
    def devices() -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
        """(Eingabegeräte, Ausgabegeräte) jeweils als (Index, Name)."""
        if sd is None:
            return [], []
        apis = sd.query_hostapis()
        inputs, outputs = [], []
        for index, dev in enumerate(sd.query_devices()):
            name = f"{dev['name']} ({apis[dev['hostapi']]['name']})"
            if dev["max_input_channels"] > 0:
                inputs.append((index, name))
            if dev["max_output_channels"] > 0:
                outputs.append((index, name))
        return inputs, outputs

    # ---------------------------------------------------------- Transport

    @property
    def position(self) -> float:
        """Abspielposition, normiert auf 0..1."""
        return self._pos / len(self._buffer) if len(self._buffer) else 0.0

    def seek(self, fraction: float) -> None:
        buffer = self._current_buffer()
        self._buffer = buffer
        self._pos = int(np.clip(fraction, 0.0, 1.0) * len(buffer))

    def play(self) -> None:
        if not len(self.original):
            return
        self.stop_stream()
        start, end = self.region or (0.0, 1.0)
        if not start <= self.position < end - 1e-4:
            self.seek(start)
        self.finished = False
        self._tail = 0
        self._open(sd.OutputStream, self._play_callback, latency="high")
        self.mode = PLAYING

    def pause(self) -> None:
        self.stop_stream()

    def stop(self) -> None:
        self.stop_stream()
        self.seek((self.region or (0.0, 1.0))[0])

    def record(self) -> None:
        self.stop_stream()
        self._recorded = []
        self._open(sd.InputStream, self._record_callback, latency="low")
        self.mode = RECORDING

    def stop_recording(self) -> np.ndarray:
        self.stop_stream()
        audio = np.concatenate(self._recorded) if self._recorded else _EMPTY
        self._recorded = []
        return audio

    def start_live(self) -> None:
        self.stop_stream()
        self._open(sd.Stream, self._live_callback, latency="low")
        self.mode = LIVE

    def stop_stream(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None
        self.mode = IDLE
        self.level = 0.0

    def _open(self, stream_cls, callback, latency: str) -> None:
        if sd is None:
            raise AudioError(f"Kein Audiosystem verfügbar: {_IMPORT_ERROR}")
        if stream_cls is sd.InputStream:
            device, channels = self.input_device, 1
        elif stream_cls is sd.OutputStream:
            device, channels = self.output_device, 2
        else:
            device, channels = (self.input_device, self.output_device), (1, 2)
        try:
            self._stream = stream_cls(
                samplerate=SAMPLE_RATE,
                blocksize=BLOCK_SIZE,
                device=device,
                channels=channels,
                dtype="float32",
                latency=latency,
                callback=callback,
            )
            self._stream.start()
        except Exception as exc:
            self._stream = None
            raise AudioError(f"Audiogerät konnte nicht geöffnet werden:\n{exc}") from exc

    # ---------------------------------------------------------- Callbacks

    def _current_buffer(self) -> np.ndarray:
        return self.voiced if self.monitor_processed and len(self.voiced) else self.original

    def next_block(self, frames: int) -> np.ndarray:
        """Liefert den nächsten Wiedergabeblock (auch ohne Soundkarte testbar)."""
        buffer = self._current_buffer()
        if buffer is not self._buffer:
            # Puffer wurde getauscht (A/B-Vergleich oder neu berechnete Stimme):
            # Position proportional übernehmen, damit die Wiedergabe weiterläuft.
            ratio = self._pos / len(self._buffer) if len(self._buffer) else 0.0
            self._buffer, self._pos = buffer, int(ratio * len(buffer))

        start, end = self.region or (0.0, 1.0)
        first, last = int(start * len(buffer)), int(end * len(buffer))
        block = np.zeros(frames, dtype=np.float32)
        filled = 0
        while filled < frames and not self._tail:
            take = min(frames - filled, last - self._pos)
            if take > 0:
                block[filled : filled + take] = buffer[self._pos : self._pos + take]
                self._pos += take
                filled += take
            if self._pos >= last:
                if self.loop and last > first:
                    self._pos = first
                else:
                    # Ende erreicht: Hall und Echo noch ausklingen lassen.
                    self._tail = int(self.chain.tail_seconds * SAMPLE_RATE) + 1

        if self.monitor_processed:
            block = self.chain.process(block)
        if self._tail:
            self._tail -= frames - filled
            silent = filled == 0 and np.abs(block).max(initial=0.0) < 1e-4
            if self._tail <= 0 or silent or not self.monitor_processed:
                self._tail = 0
                self.finished = True
        return block

    def _play_callback(self, outdata, frames, _time, _status):
        block = self.next_block(frames)
        outdata[:] = block[:, None]
        self.level = float(np.abs(block).max(initial=0.0))
        if self.finished:
            raise sd.CallbackStop

    def _record_callback(self, indata, _frames, _time, _status):
        block = indata[:, 0].copy()
        self._recorded.append(block)
        self.level = float(np.abs(block).max(initial=0.0))

    def _live_callback(self, indata, outdata, _frames, _time, _status):
        block = indata[:, 0].astype(np.float64)
        if self.monitor_processed:
            block = self.chain.process(self.shifter.process(block))
        outdata[:] = np.asarray(block, dtype=np.float32)[:, None]
        self.level = float(np.abs(block).max(initial=0.0))
