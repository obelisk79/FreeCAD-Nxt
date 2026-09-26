"""A resolved menu, turned into what the QML draws.

Everything here is plain data - dicts of strings and booleans - so QML can
read it without knowing about FreeCAD, and so it can be tested without
FreeCAD. What FreeCAD knows about a command (its label, shortcut, icon, and
whether it can run now) arrives through a `CommandInfo` lookup that
`runner.py` backs with FreeCADGui.Command; the tests pass their own.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..i18n import translate
from . import labels
from .definitions import Item, Resolved

#: The context all of the menu's own text is filed under.
CONTEXT = "NxtMenu"


@dataclass(frozen=True)
class CommandInfo:
    """What FreeCAD says about one command."""

    label: str
    shortcut: str = ""
    active: bool = True
    #: The command whose icon to draw; empty for none.
    icon: str = ""


#: Look a FreeCAD command up; None when it is not registered.
Lookup = Callable[[str], CommandInfo | None]


@dataclass(frozen=True)
class Subject:
    """What the menu is about, for its header and a few labels."""

    title: str
    subtitle: str = ""
    count: int = 1
    #: Whether any selected object is shown, for the bar's Hide or Show.
    any_shown: bool = True


def present(menu: Resolved, subject: Subject,
            lookup: Lookup) -> dict[str, Any]:
    """The menu as QML reads it.

    Items whose FreeCAD command is not registered (a workbench that is not
    installed) are left out. Commands FreeCAD says cannot run now stay, drawn
    disabled, as FreeCAD's own menu draws them.
    """
    def entry(item: Item | None) -> dict[str, Any] | None:
        return None if item is None else _entry(item, subject, lookup)

    def entries(items: list[Item]) -> list[dict[str, Any]]:
        return [e for e in (entry(i) for i in items) if e is not None]

    bar = []
    for item in menu.bar:
        shown = entry(item)
        if shown is None:
            continue
        shown["short"] = _bar_label(item.command, subject)
        if item.command in menu.dimmed:
            shown["enabled"] = False
        bar.append(shown)

    return {
        "title": subject.title,
        "subtitle": subject.subtitle,
        "bar": bar,
        "lead": entry(menu.lead),
        "state": entries(menu.state),
        "sections": [{"name": translate(CONTEXT, name),
                      "items": items}
                     for name, items in ((n, entries(i))
                                         for n, i in menu.sections)
                     if items],
        "delete": entry(menu.delete),
        "more": [{"name": translate(CONTEXT, name), "items": items}
                 for name, items in ((n, entries(i)) for n, i in menu.more)
                 if items]
        + [{"name": "", "items": [_native_entry()]}],
    }


def _entry(item: Item, subject: Subject,
           lookup: Lookup) -> dict[str, Any] | None:
    if item.items:
        children = [e for e in (_entry(i, subject, lookup)
                                for i in item.items) if e is not None]
        if not children:
            return None
        return {"command": item.command,
                "label": translate(CONTEXT, item.label), "shortcut": "",
                "enabled": True, "icon": "", "items": children}
    command = item.command
    label = translate(CONTEXT, item.label) if item.label else ""
    shortcut, enabled, icon = "", True, ""

    if command.startswith("nxt:"):
        text = labels.ACTIONS.get(command, command)
        label = label or translate(CONTEXT, text)
        icon = labels.ICONS.get(command, "")
    elif command.startswith("edit:"):
        label = label or translate(CONTEXT, "Edit %1").replace(
            "%1", subject.title)
    else:
        info = lookup(command)
        if info is None:
            return None
        label = label or info.label
        shortcut, enabled, icon = info.shortcut, info.active, info.icon

    return {"command": command, "label": label, "shortcut": shortcut,
            "enabled": enabled, "icon": icon}


def _bar_label(command: str, subject: Subject) -> str:
    if command == "Std_ToggleVisibility":
        text = labels.BAR["hide" if subject.any_shown else "show"]
    else:
        text = labels.BAR.get(command, "")
    return translate(CONTEXT, text)


def _native_entry() -> dict[str, Any]:
    return {"command": "nxt:native_menu",
            "label": translate(CONTEXT, labels.ACTIONS["nxt:native_menu"]),
            "shortcut": "", "enabled": True, "icon": ""}
