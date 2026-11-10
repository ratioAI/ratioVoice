"""Rechte Seite: aktuelles Profil, KI-Stimme, Stimm-Regler und Effektkette."""

from __future__ import annotations

from PySide6.QtCore import QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..ai import rvc
from ..config import models_dir
from ..dsp import effects
from ..dsp.voice_engine import VOICE_PARAMS
from ..params import defaults
from .widgets import ParamControl


def _card() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame(objectName="card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(12, 10, 12, 12)
    layout.setSpacing(8)
    return frame, layout


class Inspector(QWidget):
    """Bearbeitet das übergebene Einstellungs-Dict direkt und meldet Änderungen."""

    edited = Signal()  # Wert geändert (live, noch kein Undo-Schritt)
    committed = Signal()  # Änderung abgeschlossen -> Undo-Schritt
    ai_changed = Signal()
    save_preset_requested = Signal()
    reset_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, objectName="panel")
        self._settings: dict | None = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        outer.addWidget(self._scroll)

    def set_settings(self, settings: dict) -> None:
        self._settings = settings
        self._rebuild()

    # ---------------------------------------------------------------- Aufbau

    def _rebuild(self) -> None:
        scroll_pos = self._scroll.verticalScrollBar().value()
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(10)

        layout.addWidget(QLabel("AKTUELLES PROFIL", objectName="section"))
        title = QLabel(self._settings["profile"], objectName="title")
        title.setWordWrap(True)
        layout.addWidget(title)
        buttons = QHBoxLayout()
        save = QPushButton("Als Preset speichern")
        save.clicked.connect(self.save_preset_requested)
        reset = QPushButton("Zurücksetzen")
        reset.setToolTip("Alle Regler neutral, Effektkette leeren")
        reset.clicked.connect(self.reset_requested)
        buttons.addWidget(save)
        buttons.addWidget(reset)
        layout.addLayout(buttons)

        layout.addWidget(QLabel("STIMME", objectName="section"))
        layout.addWidget(self._voice_card())
        layout.addWidget(QLabel("KI-STIMME (VOICE CONVERSION)", objectName="section"))
        layout.addWidget(self._ai_card())

        header = QHBoxLayout()
        header.addWidget(QLabel("EFFEKTKETTE", objectName="section"))
        header.addStretch()
        add = QPushButton("+ Effekt")
        add.setMenu(self._add_menu(add))
        header.addWidget(add)
        layout.addLayout(header)
        chain = self._settings["chain"]
        if not chain:
            layout.addWidget(QLabel("Noch keine Effekte – über „+ Effekt“ hinzufügen.", objectName="muted"))
        for index in range(len(chain)):
            layout.addWidget(self._effect_card(index))
        layout.addStretch()

        self._scroll.setWidget(content)
        QTimer.singleShot(0, lambda: self._scroll.verticalScrollBar().setValue(scroll_pos))

    def _voice_card(self) -> QFrame:
        frame, layout = _card()
        voice = self._settings["voice"]
        for param in VOICE_PARAMS:
            control = ParamControl(param, voice[param.key])
            control.changed.connect(self._set_voice)
            control.committed.connect(self.committed)
            layout.addWidget(control)
        return frame

    def _ai_card(self) -> QFrame:
        frame, layout = _card()
        ai = self._settings["ai"]
        models = rvc.list_models()
        row = QHBoxLayout()
        combo = QComboBox()
        combo.addItem("Aus (nur DSP)", "")
        for name in models:
            combo.addItem(name, name)
        if ai["model"] and ai["model"] not in models:
            combo.addItem(f"{ai['model']} (fehlt)", ai["model"])
        combo.setCurrentIndex(max(combo.findData(ai["model"]), 0))
        transpose = QSpinBox()
        transpose.setRange(-24, 24)
        transpose.setSuffix(" HT")
        transpose.setValue(ai["transpose"])
        transpose.setToolTip("Tonhöhe an die Zielstimme anpassen (z. B. +12 für Mann → Frau)")
        row.addWidget(combo, 1)
        row.addWidget(transpose)
        layout.addLayout(row)

        def apply():
            ai["model"], ai["transpose"] = combo.currentData(), transpose.value()
            self.ai_changed.emit()
            self.committed.emit()

        combo.activated.connect(apply)
        transpose.editingFinished.connect(apply)

        if rvc.encoder_path() is None:
            hint = f"Encoder „{rvc.ENCODER_NAMES[0]}“ und RVC-Stimmmodelle (.onnx) in den Modellordner legen."
        elif not models:
            hint = "Noch keine Stimmmodelle (.onnx) im Modellordner."
        else:
            hint = "Ersetzt die Klangfarbe durch die Zielstimme; Regler und Effekte wirken danach."
        label = QLabel(hint, objectName="muted")
        label.setWordWrap(True)
        layout.addWidget(label)
        folder = QPushButton("Modellordner öffnen")
        folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(models_dir()))))
        layout.addWidget(folder)
        return frame

    def _effect_card(self, index: int) -> QFrame:
        entry = self._settings["chain"][index]
        cls = effects.EFFECTS[entry["id"]]
        frame, layout = _card()

        header = QHBoxLayout()
        toggle = QCheckBox(cls.label)
        toggle.setChecked(entry["on"])
        toggle.setToolTip("Effekt ein-/ausschalten")
        toggle.toggled.connect(lambda on: self._toggle(index, on))
        header.addWidget(toggle)
        header.addStretch()
        for text, tip, action in (
            ("↑", "Früher in der Kette", lambda: self._move(index, -1)),
            ("↓", "Später in der Kette", lambda: self._move(index, +1)),
            ("✕", "Effekt entfernen", lambda: self._remove(index)),
        ):
            button = QPushButton(text, objectName="mini")
            button.setToolTip(tip)
            button.clicked.connect(action)
            header.addWidget(button)
        layout.addLayout(header)

        for param in cls.params:
            control = ParamControl(param, entry["params"][param.key])
            control.changed.connect(lambda key, value, i=index: self._set_effect(i, key, value))
            control.committed.connect(self.committed)
            layout.addWidget(control)
        return frame

    def _add_menu(self, parent) -> QMenu:
        menu = QMenu(parent)
        for effect_id, cls in effects.EFFECTS.items():
            menu.addAction(cls.label, lambda eid=effect_id: self._add(eid))
        return menu

    # ------------------------------------------------------------ Änderungen

    def _set_voice(self, key: str, value: float) -> None:
        self._settings["voice"][key] = value
        self.edited.emit()

    def _set_effect(self, index: int, key: str, value: float) -> None:
        self._settings["chain"][index]["params"][key] = value
        self.edited.emit()

    def _toggle(self, index: int, on: bool) -> None:
        self._settings["chain"][index]["on"] = on
        self.edited.emit()
        self.committed.emit()

    def _structure_changed(self) -> None:
        self._rebuild()
        self.edited.emit()
        self.committed.emit()

    def _add(self, effect_id: str) -> None:
        params = defaults(effects.EFFECTS[effect_id].params)
        self._settings["chain"].append({"id": effect_id, "on": True, "params": params})
        self._structure_changed()

    def _remove(self, index: int) -> None:
        del self._settings["chain"][index]
        self._structure_changed()

    def _move(self, index: int, delta: int) -> None:
        chain = self._settings["chain"]
        target = index + delta
        if 0 <= target < len(chain):
            chain[index], chain[target] = chain[target], chain[index]
            self._structure_changed()
