"""The tool strip's saved order, one layout per workbench.

A layout is the order the user chose, as item keys with "|" for a
separator, and the keys they removed. Items FreeCAD shows that a layout
does not mention (a command added since, a new addon) are appended
after a separator, so nothing appears or vanishes unseen. Stored as
JSON in Nxt's settings, which go when Nxt is uninstalled.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from typing import Any

import FreeCAD as App

from ..core import settings
from . import source
from .source import Entry, Kind

SETTING = "ToolStripLayouts"
SEPARATOR = "|"
#: The layout used while a sketch is edited, from any workbench: Sketcher
#: shows its own toolbars then.
SKETCH_EDIT = "Sketch edit"


#: One item of a saved order: a key, "|", or a group of the user's as
#: {"group": key, "name": text, "members": [keys]}.
Token = str | dict[str, Any]
GROUP_PREFIX = "group:"


@dataclass
class Layout:
    """One workbench's strip, as the user arranged it."""

    order: list[Token] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)


def _token(value: Any) -> Token:
    if isinstance(value, str):
        return value
    return {"group": str(value["group"]), "name": str(value.get("name", "")),
            "members": [str(k) for k in value["members"]]}


def load_all() -> dict[str, Layout]:
    """Every saved layout by workbench; none if the setting is unreadable."""
    text = str(settings.get(SETTING) or "")
    if not text:
        return {}
    try:
        stored = json.loads(text)
        return {name: Layout([_token(t) for t in value["order"]],
                             list(value["removed"]))
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


def arrange(live: list[Entry], layout: Layout | None,
            resolve: Callable[[str], Entry | None] = lambda _key: None
            ) -> tuple[list[Entry], list[str]]:
    """The live entries in the layout's order, unmentioned ones after.

    A key FreeCAD shows on no toolbar (a command added from the drawer)
    is looked up with `resolve`; one it cannot find (its workbench not
    loaded yet) is left out and returned, so a save keeps its place.
    """
    if layout is None:
        return live, []
    missing: list[str] = []
    waiting = {e.key: e for e in live if e.kind is not Kind.SEPARATOR}

    def find(key: str) -> Entry | None:
        return waiting.pop(key) if key in waiting else resolve(key)

    arranged: list[Entry] = []
    for key in layout.order:
        if isinstance(key, dict):
            arranged.append(group_of(key, find))
        elif key == SEPARATOR:
            arranged.append(source.SEPARATOR)
        elif key in waiting:
            arranged.append(waiting.pop(key))
        elif (found := resolve(key)) is not None:
            arranged.append(found)
        else:
            missing.append(key)
    removed = set(layout.removed)
    new = [e for e in live if e.key in waiting and e.key not in removed]
    if new:
        arranged += [source.SEPARATOR, *new]
    return source.tidy(arranged), missing


def capture(shown: list[Entry], live: list[Entry],
            previous: Layout | None, missing: Iterable[str] = ()) -> Layout:
    """The layout of `shown`: what is left out of `live` counts removed.

    `missing` keys (not shown only because they cannot be found now) go
    back after the key that came before them in `previous`.
    """
    order = [_saved(e) for e in shown]
    if previous is not None:
        order = _with_missing(order, previous.order, set(missing))
    kept = {k for t in order for k in _keys_of(t)}
    live_keys = {e.key for e in live if e.kind is not Kind.SEPARATOR}
    earlier = [] if previous is None else [
        k for k in previous.removed if k not in live_keys]
    removed = earlier + sorted(live_keys - kept)
    return Layout(order, removed)


def group_of(token: dict[str, Any],
             find: Callable[[str], Entry | None]) -> Entry:
    """A user's group from its saved token, with the members found."""
    members = tuple(m for m in map(find, token["members"]) if m is not None)
    return Entry(Kind.GROUP, key=token["group"], members=members,
                 group=source.GroupState(token["name"],
                                         list(token["members"])))


def _saved(entry: Entry) -> Token:
    if entry.kind is Kind.SEPARATOR:
        return SEPARATOR
    state = entry.group
    if entry.kind is Kind.GROUP and state is not None and state.editable:
        return {"group": entry.key, "name": state.name,
                "members": list(state.keys)}
    return entry.key


def _keys_of(token: Token) -> list[str]:
    return list(token["members"]) if isinstance(token, dict) else [token]


def with_missing(order: list[Token], previous: list[Token],
                 missing: set[str]) -> list[Token]:
    """`order` with each `missing` key back after its predecessor."""
    return _with_missing(order, previous, missing)


def _with_missing(order: list[Token], previous: list[Token],
                  missing: set[str]) -> list[Token]:
    restored = list(order)
    for place, key in enumerate(previous):
        if not isinstance(key, str) or key not in missing or key in restored:
            continue
        anchor = next((k for k in reversed(previous[:place])
                       if isinstance(k, str) and k != SEPARATOR
                       and k in restored), None)
        restored.insert(0 if anchor is None
                        else restored.index(anchor) + 1, key)
    return restored


def export_text() -> str:
    """Every layout, as the JSON an import reads back."""
    return json.dumps({name: asdict(layout)
                       for name, layout in load_all().items()}, indent=1)


def import_text(text: str) -> int:
    """Take the layouts in `text`, replacing those of the same workbench.

    Returns how many; raises ValueError if `text` is not a layout export.
    """
    try:
        given = {name: Layout([_token(k) for k in value["order"]],
                              [str(k) for k in value["removed"]])
                 for name, value in json.loads(text).items()}
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("not a tool strip layout export") from exc
    for name, layout in given.items():
        save(name, layout)
    return len(given)
