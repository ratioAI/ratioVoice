"""Beschreibung einstellbarer Parameter.

Jeder Effekt und die Stimm-Engine deklarieren ihre Regler als ``Param``.
Die Oberfläche erzeugt daraus automatisch Slider bzw. Auswahlfelder, sodass
neue Effekte ohne UI-Code ergänzt werden können.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Param:
    key: str
    label: str
    lo: float = 0.0
    hi: float = 1.0
    default: float = 0.0
    unit: str = ""
    step: float = 0.01
    log: bool = False  # logarithmischer Regler (Frequenzen)
    choices: tuple[str, ...] = ()  # gesetzt => Auswahlfeld, Wert = Index

    @property
    def is_choice(self) -> bool:
        return bool(self.choices)

    def clamp(self, value: float) -> float:
        if self.is_choice:
            return float(min(max(int(round(value)), 0), len(self.choices) - 1))
        return float(min(max(value, self.lo), self.hi))

    def format(self, value: float) -> str:
        if self.is_choice:
            return self.choices[int(round(value))]
        decimals = 0 if self.step >= 1 else 1 if self.step >= 0.1 else 2
        text = f"{value:.{decimals}f}"
        return f"{text} {self.unit}".strip()


def defaults(params: Iterable[Param]) -> dict[str, float]:
    return {p.key: p.default for p in params}


def sanitize(params: Iterable[Param], values: dict | None) -> dict[str, float]:
    """Füllt fehlende Werte mit Defaults und begrenzt auf den gültigen Bereich."""
    values = values or {}
    return {p.key: p.clamp(values.get(p.key, p.default)) for p in params}
