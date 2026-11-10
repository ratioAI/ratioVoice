"""Hauptfenster: verbindet Bibliothek, Wellenformen, Inspector, Audio und Rechenprozess."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .. import audio_io, settings as settings_model
from ..audio.engine import LIVE, PLAYING, RECORDING, AudioEngine, AudioError
from ..config import APP_NAME, MAX_CLIP_SECONDS, SAMPLE_RATE, recordings_dir
from ..history import History
from ..profiles.store import ProfileStore
from ..worker import Worker
from . import theme
from .inspector import Inspector
from .library_panel import LibraryPanel
from .waveform import WaveformView

_EMPTY = np.zeros(0, dtype=np.float32)


class _Bridge(QObject):
    """Bringt Ergebnisse des Rechenprozesses sicher in den GUI-Thread."""

    finished = Signal(str, int, object)  # Auftragsart, Auftragsnummer, Future


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1360, 820)
        self.setAcceptDrops(True)

        self.engine = AudioEngine()
        self.worker = Worker()
        self.store = ProfileStore()
        self.history = History()
        self.settings = settings_model.neutral()
        self.clip = _EMPTY
        self.clip_name = ""
        self.rendered = _EMPTY
        self._selection: tuple[float, float] | None = None
        self._job = 0  # laufende Nummer; nur das Ergebnis des neuesten Auftrags zählt
        self._pending: list[tuple[str, object]] = []
        self._analysis_ready = False
        self._applied_voice: dict | None = None
        self._applied_ai: dict | None = None

        self._bridge = _Bridge()
        self._bridge.finished.connect(self._on_job_finished)
        self._voice_timer = self._single_shot(90, self._request_voice)
        self._render_timer = self._single_shot(250, self._request_render)

        self._build_ui()
        self._bind_shortcuts()
        self._apply_settings(push=False)
        self.history.reset(self._snapshot())
        self._update_buttons()

        self._ui_timer = QTimer(self)
        self._ui_timer.timeout.connect(self._tick)
        self._ui_timer.start(33)

    def _single_shot(self, ms: int, slot) -> QTimer:
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(ms)
        timer.timeout.connect(slot)
        return timer

    # ================================================================ Aufbau

    def _build_ui(self) -> None:
        self.library = LibraryPanel(self.store)
        self.library.profile_chosen.connect(self._choose_profile)
        self.inspector = Inspector()
        self.inspector.edited.connect(self._on_edited)
        self.inspector.committed.connect(self._commit)
        self.inspector.ai_changed.connect(self._refresh_source)
        self.inspector.save_preset_requested.connect(self._save_preset)
        self.inspector.reset_requested.connect(lambda: self._choose_profile(settings_model.neutral()))

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.library)
        splitter.addWidget(self._build_center())
        splitter.addWidget(self.inspector)
        splitter.setSizes([250, 740, 370])
        splitter.setStretchFactor(1, 1)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(splitter, 1)
        layout.addWidget(self._build_transport())
        self.setCentralWidget(root)
        self.statusBar().showMessage("Bereit – Aufnahme starten oder Audiodatei importieren.")

    def _build_center(self) -> QWidget:
        center = QWidget()
        layout = QVBoxLayout(center)
        layout.setContentsMargins(14, 14, 14, 10)
        layout.setSpacing(10)

        top = QHBoxLayout()
        self.clip_label = QLabel("Keine Aufnahme geladen", objectName="title")
        top.addWidget(self.clip_label, 1)
        self.btn_original = QPushButton("Original")
        self.btn_processed = QPushButton("Bearbeitet")
        for button, processed in ((self.btn_original, False), (self.btn_processed, True)):
            button.setCheckable(True)
            button.setToolTip("A/B-Vergleich – auch während der Wiedergabe (Taste A)")
            button.clicked.connect(lambda _=False, p=processed: self._set_monitor(p))
            top.addWidget(button)
        self.btn_processed.setChecked(True)
        self.btn_live = QPushButton("🎤  Live-Mikrofon")
        self.btn_live.setCheckable(True)
        self.btn_live.setToolTip("Mikrofon in Echtzeit verzerrt abhören (Kopfhörer empfohlen)")
        self.btn_live.clicked.connect(self._toggle_live)
        top.addSpacing(12)
        top.addWidget(self.btn_live)
        layout.addLayout(top)

        hint = "Aufnahme starten (●) oder Audiodatei hierher ziehen"
        self.wave_original = WaveformView("Original", theme.ORIGINAL, show_ruler=True, hint=hint)
        self.wave_processed = WaveformView("Bearbeitet", theme.ACCENT)
        for wave in (self.wave_original, self.wave_processed):
            wave.seek_requested.connect(self._seek)
            wave.selection_changed.connect(self._set_selection)
            layout.addWidget(wave, 1)

        self.meter = QProgressBar()
        self.meter.setRange(0, 100)
        self.meter.setTextVisible(False)
        self.meter.setFixedHeight(5)
        self.meter.setStyleSheet(
            f"QProgressBar {{ background: {theme.BORDER}; border: none; border-radius: 2px; }}"
            f"QProgressBar::chunk {{ background: {theme.ACCENT}; border-radius: 2px; }}"
        )
        layout.addWidget(self.meter)
        return center

    def _build_transport(self) -> QWidget:
        bar = QWidget(objectName="transport")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 10, 14, 10)

        def button(text, tip, slot, name="transportBtn", checkable=False):
            b = QPushButton(text, objectName=name)
            b.setToolTip(tip)
            b.setCheckable(checkable)
            b.setFocusPolicy(Qt.NoFocus)  # Leertaste soll immer Play/Pause bleiben
            b.clicked.connect(slot)
            layout.addWidget(b)
            return b

        self.btn_record = button("●  Aufnahme", "Aufnahme starten/beenden (R)", self._toggle_record, "record", True)
        self.btn_play = button("▶", "Wiedergabe / Pause (Leertaste)", self._toggle_play)
        self.btn_stop = button("■", "Stopp", self._stop)
        self.btn_loop = button("⟲", "Schleife (Auswahl oder ganze Aufnahme)", self._toggle_loop, checkable=True)
        self.time_label = QLabel("0:00.0 / 0:00.0", objectName="muted")
        layout.addSpacing(8)
        layout.addWidget(self.time_label)
        layout.addStretch()
        self.btn_undo = button("↶", "Rückgängig (Strg+Z)", self._undo)
        self.btn_redo = button("↷", "Wiederholen (Strg+Y)", self._redo)
        self.btn_crop = button("Zuschneiden", "Aufnahme auf die Auswahl kürzen", self._crop, "")
        layout.addStretch()
        button("Importieren …", "Audiodatei laden (Strg+O)", self._import_dialog, "")
        self.btn_export = QPushButton("Exportieren", objectName="primary")
        menu = QMenu(self.btn_export)
        menu.addAction("Bearbeitete Stimme …", lambda: self._export("processed"))
        menu.addAction("Nur Auswahl (bearbeitet) …", lambda: self._export("selection"))
        menu.addAction("Original …", lambda: self._export("original"))
        self.btn_export.setMenu(menu)
        layout.addWidget(self.btn_export)
        button("⚙", "Audiogeräte", self._device_dialog)
        return bar

    def _bind_shortcuts(self) -> None:
        for keys, slot in (
            ("Space", self._toggle_play),
            ("R", self.btn_record.click),
            ("A", lambda: self._set_monitor(not self.engine.monitor_processed)),
            ("Ctrl+Z", self._undo),
            ("Ctrl+Y", self._redo),
            ("Ctrl+Shift+Z", self._redo),
            ("Ctrl+O", self._import_dialog),
            ("Ctrl+E", lambda: self._export("processed")),
        ):
            QShortcut(QKeySequence(keys), self, activated=slot)

    # ====================================================== Aufnahme / Datei

    def _set_clip(self, audio: np.ndarray, name: str) -> None:
        """Macht ``audio`` zur aktuellen (unveränderlichen) Originalaufnahme."""
        self.engine.stop_stream()
        self.clip, self.clip_name = audio, name
        self.rendered = _EMPTY
        self.engine.original = audio
        self.engine.voiced = _EMPTY
        self.engine.seek(0.0)
        self._set_selection(None)
        self.clip_label.setText(name or "Keine Aufnahme geladen")
        self.wave_original.set_audio(audio)
        self.wave_processed.set_audio(_EMPTY)
        self._refresh_source()
        self._update_buttons()

    def _load_file(self, path: str) -> None:
        try:
            audio = audio_io.load(path)
        except Exception as exc:
            self._warn(f"Die Datei konnte nicht gelesen werden:\n{exc}")
            return
        if len(audio) > MAX_CLIP_SECONDS * SAMPLE_RATE:
            audio = audio[: MAX_CLIP_SECONDS * SAMPLE_RATE]
            self.statusBar().showMessage(f"Datei auf {MAX_CLIP_SECONDS // 60} Minuten gekürzt.", 6000)
        self._set_clip(audio, Path(path).name)
        self._commit()

    def _import_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Audiodatei importieren", "", audio_io.IMPORT_FILTER)
        if path:
            self._load_file(path)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            self._load_file(urls[0].toLocalFile())

    def _toggle_record(self) -> None:
        if self.engine.mode == RECORDING:
            audio = self.engine.stop_recording()
            self.btn_record.setText("●  Aufnahme")
            if len(audio) < SAMPLE_RATE // 5:
                self.statusBar().showMessage("Aufnahme zu kurz – verworfen.", 4000)
            else:
                # Die Originalaufnahme wird immer separat als Datei aufbewahrt.
                path = recordings_dir() / time.strftime("Aufnahme_%Y-%m-%d_%H-%M-%S.wav")
                audio_io.save(path, audio)
                self._set_clip(audio, path.name)
                self._commit()
                self.statusBar().showMessage(f"Original gespeichert: {path}", 8000)
        else:
            try:
                self.engine.record()
                self.btn_record.setText("■  Aufnahme beenden")
            except AudioError as exc:
                self._warn(str(exc))
        self._update_buttons()

    def _export(self, what: str) -> None:
        if not len(self.clip):
            return
        if what == "selection" and not self._selection:
            self._warn("Es ist kein Bereich ausgewählt. Mit gedrückter Maustaste über die Wellenform ziehen.")
            return
        stem = Path(self.clip_name).stem
        suffix = "" if what == "original" else f"_{self.settings['profile']}"
        default = "".join(c if c.isalnum() or c in " _-" else "-" for c in stem + suffix)
        path, chosen = QFileDialog.getSaveFileName(
            self, "Exportieren", default, ";;".join(audio_io.EXPORT_FILTERS)
        )
        if not path:
            return
        if not Path(path).suffix:
            path += audio_io.EXPORT_FILTERS.get(chosen, ".wav")
        self.setCursor(Qt.WaitCursor)
        try:
            audio = self.clip if what == "original" else self._render_now()
            if what == "selection":
                a, b = self._selection
                length = int(round(len(self.clip) / self.settings["voice"]["speed"]))
                audio = audio[int(a * length) : int(b * length)]
            saved = audio_io.save(path, audio)
            self.statusBar().showMessage(f"Exportiert: {saved}", 8000)
        except Exception as exc:
            self._warn(f"Export fehlgeschlagen:\n{exc}")
        finally:
            self.unsetCursor()

    def _render_now(self) -> np.ndarray:
        """Rechnet den aktuellen Stand vollständig durch (blockierend, für den Export)."""
        self._voice_timer.stop()
        self._render_timer.stop()
        self.worker.synthesize(self.settings["voice"]).result()
        return self.worker.render(self.settings["chain"]).result()

    # ========================================================== Einstellungen

    def _choose_profile(self, profile_settings: dict) -> None:
        new = settings_model.clone(profile_settings)
        if not new["ai"]["model"]:
            new["ai"] = dict(self.settings["ai"])  # KI-Zielstimme bleibt beim Profilwechsel erhalten
        self.settings = new
        self._apply_settings(push=True)

    def _apply_settings(self, push: bool) -> None:
        """Übernimmt ``self.settings`` vollständig (Profilwechsel, Undo, Reset)."""
        self.inspector.set_settings(self.settings)
        if self._applied_ai is not None and self.settings["ai"] != self._applied_ai:
            self._refresh_source()
        self._on_edited()
        if push:
            self._commit()

    def _on_edited(self) -> None:
        """Reagiert live auf jede Regleränderung."""
        self.engine.chain.configure(self.settings["chain"])
        self.engine.shifter.set_voice(self.settings["voice"])
        if self.settings["voice"] != self._applied_voice:
            self._voice_timer.start()
        else:
            self._render_timer.start()
        if len(self.clip):
            self.wave_processed.set_busy(True)

    def _save_preset(self) -> None:
        name, ok = QInputDialog.getText(self, "Preset speichern", "Name des Stimmenprofils:", text=self.settings["profile"])
        name = name.strip()
        if ok and name:
            self.settings["profile"] = name
            self.store.save_preset(name, self.settings)
            self.library.refresh()
            self.inspector.set_settings(self.settings)
            self.statusBar().showMessage(f"Preset „{name}“ gespeichert.", 5000)

    # ================================================================== Undo

    def _snapshot(self) -> dict:
        return {"clip": self.clip, "name": self.clip_name, "settings": settings_model.clone(self.settings)}

    def _commit(self) -> None:
        self.history.push(self._snapshot())
        self._update_buttons()

    def _restore(self, state: dict | None) -> None:
        if state is None:
            return
        self.settings = settings_model.clone(state["settings"])
        if state["clip"] is not self.clip:
            self._applied_ai = dict(self.settings["ai"])
            self._set_clip(state["clip"], state["name"])
        self._apply_settings(push=False)
        self._update_buttons()

    def _undo(self) -> None:
        self._restore(self.history.undo())

    def _redo(self) -> None:
        self._restore(self.history.redo())

    # ========================================================= Rechenaufträge

    def _submit(self, kind: str, future) -> None:
        self._job += 1
        job = self._job
        self._pending.append((kind, future))
        future.add_done_callback(lambda f: self._bridge.finished.emit(kind, job, f))

    def _cancel_pending(self, kinds: tuple[str, ...]) -> None:
        """Verwirft noch nicht begonnene Aufträge, die inzwischen überholt sind."""
        for kind, future in self._pending:
            if kind in kinds:
                future.cancel()
        self._pending = [(k, f) for k, f in self._pending if not f.done()]

    def _refresh_source(self) -> None:
        """Quelle neu aufbereiten: optional KI-Umwandlung, danach Analyse."""
        self._applied_ai = dict(self.settings["ai"])
        self._applied_voice = None
        if not len(self.clip):
            return
        self._cancel_pending(("convert", "analyze", "voice", "render"))
        self._analysis_ready = False
        self.wave_processed.set_busy(True)
        ai = self.settings["ai"]
        if ai["model"]:
            self.statusBar().showMessage(f"KI-Umwandlung mit „{ai['model']}“ läuft …")
            self._submit("convert", self.worker.convert(self.clip, ai["model"], ai["transpose"]))
        else:
            self._analyze(self.clip)

    def _analyze(self, source: np.ndarray) -> None:
        self.statusBar().showMessage("Stimme wird analysiert …")
        self._submit("analyze", self.worker.analyze(source))

    def _request_voice(self) -> None:
        if not self._analysis_ready:
            return  # wird nach Abschluss der Analyse automatisch nachgeholt
        self._cancel_pending(("voice", "render"))
        self._applied_voice = dict(self.settings["voice"])
        self._submit("voice", self.worker.synthesize(self._applied_voice))

    def _request_render(self) -> None:
        if self._analysis_ready and self._applied_voice is not None:
            self._cancel_pending(("render",))
            self._submit("render", self.worker.render(settings_model.clone(self.settings)["chain"]))

    def _on_job_finished(self, kind: str, job: int, future) -> None:
        self._pending = [(k, f) for k, f in self._pending if f is not future]
        if future.cancelled():
            return
        error = future.exception()
        if error is not None:
            self.wave_processed.set_busy(False)
            self.statusBar().clearMessage()
            if kind == "convert":
                self.settings["ai"]["model"] = ""
                self._applied_ai = dict(self.settings["ai"])
                self.inspector.set_settings(self.settings)
                self._analyze(self.clip)
            self._warn(str(error))
            return
        result = future.result()
        if kind == "convert":
            self._analyze(result)
        elif kind == "analyze":
            self.statusBar().showMessage("Analyse abgeschlossen.", 3000)
            self._analysis_ready = True
            self._request_voice()
        elif kind == "voice":
            self.engine.voiced = result
            self._request_render()
        elif kind == "render" and job == self._job:
            self.rendered = result
            # Ausklang (Hall/Echo) für die Anzeige abschneiden, damit beide Wellenformen
            # dieselbe Zeitachse haben.
            self.wave_processed.set_audio(result[: len(self.engine.voiced)])

    # ============================================================== Transport

    def _toggle_play(self) -> None:
        if not len(self.clip) or self.engine.mode in (RECORDING, LIVE):
            return
        try:
            if self.engine.mode == PLAYING:
                self.engine.pause()
            else:
                self.engine.play()
        except AudioError as exc:
            self._warn(str(exc))
        self._update_buttons()

    def _stop(self) -> None:
        if self.engine.mode == RECORDING:
            self._toggle_record()
            return
        self.engine.stop()
        self.btn_live.setChecked(False)
        self._update_buttons()

    def _toggle_loop(self) -> None:
        self.engine.loop = self.btn_loop.isChecked()

    def _toggle_live(self) -> None:
        try:
            if self.btn_live.isChecked():
                self.engine.start_live()
                self.statusBar().showMessage(
                    "Live-Modus: Tonhöhe, Formant, Flüstern und alle Effekte wirken in Echtzeit "
                    "(übrige Stimm-Regler nur bei Aufnahmen)."
                )
            else:
                self.engine.stop_stream()
                self.statusBar().clearMessage()
        except AudioError as exc:
            self.btn_live.setChecked(False)
            self._warn(str(exc))
        self._update_buttons()

    def _set_monitor(self, processed: bool) -> None:
        self.engine.monitor_processed = processed
        self.btn_processed.setChecked(processed)
        self.btn_original.setChecked(not processed)

    def _seek(self, fraction: float) -> None:
        self.engine.seek(fraction)

    def _set_selection(self, selection) -> None:
        self._selection = selection
        self.engine.region = selection
        self.wave_original.set_selection(selection)
        self.wave_processed.set_selection(selection)
        self.btn_crop.setEnabled(bool(selection))

    def _crop(self) -> None:
        if not self._selection or not len(self.clip):
            return
        a, b = self._selection
        piece = self.clip[int(a * len(self.clip)) : int(b * len(self.clip))].copy()
        if len(piece) > SAMPLE_RATE // 10:
            self._set_clip(piece, self.clip_name)
            self._commit()

    def _tick(self) -> None:
        engine = self.engine
        if engine.finished:
            engine.finished = False
            engine.stop()
            self._update_buttons()
        position = engine.position
        self.wave_original.set_playhead(position)
        self.wave_processed.set_playhead(position)
        self.meter.setValue(int(min(engine.level, 1.0) ** 0.5 * 100))
        total = len(self.clip) / SAMPLE_RATE
        if engine.mode == RECORDING:
            seconds = sum(len(block) for block in engine._recorded) / SAMPLE_RATE
            self.time_label.setText(f"Aufnahme läuft  {self._clock(seconds)}")
        else:
            self.time_label.setText(f"{self._clock(position * total)} / {self._clock(total)}")

    @staticmethod
    def _clock(seconds: float) -> str:
        return f"{int(seconds // 60)}:{seconds % 60:04.1f}"

    def _update_buttons(self) -> None:
        mode, has_clip = self.engine.mode, bool(len(self.clip))
        self.btn_play.setText("⏸" if mode == PLAYING else "▶")
        self.btn_play.setEnabled(has_clip and mode not in (RECORDING, LIVE))
        self.btn_record.setChecked(mode == RECORDING)
        self.btn_record.setEnabled(mode != LIVE)
        self.btn_live.setEnabled(mode != RECORDING)
        self.btn_export.setEnabled(has_clip)
        self.btn_crop.setEnabled(has_clip and bool(self._selection))
        self.btn_undo.setEnabled(self.history.can_undo)
        self.btn_redo.setEnabled(self.history.can_redo)

    # ================================================================ Sonstiges

    def _device_dialog(self) -> None:
        inputs, outputs = self.engine.devices()
        dialog = QDialog(self)
        dialog.setWindowTitle("Audiogeräte")
        form = QFormLayout(dialog)
        combos = []
        for label, devices, current in (
            ("Mikrofon", inputs, self.engine.input_device),
            ("Wiedergabe", outputs, self.engine.output_device),
        ):
            combo = QComboBox()
            combo.addItem("Systemstandard", None)
            for index, name in devices:
                combo.addItem(name, index)
            combo.setCurrentIndex(max(combo.findData(current), 0))
            form.addRow(label, combo)
            combos.append(combo)
        if not self.engine.available():
            form.addRow(QLabel("Kein Audiosystem gefunden.", objectName="muted"))
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() == QDialog.Accepted:
            self.engine.stop_stream()
            self.btn_live.setChecked(False)
            self.engine.input_device = combos[0].currentData()
            self.engine.output_device = combos[1].currentData()
            self._update_buttons()

    def _warn(self, message: str) -> None:
        QMessageBox.warning(self, APP_NAME, message)

    def closeEvent(self, event):
        self._ui_timer.stop()
        self.engine.stop_stream()
        self.worker.shutdown()
        super().closeEvent(event)
