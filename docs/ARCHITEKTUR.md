# Architektur und Technologie-Entscheidungen

## Signalweg

```
Aufnahme/Datei ──► [KI-Voice-Conversion, optional] ──► Stimm-Engine (WORLD) ──► Effektkette ──► Ausgabe/Export
                         ai/rvc.py                      dsp/voice_engine.py      dsp/chain.py
Live-Mikrofon ───────────────────────────────────────► Live-Shifter ──────────► Effektkette ──► Lautsprecher
                                                        dsp/live_shifter.py
```

| Modul | Aufgabe |
|---|---|
| `params.py` | Beschreibung eines Reglers (`Param`); daraus baut die UI Slider automatisch |
| `settings.py` | Datenmodell einer Stimmeinstellung (Profil = Preset = Undo-Zustand) |
| `dsp/voice_engine.py` | Analyse/Synthese mit WORLD: Tonhöhe, Formant, Tempo, Melodie, Hauch, Rauheit, Autotune |
| `dsp/live_shifter.py` | Echtzeit-Pitch/Formant per Phase-Vocoder mit cepstraler Hüllkurve |
| `dsp/effects/` | 19 Streaming-Effekte + Registry |
| `dsp/chain.py` | Effektkette (Echtzeit und Offline-Rendern mit demselben Code) |
| `ai/rvc.py` | RVC-Inferenz über ONNX Runtime |
| `audio/engine.py` | Wiedergabe, Aufnahme, Live-Modus über PortAudio (WASAPI) |
| `worker.py` | Eigener Rechenprozess für Analyse, Synthese, KI, Rendern |
| `profiles/` | 29 Bibliotheksprofile, Favoriten, eigene Presets |
| `ui/` | PySide6-Oberfläche |

## Warum diese Technologien

### Pitch und Formant: WORLD-Vocoder (pyworld)

Geprüfte Alternativen:

| Verfahren | Bewertung |
|---|---|
| Resampling (Audacity „Tempo/Tonhöhe ändern“) | Tonhöhe, Tempo und Formanten hängen zusammen – genau das Problem aus der Aufgabenstellung |
| Phase-Vocoder / Rubber Band | Sehr gut für Musik und Time-Stretching; Formanterhalt möglich, aber kein freier Formant-Regler und keine Kontrolle über Sprachmelodie, Hauch oder Rauheit |
| PSOLA (Praat) | Gute Sprachqualität bei kleinen Verschiebungen, bei großen Sprüngen und rauen Stimmen instabil |
| **WORLD** | Zerlegt Sprache in Grundfrequenz, spektrale Hüllkurve und Aperiodizität. Jede Größe ist einzeln veränderbar; Synthese ~25× schneller als Echtzeit |
| Neuronale Vocoder | Höchste Natürlichkeit, aber an trainierte Stimmen gebunden → als KI-Modul umgesetzt |

WORLD macht aus den Wünschen „tiefer ohne langsamer“, „Formant unabhängig“, „Flüstern“, „alte Stimme“,
„Autotune“ jeweils eine einfache Operation auf einer der drei Komponenten. Die Analyse (ca. 0,35× Echtzeit)
läuft einmal pro Aufnahme, danach kostet jede Regleränderung nur die Synthese.

Bei neutralen Reglern wird das Originalsignal bit-genau durchgereicht – der Vocoder färbt also nur,
wenn er gebraucht wird.

### Live-Betrieb: Phase-Vocoder mit Hüllkurventrennung

WORLD braucht Kontext und eignet sich nicht für < 50 ms Latenz. Für das Live-Mikrofon trennt ein STFT-Verfahren
(2048 Samples, 75 % Überlappung) die Hüllkurve per Cepstrum von der Anregung, verschiebt beide unabhängig
und setzt sie mit korrigierten Phasen zusammen. Qualität etwas unter WORLD, dafür ~43 ms algorithmische Latenz.

### Effekte: pedalboard + eigene DSP

Spotifys `pedalboard` (C++/JUCE) liefert Kompressor, Chorus, Phaser, Delay, Reverb und Gate in Studioqualität
bei ~0,03 ms pro Block. Alles, was es dort nicht (passend) gibt, ist in NumPy/SciPy als Streaming-Effekt
implementiert: Equalizer (RBJ-Biquads, 24 dB/Okt.-Filter), Saturation, Distortion, Bitcrusher, Ringmodulator,
Roboter (STFT-Phasennullung), Kanal-Vocoder, Glitch, Echo, Tremolo, Rauschen.

### KI-Voice-Conversion: RVC über ONNX Runtime

| System | Prinzip | Einordnung |
|---|---|---|
| **RVC v2** | ein trainiertes Modell pro Zielstimme | sehr gute Qualität, riesiges Modellangebot, per ONNX ohne PyTorch lauffähig |
| Seed-VC | Zero-Shot aus 1–30 s Referenzaufnahme | flexibler, aber PyTorch-Stack (mehrere GB); guter Kandidat für eine spätere Ausbaustufe |
| So-VITS-SVC | wie RVC, älter | aufwändiger, keine Vorteile für Sprache |

RVC über ONNX hält die Installation klein (nur `onnxruntime-gpu`), nutzt die NVIDIA-Karte über CUDA und
verwendet für die Tonhöhe denselben WORLD-Schätzer wie die Stimm-Engine.

### Oberfläche und Audio-I/O

- **PySide6 (Qt 6):** natives Desktop-Fenster, gutes Dark-Theme, kein Browser/Electron nötig.
- **sounddevice (PortAudio):** WASAPI unter Windows, Callback-basiert, bringt die DLL im Wheel mit.
- **soundfile (libsndfile ≥ 1.2):** liest und schreibt WAV, FLAC, OGG und MP3 ohne ffmpeg.

### Nebenläufigkeit

Der Audio-Callback darf nie warten. Deshalb laufen Analyse, Synthese, KI und Offline-Rendern in einem
**eigenen Prozess** (`worker.py`) – Pythons GIL würde sonst bei jeder Neuberechnung die Wiedergabe stören.
Die Effektkette selbst rechnet im Callback (alle Effekte zusammen deutlich unter 1 ms pro Block, der Vocoder
~1,5 ms bei 10,7 ms Blocklänge).

## Erweitern

**Neuer Effekt:** Klasse von `Effect` (oder `PedalboardEffect`) ableiten, `id`, `label`, `params` setzen,
`process()` implementieren, in `dsp/effects/__init__.py` eintragen. Menü, Regler, Presets, Undo und Export
funktionieren automatisch.

**Neues Profil:** Eintrag in `profiles/library.py` – oder im Programm einstellen und „Als Preset speichern“.

**Neuer Stimm-Regler:** `Param` in `VOICE_PARAMS` ergänzen und in `_shape_f0` bzw. `synthesize` auswerten.

## Mögliche nächste Schritte

- KI-Umwandlung in Echtzeit (blockweise RVC-Inferenz mit Überblendung)
- Zero-Shot-Conversion (Seed-VC) als zweites KI-Backend
- Stereo-Effekte, VST3-Plugins (pedalboard kann VST3 laden)
- Virtuelles Mikrofon für Discord/Spiele (im Live-Modus unter „Audiogeräte“ z. B. VB-CABLE als Ausgabe wählen – noch ungetestet)
