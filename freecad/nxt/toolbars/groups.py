"""Groups on the tool strip: several commands behind one button.

The button runs, and shows, the member last used; its arrow lists them
all. Groups are the user's (made in edit mode, saved in the layout) or
FreeCAD's own group commands added from the drawer, which FreeCAD
defines and which are not edited here. Entries are immutable: each
change gives a new group entry sharing the same state.
"""

from __future__ import annotations

import dataclasses
import uuid

from . import catalog, layouts
from .source import Entry, GroupState, Kind


def freecad_group(key: str) -> Entry | None:
    """FreeCAD's group command `key` as a group; None if not one."""
    actions = catalog.group_actions(key)
    if not actions:
        return None
    members = tuple(Entry(Kind.COMMAND, a, None, a.objectName())
                    for a in actions)
    return Entry(Kind.GROUP, key=key, members=members,
                 group=GroupState(catalog.menu_text(key),
                                  [m.key for m in members], editable=False))


def new(name: str) -> Entry:
    """An empty group of the user's, to drop commands into."""
    key = "%s%s" % (layouts.GROUP_PREFIX, uuid.uuid4().hex[:8])
    return Entry(Kind.GROUP, key=key, members=(), group=GroupState(name, []))


def editable(entry: Entry | None) -> bool:
    return (entry is not None and entry.kind is Kind.GROUP
            and entry.group is not None and entry.group.editable)


def _changed(entry: Entry, members: tuple[Entry, ...]) -> Entry:
    state = entry.group or GroupState("", [])
    found = [m.key for m in members]
    missing = set(state.keys) - {m.key for m in entry.members}
    state.keys = [str(k) for k in layouts.with_missing(
        list(found), list(state.keys), missing)]
    state.last = min(state.last, max(0, len(members) - 1))
    return dataclasses.replace(entry, members=members)


def added(entry: Entry, member: Entry) -> Entry:
    return _changed(entry, (*entry.members, member))


def reordered(entry: Entry, keys: list[str]) -> Entry:
    """The group with its members in the order of `keys`; others after."""
    rank = {key: place for place, key in enumerate(keys)}
    members = sorted(entry.members, key=lambda m: rank.get(m.key, len(rank)))
    return _changed(entry, tuple(members))


def without(entry: Entry, index: int) -> Entry:
    members = list(entry.members)
    del members[index]
    return _changed(entry, tuple(members))


def lone_member(entry: Entry) -> Entry | None:
    """The member a group of one stands for; None while it holds more.

    Not while a member is missing (its workbench not loaded): the group
    still holds it.
    """
    state = entry.group
    if state is None or len(entry.members) != 1 or len(state.keys) != 1:
        return None
    return entry.members[0]


def is_empty(entry: Entry) -> bool:
    return (editable(entry) and not entry.members
            and entry.group is not None and not entry.group.keys)


def use(entry: Entry, member: Entry) -> bool:
    """Make `member` the one the button runs; whether it changed."""
    state = entry.group
    for index, shown in enumerate(entry.members):
        if shown is member or shown.action is member.action:
            if state is not None and state.last != index:
                state.last = index
                return True
            return False
    return False
