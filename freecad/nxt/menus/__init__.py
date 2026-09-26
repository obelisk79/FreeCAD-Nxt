"""The tree's context menu, built from definition files.

Nxt's own definitions are `resources/menus/default.toml`. An addon adds its
own with one call, and needs nothing else from Nxt:

    try:
        from freecad.nxt import menus
        menus.register(Path(__file__).parent / "nxt_menu.toml")
    except ImportError:
        pass    # Nxt is not installed

To see why the current selection's menu is what it is:

    from freecad.nxt import menus; menus.explain()
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import FreeCAD as App

from .definitions import Definitions, ObjectFacts, Resolved, load, resolve

_registered: list[Path] = []
_cache: Definitions | None = None


def register(path: Path | str) -> None:
    """Add an addon's definition file; its menus apply after Nxt's own."""
    path = Path(path)
    if path not in _registered:
        _registered.append(path)
    invalidate()


def invalidate() -> None:
    """Read the files again on next use: after editing one, say."""
    global _cache
    _cache = None


def loaded() -> Definitions:
    """Nxt's definitions and every registered file's, merged."""
    global _cache
    if _cache is None:
        # Looked up afresh rather than through resources.MENUS: Reload Nxt
        # keeps an older resources module until FreeCAD restarts.
        default = Path(str(files("freecad.nxt.resources") / "menus"))
        merged = load(default / "default.toml")
        for path in _registered:
            merged.extend(load(path))
        for error in merged.errors:
            App.Console.PrintWarning("Nxt menu: %s\n" % error)
        _cache = merged
    return _cache


def for_selection(selection: list[ObjectFacts]) -> Resolved:
    """The menu for these objects."""
    return resolve(loaded(), selection)


def explain(selection: list[ObjectFacts] | None = None) -> Resolved:
    """Print why each command is in the menu, or not, for the selection."""
    if selection is None:
        selection = current_selection()
    menu = for_selection(selection)
    App.Console.PrintMessage("\n=== Nxt menu ===\n")
    for line in menu.trace or ["(nothing selected)"]:
        App.Console.PrintMessage("  %s\n" % line)
    App.Console.PrintMessage("=== end ===\n\n")
    return menu


def current_selection() -> list[ObjectFacts]:
    """Facts for FreeCAD's current selection, read afresh."""
    import FreeCADGui as Gui

    from ..tree import scene
    from .facts import of

    doc = App.ActiveDocument
    if doc is None:
        return []
    snapshot = scene.Snapshot(doc)
    return [of(obj, snapshot.nodes.get(obj.Name), snapshot.nodes)
            for obj in Gui.Selection.getSelection(doc.Name)]
