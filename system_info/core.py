"""Core data models shared by all collectors and any future UI.

Kept UI-agnostic on purpose: collectors return these structures, and a
renderer (Console today, GUI later) only consumes them. Nothing here prints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from datetime import datetime


def _clean(value: Any) -> Any:
    """Recursively convert values into JSON-friendly primitives."""
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_clean(v) for v in value]
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    return str(value)


@dataclass(slots=True)
class Field:
    """A single labelled value, e.g. name='Cores' value=32 unit='logical'."""

    label: str
    value: Any
    unit: str | None = None
    advanced: bool = False

    def display(self) -> str:
        if self.value is None:
            return "unavailable"
        base = str(self.value)
        if self.unit:
            base += f" {self.unit}"
        return base

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"label": self.label, "value": _clean(self.value)}
        if self.unit:
            data["unit"] = self.unit
        if self.advanced:
            data["advanced"] = True
        return data


@dataclass(slots=True)
class CategoryResult:
    """One category of info: scalar fields + optional lists of records.

    `records` holds structured sub-items (e.g. one dict per storage device or
    per NIC that don't fit a single label/value pair).
    """

    name: str
    title: str
    fields: list[Field] = field(default_factory=list)
    records: list[dict[str, Any]] = field(default_factory=list)
    note: str | None = None

    def add(self, label: str, value: Any, unit: str | None = None, advanced: bool = False) -> "CategoryResult":
        if isinstance(value, list):
            self.fields.append(Field(label=label, value=", ".join(str(v) for v in value) if value else None, unit=unit, advanced=advanced))
        else:
            self.fields.append(Field(label=label, value=value, unit=unit, advanced=advanced))
        return self

    def add_record(self, record: dict[str, Any]) -> "CategoryResult":
        self.records.append(_clean(record))
        return self

    @property
    def available(self) -> bool:
        return any(f.value is not None for f in self.fields) or bool(self.records)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "note": self.note,
            "fields": [f.to_dict() for f in self.fields],
            "records": self.records,
        }


@dataclass(slots=True)
class SystemSnapshot:
    """The whole collected result across every category."""

    categories: list[CategoryResult] = field(default_factory=list)
    captured_at: str = field(default_factory=lambda: datetime.now().astimezone().isoformat(timespec="seconds"))

    def add(self, result: CategoryResult | None) -> None:
        if result is not None:
            self.categories.append(result)

    def get(self, name: str) -> CategoryResult | None:
        for cat in self.categories:
            if cat.name == name:
                return cat
        return None

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": "1.2", "collected_at": self.captured_at, "categories": [c.to_dict() for c in self.categories]}
