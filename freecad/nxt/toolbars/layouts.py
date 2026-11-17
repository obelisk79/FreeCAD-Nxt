"""The tool strips' saved arrangement, one layout per workbench.

A layout is, for each area (top, left, right), the order the user chose
as item keys, "|" for a separator and a newline (ROW) between rows; and
the keys they removed. Items FreeCAD shows that a layout does not
mention (a command added since, a new addon) are appended after a
separator, so nothing appears or vanishes unseen. Stored as JSON in
Nxt's settings, which go when Nxt is uninstalled. What is locked (the
top strip's first row, a side strip) is the same in every workbench:
kept in the SHARED layout.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from typing import Any

import FreeCAD as App

from ..core import settings
from . import source, state
from .source import Areas, Entry, Kind

SETTING = "ToolStripLayouts"
SEPARATOR = "|"
ROW = "\n"
#: The layout used while a sketch is edited, from any workbench: Sketcher
#: shows its own toolbars then.
SKETCH_EDIT = "Sketch edit"
#: The layout locked strips share across workbenches.
SHARED = "*"
#: The top strip's first row, locked on its own.
FIRST_ROW = "first-row"
#: What can be locked: the top strip's first row and the side strips.
LOCKABLE = (FIRST_ROW, state.LEFT, state.RIGHT)


#: One item of a saved order: a key, "|", or a group of the user's as
#: {"group": key, "name": text, "members": [keys]}.
Token = str | dict[str, Any]
GROUP_PREFIX = "group:"


@dataclass
class Layout:
    """One workbench's strips, as the user arranged them."""

    areas: dict[str, list[Token]] = field(default_factory=dict)
    removed: list[str] = field(default_factory=list)

    @classmethod
    def top(cls, order: list[Token], removed: Iterable[str] = ()) -> Layout:
        """A layout with only a top strip."""
        return cls({state.TOP: list(order)}, list(removed))


def _layout(value: dict[str, Any]) -> Layout:
    # Before rows and areas: one "order", the top strip.
    areas = value["areas"] if "areas" in value \
        else {state.TOP: value["order"]}
    return Layout({str(area): [_token(t) for t in tokens]
                   for area, tokens in areas.items()},
                  [str(k) for k in value["removed"]])


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
        return {name: _layout(value)
                for name, value in json.loads(text).items()}
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


Units = dict[str, list[Token]]


def _units(areas: Units) -> Units:
    # The areas with the top strip's first row apart, as FIRST_ROW.
    units = dict(areas)
    top = units.pop(state.TOP, [])
    cut = top.index(ROW) if ROW in top else len(top)
    units[FIRST_ROW], units[state.TOP] = top[:cut], top[cut + 1:]
    return units


def _areas(units: Units) -> Units:
    # The first row back at the top strip's start; kept apart by a ROW
    # even when empty, so a workbench's own rows never become it.
    areas = {a: t for a, t in units.items() if a != FIRST_ROW}
    first, rest = units.get(FIRST_ROW, []), areas.get(state.TOP, [])
    areas[state.TOP] = [*first, ROW, *rest] if rest else list(first)
    return areas


def load_for(workbench: str, locked: Iterable[str]) -> Layout | None:
    """`workbench`'s layout, what is locked taken from the shared one."""
    own, shared = load(workbench), load(SHARED)
    locked = set(locked)
    if shared is None or not locked:
        return own
    units = _units(own.areas) if own is not None else {}
    units.update({u: t for u, t in _units(shared.areas).items()
                  if u in locked})
    removed = (own.removed if own is not None else []) + shared.removed
    return Layout(_areas(units), removed)


def save_for(workbench: str, layout: Layout, locked: Iterable[str],
             live: Areas) -> None:
    """Store `layout`, what is locked as the shared layout.

    What was removed from something locked is shared too; the rest is
    `workbench`'s own.
    """
    locked = set(locked)
    live_units = dict(live)
    live_units[FIRST_ROW] = source.rows_of(live.get(state.TOP, []))[0]
    of_locked = {e.key for unit in locked for e in live_units.get(unit, [])}
    units = _units(layout.areas)
    save(SHARED, Layout(
        _areas({u: t for u, t in units.items() if u in locked}),
        [k for k in layout.removed if k in of_locked]) if locked else None)
    save(workbench, Layout(
        _areas({u: t for u, t in units.items() if u not in locked}),
        [k for k in layout.removed if k not in of_locked]))


def arrange(live: Areas, layout: Layout | None,
            resolve: Callable[[str], Entry | None] = lambda _key: None,
            locked: Iterable[str] = ()) -> tuple[Areas, list[str]]:
    """The live entries in the layout's arrangement, unmentioned ones after.

    A key FreeCAD shows on no toolbar (a command added from the drawer)
    is looked up with `resolve`; one it cannot find (its workbench not
    loaded yet) is left out and returned, so a save keeps its place.
    Items the layout does not mention end the last row of the area
    FreeCAD shows them in; a locked strip stays as it is, so its new
    items go to the first unlocked strip, or are not shown. A locked
    first row stays as it is too: new top items start a row after it.
    """
    locked = set(locked)
    open_area = next((a for a in state.AREAS if a not in locked), None)
    if layout is None:
        return live, []
    missing: list[str] = []
    waiting = {e.key: e for entries in live.values() for e in entries
               if e.kind not in (Kind.SEPARATOR, Kind.BREAK)}

    def find(key: str) -> Entry | None:
        return waiting.pop(key) if key in waiting else resolve(key)

    arranged: Areas = {}
    for area in state.AREAS:
        shown: list[Entry] = []
        for key in layout.areas.get(area, []):
            if isinstance(key, dict):
                shown.append(group_of(key, find))
            elif key in _DIVIDERS:
                shown.append(_DIVIDERS[key])
            elif (found := find(key)) is not None:
                shown.append(found)
            else:
                missing.append(key)
        arranged[area] = shown
    removed = set(layout.removed)
    for area in state.AREAS:
        new = [e for e in live.get(area, [])
               if e.key in waiting and e.key not in removed]
        target = open_area if area in locked else area
        if new and target is not None:
            arranged[target] += [_lead(arranged[target], target, locked),
                                 *new]
    for area in state.AREAS:
        arranged[area] = source.tidy(arranged[area])
    return arranged, missing


def _lead(entries: list[Entry], area: str, locked: set[str]) -> Entry:
    # What goes before new items: a row of their own after a lone
    # locked first row, otherwise a separator.
    alone = all(e.kind is not Kind.BREAK for e in entries)
    if area == state.TOP and FIRST_ROW in locked and alone:
        return source.BREAK
    return source.SEPARATOR


def capture(shown: Areas, live: Areas, previous: Layout | None,
            missing: Iterable[str] = ()) -> Layout:
    """The layout of `shown`: what is left out of `live` counts removed.

    `missing` keys (not shown only because they cannot be found now) go
    back after the key that came before them in `previous`.
    """
    areas: dict[str, list[Token]] = {}
    for area, entries in shown.items():
        order = [_saved(e) for e in entries]
        if previous is not None:
            order = _with_missing(order, previous.areas.get(area, []),
                                  set(missing))
        areas[area] = order
    kept = {k for order in areas.values() for t in order for k in _keys_of(t)}
    live_keys = {e.key for entries in live.values() for e in entries
                 if e.kind not in (Kind.SEPARATOR, Kind.BREAK)}
    earlier = [] if previous is None else [
        k for k in previous.removed if k not in live_keys]
    removed = earlier + sorted(live_keys - kept)
    return Layout(areas, removed)


def group_of(token: dict[str, Any],
             find: Callable[[str], Entry | None]) -> Entry:
    """A user's group from its saved token, with the members found."""
    members = tuple(m for m in map(find, token["members"]) if m is not None)
    return Entry(Kind.GROUP, key=token["group"], members=members,
                 group=source.GroupState(token["name"],
                                         list(token["members"])))


_DIVIDERS = {SEPARATOR: source.SEPARATOR, ROW: source.BREAK}


def _saved(entry: Entry) -> Token:
    if entry.kind is Kind.SEPARATOR:
        return SEPARATOR
    if entry.kind is Kind.BREAK:
        return ROW
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
                       if isinstance(k, str) and k not in _DIVIDERS
                       and k in restored), None)
        restored.insert(0 if anchor is None
                        else restored.index(anchor) + 1, key)
    return restored
