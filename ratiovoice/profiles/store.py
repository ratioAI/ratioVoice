"""Favoriten und eigene Presets (als JSON im Benutzerordner)."""

from __future__ import annotations

import json
from pathlib import Path

from ..config import user_data_dir
from ..settings import clone, normalize


class ProfileStore:
    def __init__(self, path: Path | None = None):
        self._path = path or user_data_dir() / "profile.json"
        self.favorites: list[str] = []
        self.presets: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.favorites = [str(name) for name in data.get("favorites", [])]
        self.presets = {str(name): normalize(s) for name, s in data.get("presets", {}).items()}

    def _save(self) -> None:
        data = {"favorites": self.favorites, "presets": self.presets}
        self._path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def toggle_favorite(self, name: str) -> bool:
        if name in self.favorites:
            self.favorites.remove(name)
        else:
            self.favorites.append(name)
        self._save()
        return name in self.favorites

    def save_preset(self, name: str, settings: dict) -> None:
        stored = clone(settings)
        stored["profile"] = name
        self.presets[name] = stored
        self._save()

    def delete_preset(self, name: str) -> None:
        self.presets.pop(name, None)
        if name in self.favorites:
            self.favorites.remove(name)
        self._save()
