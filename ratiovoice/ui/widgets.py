"""Wiederverwendbare Bedienelemente."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QGridLayout, QLabel, QSlider, QWidget

from ..params import Param

_STEPS = 1000


class _NoWheelSlider(QSlider):
    """Slider, der das Mausrad ignoriert – sonst verstellt Scrollen im Panel versehentlich Werte."""

    def wheelEvent(self, event):
        event.ignore()


class _NoWheelCombo(QComboBox):
    def wheelEvent(self, event):
        event.ignore()


class ParamControl(QWidget):
    """Regler (oder Auswahlfeld) für einen ``Param``.

    ``changed`` feuert bei jeder Bewegung, ``committed`` beim Loslassen –
    erst dann wird ein Undo-Schritt angelegt. Doppelklick setzt zurück.
    """

    changed = Signal(str, float)
    committed = Signal()

    def __init__(self, param: Param, value: float, parent=None):
        super().__init__(parent)
        self.param = param
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setVerticalSpacing(1)
        layout.addWidget(QLabel(param.label), 0, 0)

        if param.is_choice:
            self._combo = _NoWheelCombo()
            self._combo.addItems(param.choices)
            self._combo.setCurrentIndex(int(round(value)))
            self._combo.currentIndexChanged.connect(self._on_choice)
            layout.addWidget(self._combo, 0, 1, Qt.AlignRight)
            return

        self._value_label = QLabel(param.format(value), objectName="value")
        layout.addWidget(self._value_label, 0, 1, Qt.AlignRight)
        self._slider = _NoWheelSlider(Qt.Horizontal)
        self._slider.setRange(0, _STEPS)
        self._slider.setValue(self._to_slider(value))
        self._slider.valueChanged.connect(self._on_slider)
        self._slider.sliderReleased.connect(self.committed)
        self._slider.setToolTip("Doppelklick: zurücksetzen")
        layout.addWidget(self._slider, 1, 0, 1, 2)

    def mouseDoubleClickEvent(self, _event):
        if not self.param.is_choice:
            self._slider.setValue(self._to_slider(self.param.default))
            self.committed.emit()

    def _to_slider(self, value: float) -> int:
        p = self.param
        if p.log:
            fraction = math.log(value / p.lo) / math.log(p.hi / p.lo)
        else:
            fraction = (value - p.lo) / (p.hi - p.lo)
        return int(round(fraction * _STEPS))

    def _from_slider(self, position: int) -> float:
        p = self.param
        fraction = position / _STEPS
        value = p.lo * (p.hi / p.lo) ** fraction if p.log else p.lo + fraction * (p.hi - p.lo)
        return p.clamp(round(value / p.step) * p.step)

    def _on_slider(self, position: int):
        value = self._from_slider(position)
        self._value_label.setText(self.param.format(value))
        self.changed.emit(self.param.key, value)

    def _on_choice(self, index: int):
        self.changed.emit(self.param.key, float(index))
        self.committed.emit()
