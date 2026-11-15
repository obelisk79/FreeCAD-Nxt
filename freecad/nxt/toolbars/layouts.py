"""The tool strip's saved order, one layout per workbench.

A layout is the order the user chose, as item keys with "|" for a
separator, and the keys they removed. Items FreeCAD shows that a layout
does not mention (a command added since, a new addon) are appended
after a separator, so nothing appears or vanishes unseen. Stored as
JSON in Nxt's settings, which go when Nxt is uninstalled.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

import FreeCAD as App

from ..core import settings
from . import source
from .source import Entry, Kind

SETTING = "ToolStripLayouts"
SEPARATOR = "|"


@dataclass
class Layout:
    """One workbench's strip, as the user arranged it."""

    order: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)


def load_all() -> dict[str, Layout]:
    """Every saved layout by workbench; none if the setting is unreadable."""
    text = str(settings.get(SETTING) or "")
    if not text:
        return {}
    try:
        stored = json.loads(text)
        return {name: Layout(list(value["order"]), list(value["removed"]))
                for name, value in stored.items()}
    except (ValueError, KeyError, TypeError, AttributeError):
        App.Console.PrintWarning("Nxt: tool strip layouts unreadable; "
                                 "using FreeCAD's toolbars\n")
        return {}


def load(workbench: str) -> Layout | None:
    return load_all().get(workbench)


def save(workbench: str, layout: Layout | None) -> None:
    """Store `workbench`'s layout; None forgets it (back to FreeCAD's)."""
    layouts = load_all()
    if layout is None:
        layouts.pop(workbench, None)
    else:
        layouts[workbench] = layout
    settings.put(SETTING, json.dumps(
        {name: asdict(value) for name, value in layouts.items()})
        if layouts else "")


def arrange(live: list[Entry], layout: Layout | None) -> list[Entry]:
    """The live entries in the layout's order, unmentioned ones after."""
    if layout is None:
        return live
    waiting = {e.key: e for e in live if e.kind is not Kind.SEPARATOR}
    arranged: list[Entry] = []
    for key in layout.order:
        if key == SEPARATOR:
            arranged.append(source.SEPARATOR)
        elif key in waiting:
            arranged.append(waiting.pop(key))
    removed = set(layout.removed)
    new = [e for e in live if e.key in waiting and e.key not in removed]
    if new:
        arranged += [source.SEPARATOR, *new]
    return source.tidy(arranged)


def capture(shown: list[Entry], live: list[Entry],
            previous: Layout | None) -> Layout:
    """The layout of `shown`: what is left out of `live` counts removed."""
    order = [SEPARATOR if e.kind is Kind.SEPARATOR else e.key
             for e in shown]
    kept = set(order)
    live_keys = {e.key for e in live if e.kind is not Kind.SEPARATOR}
    earlier = [] if previous is None else [
        k for k in previous.removed if k not in live_keys]
    removed = earlier + sorted(live_keys - kept)
    return Layout(order, removed)
