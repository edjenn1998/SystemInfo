"""Text/console renderer for SystemSnapshot (stdlib-only).

Kept plain (no third-party deps) so it renders anywhere; a GUI renderer
would consume the same SystemSnapshot.
"""

from __future__ import annotations

import os

from ..core import CategoryResult, SystemSnapshot


def _term_width(default: int = 88) -> int:
    try:
        return min(100, max(48, os.get_terminal_size().columns - 4))
    except (OSError, ValueError):
        return default


class ConsoleRenderer:
    def __init__(self, color: bool = True, width: int | None = None):
        self.color = color and os.isatty(1)
        self.width = width or _term_width()

    # -- color helpers -----------------------------------------------------
    def _c(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.color else text

    def _title_bar(self, title: str) -> str:
        label = f" {title} "
        line = self._c("1;36", "═" * max(0, self.width - len(label)) + label)
        return line

    def render(self, snapshot: SystemSnapshot) -> str:
        parts = []
        for i, cat in enumerate(snapshot.categories):
            parts.append(self._render_category(cat, first=(i == 0)))
        return "\n".join(p for p in parts if p)

    def _render_category(self, cat: CategoryResult, first: bool = False) -> str:
        out: list[str] = []
        if not first:
            out.append("")
        out.append(self._c("1;36", f"── {cat.title} ".ljust(self.width, "─")))

        if not cat.available:
            out.append(self._c("33", f"  (no data{' — ' + cat.note if cat.note else ''})"))
            return "\n".join(out)

        if cat.note:
            out.append(self._c("33", f"  note: {cat.note}"))

        for f in cat.fields:
            label = self._c("32", f"{f.label}:".ljust(26))
            out.append(f"  {label} {self._c('37', f.display())}")

        if cat.records:
            out.append(self._c("35", "  records:"))
            for rec in cat.records:
                out.append(self._render_record(rec, 2))
        return "\n".join(out)

    def _render_record(self, rec: dict, depth: int) -> str:
        kind = rec.get("kind", "record")
        indent = "   " + "  " * depth
        colored_kind = self._c("1;35", f"[{kind}]")
        pairs = []
        for k, v in rec.items():
            if k == "kind":
                continue
            if v is None or v == "" or v == []:
                continue
            pairs.append(self._c("36", f"{k}=") + self._c("37", self._fmt(v)))
        return f"{indent}{colored_kind} " + self._c("37", "  ".join(pairs))

    def _fmt(self, value) -> str:
        if isinstance(value, bool):
            return "yes" if value else "no"
        if isinstance(value, (list, tuple)):
            return ", ".join(self._fmt(v) for v in value)
        return str(value)
