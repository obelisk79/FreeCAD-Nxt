"""Space shows or hides what is selected, as its eye in the tree would.

FreeCAD files a pick inside a Body under the Body ("Body", "Pad." or
"Pad.Face6"), so each entry is resolved to what it means: a feature
picked in the tree is that feature; a face, edge or point picked in the
3D view is the Body that shows it.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from ..core import view3d
from ..core.events import ApplicationEventFilter
from ..core.qt import QtCore, QtGui, QtWidgets
from ..core.transaction import transaction

BODY = "PartDesign::Body"
FEATURE = "PartDesign::Feature"
#: FreeCAD's own Space command.
STOCK = "Std_ToggleVisibility"
#: macOS gives a native menu bar's shortcut the key before Qt's
#: ShortcutOverride, so there FreeCAD's command loses its Space and Nxt
#: hands it the keys it does not take.
NATIVE_MENU_BAR = sys.platform == "darwin"
#: The Nxt tree's panel (tree/panel.py OBJECT_NAME).
TREE_PANEL = "NxtModelPanel"
#: Keys the Nxt tree claims (NxtTree.qml, Keys.onShortcutOverride).
TREE_KEYS = ("Space", "Home", "End", "Del", "Backspace")


def in_tree(widget: Any) -> bool:
    """Whether `widget` is inside the Nxt tree's panel."""
    while widget is not None:
        if widget.objectName() == TREE_PANEL:
            return True
        widget = widget.parentWidget()
    return False


def tree_claims(sequence: Any) -> bool:
    """A shortcut the Nxt tree handles itself, while it has the focus.

    Some Qt builds (6.8 on Windows) look for the shortcut again once the
    key reaches the tree's offscreen window, after the tree claimed it,
    so FreeCAD's command runs as well as the tree's: Space toggled
    twice. The command's shortcut event is dropped instead.
    """
    return sequence.toString() in TREE_KEYS \
        and in_tree(QtWidgets.QApplication.focusWidget())


def _is(obj: Any, type_name: str) -> bool:
    try:
        return bool(obj.isDerivedFrom(type_name))
    except Exception:
        return False


def _shown(obj: Any) -> bool:
    return bool(getattr(getattr(obj, "ViewObject", None), "Visibility",
                        False))


def _picked(doc: Any, top: Any, sub: str) -> Any:
    """The object one selection entry means.

    A geometry pick (a face, edge or point) is the innermost Body on its
    path, else the object that owns it; a path alone is its last object.
    """
    path, _dot, element = sub.rpartition(".")
    chain = [top] + [o for o in (doc.getObject(n)
                                 for n in path.split(".") if n)
                     if o is not None]
    if element:
        bodies = [o for o in chain if _is(o, BODY)]
        return bodies[-1] if bodies else chain[-1]
    return chain[-1]


def targets(doc: Any) -> list[Any]:
    """What Space should show or hide in `doc`, from the selection."""
    try:
        selection = Gui.Selection.getSelectionEx(doc.Name, 0)
    except Exception:
        return []
    found: list[Any] = []
    for entry in selection:
        top = getattr(entry, "Object", None)
        if top is None:
            continue
        subs = list(getattr(entry, "SubElementNames", ()) or ()) or [""]
        for sub in subs:
            obj = _picked(doc, top, sub or "")
            if obj is not None and obj not in found:
                found.append(obj)
    return found


def toggle(doc: Any, objects: list[Any],
           show_alone: Callable[[Any, list[str]], None] | None = None
           ) -> None:
    """Show or hide `objects` together, as one undo step.

    If any is shown all are hidden; `show_alone` runs after showing.
    Only their own visibility changes, as clicking their eyes would.
    """
    views = [(o, o.ViewObject) for o in objects
             if getattr(o, "ViewObject", None) is not None]
    if not views:
        return
    show = not any(bool(vo.Visibility) for _o, vo in views)
    try:
        with transaction(doc, "Toggle visibility"):
            for _obj, vo in views:
                vo.Visibility = show
            if show and show_alone is not None:
                show_alone(doc, [o.Name for o, _vo in views])
    except Exception:
        App.Console.PrintError("Nxt: visibility toggle failed\n")


def toggle_selected() -> None:
    doc = App.ActiveDocument
    if doc is not None:
        toggle(doc, targets(doc))


def _editing() -> bool:
    try:
        gui_doc = Gui.ActiveDocument
        return gui_doc is not None and gui_doc.getInEdit() is not None
    except Exception:
        return False


def _stock_actions() -> list[Any]:
    try:
        return list(Gui.Command.get(STOCK).getAction() or ())
    except Exception:
        return []


class SpaceInView(ApplicationEventFilter):
    """Space in a 3D view, ahead of FreeCAD's shortcut; not during edits."""

    def __init__(self, parent: QtCore.QObject | None = None,
                 action: Callable[[], None] = toggle_selected,
                 native_menu_bar: bool = NATIVE_MENU_BAR) -> None:
        super().__init__(parent)
        self._action = action
        self._native = native_menu_bar
        #: FreeCAD's actions and the shortcuts taken from them (macOS).
        self._taken: list[tuple[Any, Any]] = []
        self._fallback: Any = None

    def install(self) -> None:
        super().install()
        if self._native:
            self._take_stock_shortcut()

    def remove(self) -> None:
        super().remove()
        self._give_back_stock_shortcut()

    def _take_stock_shortcut(self) -> None:
        """Space off FreeCAD's menu item, and on an action of ours.

        Ours is an ordinary Qt shortcut, so the 3D view's claim on Space
        (ShortcutOverride, below) and the Nxt tree's and text fields' are
        honoured; anywhere else it runs FreeCAD's command as before.
        """
        main = Gui.getMainWindow()
        if main is None:
            return
        for action in _stock_actions():
            if not action.shortcut().isEmpty():
                self._taken.append((action, action.shortcut()))
                action.setShortcut(QtGui.QKeySequence())
        if not self._taken:
            return
        fallback = QtGui.QAction(main)
        fallback.setShortcut(self._taken[0][1])
        fallback.setShortcutContext(
            QtCore.Qt.ShortcutContext.ApplicationShortcut)
        fallback.triggered.connect(lambda: Gui.runCommand(STOCK, 0))
        main.addAction(fallback)
        self._fallback = fallback

    def _give_back_stock_shortcut(self) -> None:
        taken, self._taken = self._taken, []
        for action, shortcut in taken:
            try:
                action.setShortcut(shortcut)
            except RuntimeError:
                pass
        fallback, self._fallback = self._fallback, None
        if fallback is not None:
            try:
                main = fallback.parent()
                if isinstance(main, QtWidgets.QWidget):
                    main.removeAction(fallback)
                fallback.deleteLater()
            except RuntimeError:
                pass

    def eventFilter(self, watched: Any, event: Any) -> bool:  # noqa: N802
        # Sees every application event: cheap test first.
        kind = event.type()
        if kind == QtCore.QEvent.Type.Shortcut:
            try:
                return tree_claims(event.key())
            except Exception:
                return False
        if kind not in (QtCore.QEvent.Type.ShortcutOverride,
                        QtCore.QEvent.Type.KeyPress):
            return False
        try:
            if (event.key() != QtCore.Qt.Key.Key_Space
                    or event.modifiers()
                    != QtCore.Qt.KeyboardModifier.NoModifier
                    or event.isAutoRepeat()
                    or view3d.view3d_holding(watched) is None or _editing()):
                return False
        except Exception:
            return False
        event.accept()
        if kind == QtCore.QEvent.Type.ShortcutOverride:
            return False        # accepted: the key comes as a KeyPress
        try:
            self._action()
        except Exception as exc:
            App.Console.PrintError("Nxt: Space failed: %s\n" % exc)
        return True
