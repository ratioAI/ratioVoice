# RatioVoice

Lokales Studio für Stimmenverzerrung: eine Aufnahme machen, Stimme auswählen, anhören, anpassen, exportieren.
Alles läuft auf dem eigenen Rechner – ohne Cloud.

## Starten (Windows)

1. Den „Python Install Manager“ von <https://www.python.org/downloads/> installieren (falls noch kein Python 3.11–3.13 vorhanden ist).
2. `start.bat` doppelklicken. Das Skript sucht Python 3.13/3.12/3.11, installiert bei Bedarf 3.13 über den
   Install Manager, richtet die Bibliotheken in `.venv` ein und startet das Programm.

Python 3.14 und neuer funktionieren noch nicht, weil es die Bibliothek `pyworld` dafür nicht als fertiges
Windows-Paket gibt. Mehrere Python-Versionen nebeneinander sind kein Problem.

Optional:

- `build_exe.bat` baut `dist\RatioVoice\RatioVoice.exe`, die ohne installiertes Python läuft.
- `ki_installieren.bat` installiert ONNX Runtime (CUDA) für die KI-Stimmen.

Manuell: `pip install -r requirements.txt`, dann `python RatioVoice.py`.

## Bedienung

| Bereich | Funktion |
|---|---|
| Links | Stimmenbibliothek (29 Profile in 3 Kategorien), Favoriten, eigene Profile. Klick = anwenden, Rechtsklick = Favorit/Löschen. |
| Mitte | Wellenform von Original und bearbeiteter Stimme. Klick = springen, Ziehen = Bereich auswählen (Schleife, Zuschneiden, Teil-Export). |
| Rechts | Stimm-Regler, KI-Stimme, Effektkette (hinzufügen, ein/aus, umsortieren, entfernen), „Als Preset speichern“. |
| Unten | Aufnahme, Play/Pause, Stopp, Schleife, Undo/Redo, Zuschneiden, Import, Export, Audiogeräte. |

Tasten: Leertaste = Play/Pause, `R` = Aufnahme, `A` = Original ⇄ Bearbeitet, `Strg+Z` / `Strg+Y`, `Strg+O`, `Strg+E`.
Doppelklick auf einen Regler setzt ihn zurück.

- **Import:** WAV, MP3, OGG, FLAC (auch per Drag & Drop). **Export:** WAV, MP3, OGG.
- **Original bleibt erhalten:** Jede Mikrofonaufnahme wird unverändert unter
  `%APPDATA%\RatioVoice\Aufnahmen` gespeichert; die bearbeitete Fassung entsteht erst beim Export als eigene Datei.
- **Echtzeit:** Effekte, A/B-Vergleich und Regler wirken während der Wiedergabe. Änderungen an den
  Stimm-Reglern (Tonhöhe, Formant …) werden im Hintergrund neu berechnet und nahtlos eingeblendet.
- **Live-Mikrofon:** Tonhöhe, Formant, Flüstern und alle Effekte in Echtzeit (ca. 45–60 ms Verzögerung,
  Kopfhörer verwenden). Sprachmelodie, Rauheit, Zittern, Schwanken und Pitch Correction brauchen die ganze
  Aufnahme und wirken deshalb nur auf Aufnahmen/Dateien.

## Die Stimm-Regler

| Regler | Wirkung |
|---|---|
| Tonhöhe | Grundfrequenz in Halbtönen – ohne Tempo oder Klangfarbe zu ändern |
| Formant | Klangfarbe / gefühlte Körpergröße – unabhängig von der Tonhöhe |
| Tempo | Time-Stretching ohne Tonhöhenänderung |
| Sprachmelodie | 0 = monoton, 1 = original, 2 = übertrieben lebhaft |
| Hauch / Flüstern | Rauschanteil; bei 1,0 echtes Flüstern ohne Stimmbänder |
| Rauheit | Unregelmäßige Stimmbandschwingung, Knarren |
| Zittern / Schwanken | Schnelles Tremolo der Tonhöhe bzw. langsames Driften |
| Pitch Correction | Autotune auf eine Tonleiter; Korrektur-Tempo 1,0 = harter Effekt |

Faustregel für natürliche Ergebnisse: Formant etwa halb so weit verschieben wie die Tonhöhe
(z. B. Tonhöhe −6, Formant −3). Die Profile gehen von einer durchschnittlichen Männerstimme aus.

## KI-Stimmen (Voice Conversion)

Für wirklich „andere Menschen“ ersetzt das KI-Modul die Klangfarbe durch ein trainiertes Stimmmodell
(RVC v2 im ONNX-Format). Regler und Effekte wirken anschließend auf das Ergebnis.

1. `ki_installieren.bat` ausführen.
2. Im Programm unter „KI-Stimme“ auf „Modellordner öffnen“ klicken und dort ablegen:
   - `vec-768-layer-12.onnx` (ContentVec-Encoder, einmalig)
   - beliebige RVC-v2-Stimmmodelle als `.onnx` (aus der RVC-WebUI über „Export Onnx“)
3. Stimme im Auswahlfeld wählen; mit der Transponierung an die Zielstimme anpassen (z. B. +12 Mann → Frau).

Nur Stimmen verwenden, für die eine Erlaubnis vorliegt (eigene Stimme, frei lizenzierte Modelle).

**Stand der Prüfung:** Die Datenwege des KI-Moduls sind mit Platzhalter-Modellen getestet
(`tests/test_ai_plumbing.py`), aber noch nicht mit echten Stimmmodellen und nicht auf einer GPU.
Die KI-Umwandlung arbeitet auf Aufnahmen, nicht im Live-Mikrofonbetrieb.

## Tests

```
pip install -r requirements-dev.txt
python -m pytest tests
python tests/test_engine.py demos     # rendert zusätzlich alle 29 Profile nach .\demos
```

Geprüft wird an echten Sprachaufnahmen (`tests/data`, LibriSpeech, gemeinfrei) unter anderem, dass
Tonhöhe und Formant messbar unabhängig sind und dass sich alle Profile klanglich unterscheiden.

## Grenzen dieser Version

- Entwickelt und getestet unter Linux ohne Soundkarte: Signalverarbeitung, Oberfläche, Export und
  Wiedergabelogik sind dort geprüft; Mikrofon/Lautsprecher (PortAudio) und `build_exe.bat` sind unter
  Windows noch nicht gelaufen.
- Die Profile sind nach Messwerten abgestimmt, nicht nach Gehör – Feintuning am eigenen Mikrofon lohnt sich.
- Aufnahmen bis 10 Minuten; intern mono, 48 kHz.

## Lizenzen der Bibliotheken

pedalboard (GPLv3), PySide6 (LGPL), pyworld/WORLD (MIT/BSD), sounddevice, soundfile, NumPy, SciPy (BSD/MIT).
Für die private Nutzung unproblematisch; bei einer Weitergabe des Programms gilt wegen pedalboard die GPLv3.

Technischer Aufbau und Begründung der Technologie-Wahl: [docs/ARCHITEKTUR.md](docs/ARCHITEKTUR.md)
