"""Undo/Redo als Liste von Zustands-Schnappschüssen."""

from __future__ import annotations

_LIMIT = 200


class History:
    """Jeder Zustand ist ein Dict ``{"clip": ndarray, "name": str, "settings": dict}``."""

    def __init__(self):
        self._states: list[dict] = []
        self._index = -1

    def reset(self, state: dict) -> None:
        self._states, self._index = [state], 0

    def push(self, state: dict) -> None:
        if self._index >= 0 and self._same(state, self._states[self._index]):
            return
        del self._states[self._index + 1 :]
        self._states.append(state)
        del self._states[:-_LIMIT]
        self._index = len(self._states) - 1

    @staticmethod
    def _same(a: dict, b: dict) -> bool:
        return a["clip"] is b["clip"] and a["settings"] == b["settings"]

    @property
    def can_undo(self) -> bool:
        return self._index > 0

    @property
    def can_redo(self) -> bool:
        return self._index < len(self._states) - 1

    def undo(self) -> dict | None:
        if not self.can_undo:
            return None
        self._index -= 1
        return self._states[self._index]

    def redo(self) -> dict | None:
        if not self.can_redo:
            return None
        self._index += 1
        return self._states[self._index]
