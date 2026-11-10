"""Wellenform-Anzeige mit Abspielmarke, Auswahlbereich und Zeitleiste."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from ..config import SAMPLE_RATE
from . import theme

_BINS = 1600
_RULER = 18


class WaveformView(QWidget):
    seek_requested = Signal(float)  # Klick: Position 0..1
    selection_changed = Signal(object)  # (start, ende) normiert oder None

    def __init__(self, title: str, color: str, show_ruler: bool = False, hint: str = "", parent=None):
        super().__init__(parent)
        self.setMinimumHeight(110)
        self.setCursor(Qt.IBeamCursor)
        self._title = title
        self._hint = hint
        self._color = QColor(color)
        self._show_ruler = show_ruler
        self._low = self._high = np.zeros(0)
        self._seconds = 0.0
        self._playhead = 0.0
        self._selection: tuple[float, float] | None = None
        self._drag_start: float | None = None
        self._busy = False

    # ----------------------------------------------------------------- Daten

    def set_audio(self, audio: np.ndarray) -> None:
        self._seconds = len(audio) / SAMPLE_RATE
        if len(audio) < _BINS:
            self._low = self._high = np.zeros(0)
        else:
            usable = audio[: len(audio) // _BINS * _BINS].reshape(_BINS, -1)
            # Anzeige auf den Spitzenpegel normieren, damit auch leise Aufnahmen gut erkennbar sind.
            peak = max(float(np.abs(usable).max()), 1e-4)
            self._low, self._high = usable.min(axis=1) / peak, usable.max(axis=1) / peak
        self._busy = False
        self.update()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.update()

    def set_playhead(self, fraction: float) -> None:
        if fraction != self._playhead:
            self._playhead = fraction
            self.update()

    def set_selection(self, selection: tuple[float, float] | None) -> None:
        self._selection = selection
        self.update()

    # ------------------------------------------------------------- Zeichnen

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        top = _RULER if self._show_ruler else 0
        painter.fillRect(self.rect(), QColor(theme.PANEL))
        painter.fillRect(QRectF(0, top, w, h - top), QColor("#101216"))

        if self._show_ruler and self._seconds > 0:
            self._paint_ruler(painter, w)

        if self._selection:
            a, b = self._selection
            painter.fillRect(QRectF(a * w, top, (b - a) * w, h - top), QColor(79, 209, 197, 45))

        mid, scale = top + (h - top) / 2, (h - top) / 2 * 0.92
        if len(self._high):
            xs = np.linspace(0, w, _BINS)
            upper = [QPointF(x, mid - v * scale) for x, v in zip(xs, self._high)]
            lower = [QPointF(x, mid - v * scale) for x, v in zip(xs[::-1], self._low[::-1])]
            color = QColor(self._color)
            color.setAlpha(90 if self._busy else 230)
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawPolygon(QPolygonF(upper + lower))
        painter.setPen(QPen(QColor(theme.BORDER), 1))
        painter.drawLine(QPointF(0, mid), QPointF(w, mid))
        if not self._seconds and self._hint:
            painter.setPen(QColor(theme.MUTED))
            painter.drawText(QRectF(0, top, w, h - top), Qt.AlignCenter, self._hint)

        painter.setPen(QColor(theme.MUTED))
        label = f"{self._title}  ·  wird berechnet …" if self._busy else self._title
        painter.drawText(QRectF(8, top + 4, w - 16, 18), Qt.AlignLeft, label)
        if self._seconds:
            painter.drawText(QRectF(8, top + 4, w - 16, 18), Qt.AlignRight, f"{self._seconds:.2f} s")

        x = self._playhead * w
        painter.setPen(QPen(QColor(theme.TEXT), 1.5))
        painter.drawLine(QPointF(x, top), QPointF(x, h))

    def _paint_ruler(self, painter: QPainter, width: int):
        steps = (0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60)
        step = next((s for s in steps if s / self._seconds * width >= 70), 120)
        painter.setPen(QColor(theme.MUTED))
        t = 0.0
        while t <= self._seconds:
            x = t / self._seconds * width
            painter.drawLine(QPointF(x, _RULER - 5), QPointF(x, _RULER))
            painter.drawText(QPointF(x + 3, _RULER - 5), f"{t:g} s")
            t += step

    # ---------------------------------------------------------------- Maus

    def _fraction(self, event) -> float:
        return float(np.clip(event.position().x() / max(self.width(), 1), 0.0, 1.0))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = self._fraction(event)

    def mouseMoveEvent(self, event):
        if self._drag_start is None:
            return
        current = self._fraction(event)
        if abs(current - self._drag_start) * self.width() > 4:
            self.selection_changed.emit((min(current, self._drag_start), max(current, self._drag_start)))

    def mouseReleaseEvent(self, event):
        if self._drag_start is None:
            return
        current = self._fraction(event)
        if abs(current - self._drag_start) * self.width() <= 4:
            self.selection_changed.emit(None)
            self.seek_requested.emit(current)
        self._drag_start = None
