"""Every command FreeCAD has, for the tool strip's drawer.

Membership comes from each workbench's declared toolbars; "Global" is
what every such workbench shows. Commands that are on no toolbar yet
(Sketcher's, outside a sketch) have no QAction: they get a stand-in that
runs the command by name, drawn from the command's pixmap.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from ..core.qt import QtCore, QtGui
from .models import plain

ALL = "all"
GLOBAL = "global"

#: Fuzzy-match points: a letter found, one right after the last, one
#: starting a word, and a hit in the first letter.
HIT, RUN, WORD_START, FIRST = 1, 4, 6, 8


@dataclass(frozen=True)
class Command:
    """One command as the drawer lists it."""

    key: str
    text: str
    tip: str
    pixmap: str
    groups: frozenset[str]


def score(query: str, text: str) -> int | None:
    """How well `query`'s letters appear in order in `text`; None if not.

    "pdpad" finds "PartDesign_Pad"; matches at word starts and in runs
    score higher.
    """
    query, text = query.lower().replace(" ", ""), text.lower()
    if not query:
        return 0
    total, at, last = 0, 0, -2
    for letter in query:
        found = text.find(letter, at)
        if found < 0:
            return None
        total += HIT
        if found == last + 1:
            total += RUN
        if found == 0:
            total += FIRST
        elif not text[found - 1].isalnum():
            total += WORD_START
        last, at = found, found + 1
    return total


def _searchable(command: Command) -> str:
    # Word starts in CamelCase command names count as words.
    spaced = "".join(" " + c if c.isupper() else c for c in command.key)
    return "%s %s" % (command.text, spaced.replace("_", " "))


def search(commands: Iterable[Command], query: str,
           group: str) -> list[Command]:
    """The commands in `group` matching `query`, best first."""
    chosen = [c for c in commands if group == ALL or group in c.groups]
    if not query.strip():
        return sorted(chosen, key=lambda c: c.text.lower())
    scored = [(s, c) for c in chosen
              if (s := score(query, _searchable(c))) is not None]
    scored.sort(key=lambda pair: (-pair[0], pair[1].text.lower()))
    return [c for _s, c in scored]


def _toolbar_items(workbench: Any) -> dict[str, list[str]]:
    try:
        return dict(workbench.getToolbarItems())
    except Exception:  # noqa: BLE001 - a workbench not set up yet
        return {}


def _info(command: Any) -> dict[str, Any] | None:
    try:
        return dict(command.getInfo())
    except Exception:  # noqa: BLE001 - a command without info
        return None


def _membership() -> tuple[dict[str, set[str]], list[tuple[str, str]]]:
    """Command -> workbenches showing it, and (name, label) of each."""
    members: dict[str, set[str]] = {}
    groups: list[tuple[str, str]] = []
    for name, workbench in Gui.listWorkbenches().items():
        items = _toolbar_items(workbench)
        if not items:
            continue
        groups.append((name, str(getattr(workbench, "MenuText", name))))
        for commands in items.values():
            for command in commands:
                members.setdefault(command, set()).add(name)
    return members, groups


def read() -> tuple[list[Command], list[tuple[str, str]]]:
    """Every command, and the drawer's filters as (id, label)."""
    members, groups = _membership()
    everywhere = {name for name, _label in groups}
    commands: list[Command] = []
    for key in Gui.listCommands():  # type: ignore[attr-defined]  # stubs
        command = Gui.Command.get(key)
        info = None if command is None else _info(command)
        if info is None:
            continue
        shown_in = members.get(key, set())
        group_ids = set(shown_in)
        if everywhere and shown_in >= everywhere:
            group_ids.add(GLOBAL)
        commands.append(Command(
            key, plain(str(info.get("menuText") or key)),
            str(info.get("toolTip") or ""), str(info.get("pixmap") or ""),
            frozenset(group_ids)))
    groups.sort(key=lambda group: group[1].lower())
    return commands, [(ALL, "All"), (GLOBAL, "Global"), *groups]


def live_action(key: str) -> Any:
    """The command's own QAction, if FreeCAD has made one."""
    command = Gui.Command.get(key)
    actions = command.getAction() if command is not None else None
    if isinstance(actions, (list, tuple)):
        return actions[0] if actions else None
    return actions


def group_actions(key: str) -> list[Any]:
    """The member actions of a FreeCAD group command; none if not a group.

    A group's getAction() lists its members, each named for its own
    command; a plain command's lists itself.
    """
    command = Gui.Command.get(key)
    actions = command.getAction() if command is not None else None
    if not isinstance(actions, (list, tuple)):
        return []
    members = [a for a in actions if a.objectName() != key]
    return members if members and len(members) == len(actions) else []


def menu_text(key: str) -> str:
    command = Gui.Command.get(key)
    info = _info(command) if command is not None else None
    return plain(str((info or {}).get("menuText") or key))


def icon(key: str, pixmap: str) -> QtGui.QIcon:
    """The command's icon: its action's, else looked up by pixmap name."""
    action = live_action(key)
    if action is not None and not action.icon().isNull():
        return action.icon()
    finder = getattr(Gui, "getIcon", None)
    if finder is not None and pixmap:
        with_icon = finder(pixmap)
        if isinstance(with_icon, QtGui.QIcon) and not with_icon.isNull():
            return with_icon
    for path in (":/icons/%s.svg" % pixmap, pixmap):
        if pixmap and QtCore.QFile.exists(path):
            return QtGui.QIcon(path)
    return QtGui.QIcon()


class StandIns(QtCore.QObject):
    """QActions for commands FreeCAD has not made one for yet."""

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._made: dict[str, QtGui.QAction] = {}

    def action(self, key: str) -> Any:
        """The command's live action, else a stand-in; None if no command."""
        live = live_action(key)
        if live is not None:
            return live
        if key in self._made:
            return self._made[key]
        command = Gui.Command.get(key)
        if command is None:
            return None
        info = command.getInfo()
        stand_in = QtGui.QAction(
            icon(key, str(info.get("pixmap") or "")),
            plain(str(info.get("menuText") or key)), self)
        stand_in.setObjectName(key)
        stand_in.setToolTip(str(info.get("toolTip") or ""))
        stand_in.triggered.connect(_runner(key))
        self._made[key] = stand_in
        return stand_in


def _runner(key: str) -> Callable[[], None]:
    def run(*_args: Any) -> None:
        try:
            Gui.runCommand(key)
        except Exception:  # noqa: BLE001 - must not reach Qt's event loop
            App.Console.PrintError("Nxt: could not run %s\n" % key)
    return run
