"""The undo toast at the top centre of the 3D view.

"Moved Pocket after Pad · Undo": what Nxt just did in one gesture, with a
way back (ToastBanner.qml). It belongs to the services, so anything in
Nxt can raise one through `services.toast`, with the model panel open or
not. With no 3D view to show it over, the message goes to the Report
view instead.

It also carries what Nxt found and left for the user, with buttons of
the caller's own: "Sketch is not closed · Edit".

What Undo would undo is remembered by the document's undo count, so it
does nothing once anything else has happened.
"""

from __future__ import annotations

import traceback
from collections.abc import Callable, Sequence
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from .i18n import translate
from .qt import QtCore
from .view_notice import TopNotice, active_view_widget, alive

#: Called with the document once the toast's Undo has undone the change,
#: for whatever undo does not restore by itself (view state).
AfterUndo = Callable[[Any], None]
#: A button on the toast: (its label, what it does).
Action = tuple[str, Callable[[], Any]]


class Toast(TopNotice):
    """One message at a time; a new one replaces the last."""

    SOURCE = "ToastBanner.qml"

    shown = QtCore.Signal()
    cleared = QtCore.Signal()

    def __init__(self, theme: Any, above: Callable[[], TopNotice | None],
                 parent: QtCore.QObject | None = None) -> None:
        super().__init__(theme, parent)
        #: The notice this one keeps clear of, when that one is showing.
        self._above = above
        self._message = ""
        #: What is showing: (document, its undo count just after the
        #: change or None if there is nothing to undo, AfterUndo).
        self._current: tuple[str, int | None, AfterUndo | None] | None = None
        self._actions: list[Action] = []
        self._sticky = False

    @QtCore.Property(str, notify=shown)
    def message(self) -> str:
        return self._message

    @QtCore.Property(list, notify=shown)
    def labels(self) -> list[str]:
        return [label for label, _action in self._actions]

    @QtCore.Property(bool, notify=shown)
    def sticky(self) -> bool:
        return self._sticky

    def show(self, doc: Any, message: str,
             after_undo: AfterUndo | None = None, undoable: bool = True,
             actions: Sequence[Action] = (), sticky: bool = False) -> None:
        """Say what was just done to `doc`, and offer to undo it.

        Not `undoable`: something to be told that Nxt did not do.
        `actions` are further buttons; `sticky` keeps it up until one is
        used or it is dismissed.
        """
        self._current = (
            str(getattr(doc, "Name", "")),
            int(getattr(doc, "UndoCount", -1)) if undoable else None,
            after_undo)
        undo: list[Action] = (
            [(translate("Nxt", "Undo"), self.undo)] if undoable else [])
        self._actions = undo + list(actions)
        self._sticky = sticky
        self._message = message
        self.shown.emit()
        self._sync()
        if not (alive(self._widget) and self._widget.isVisible()):
            self.dismissed()
            App.Console.PrintMessage("Nxt: %s\n" % message)

    @QtCore.Slot(int)
    def act(self, index: int) -> None:
        """A button on the toast was used."""
        if not 0 <= index < len(self._actions):
            return
        action = self._actions[index][1]
        if action != self.undo:
            self.dismissed()
        action()

    @QtCore.Slot(result=bool)
    def undo(self) -> bool:
        """The toast's Undo. True if the change was undone."""
        pending, self._current = self._current, None
        self.cleared.emit()
        doc = App.ActiveDocument
        if pending is None or doc is None:
            return False
        name, count, after_undo = pending
        if doc.Name != name or int(getattr(doc, "UndoCount", -1)) != count:
            return False        # something else has happened since
        try:
            doc.undo()
            if after_undo is not None:
                after_undo(doc)
            doc.recompute()
        except Exception:
            App.Console.PrintError("Nxt: could not undo\n")
            App.Console.PrintError(traceback.format_exc())
            return False
        return True

    @QtCore.Slot()
    def dismissed(self) -> None:
        """The toast has gone, by itself or by hand: Undo goes with it."""
        self._current = None
        if alive(self._widget):
            self._widget.hide()     # kept, for the next message

    # ------------------------------------------------------------------ #

    def _context(self) -> dict[str, Any]:
        return {"toasts": self}

    def _wanted_host(self) -> Any:
        if self._current is None:
            return None
        gui_doc = Gui.ActiveDocument
        if gui_doc is None or gui_doc.Document.Name != self._current[0]:
            return None
        return active_view_widget()

    def _view_changed(self, *_args: Any) -> None:
        # Another view is something else happening: the toast does not
        # follow there.
        if self._current is not None \
                and self._wanted_host() is not self._host:
            self.dismissed()

    def _top(self) -> int:
        above = self._above()
        return super()._top() + (above.bottom() if above is not None else 0)

    def _place(self) -> None:
        if alive(self._widget) and alive(self._host):
            root = self._widget.rootObject()
            if root is not None:
                root.setProperty("available", self._host.width())
        super()._place()
