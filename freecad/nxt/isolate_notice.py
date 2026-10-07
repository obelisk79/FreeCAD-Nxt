"""The isolate mode's notice at the top centre of the 3D view.

A small QQuickWidget over the active 3D view while the mode is on
(isolate.py), showing IsolationBanner.qml: what is isolated, and Exit.
It is the mode's one notice; the model panel only dims. It follows the
active view: shown over any 3D view of the isolated document that
becomes active, never over another document's.
"""

from __future__ import annotations

from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from .qt import QtCore, QtWidgets
from .view_notice import TopNotice, active_view_widget


class ViewNotice(TopNotice):
    """Keeps the notice over the active 3D view while isolating."""

    SOURCE = "IsolationBanner.qml"

    def __init__(self, isolation: Any, theme: Any,
                 parent: QtCore.QObject | None = None) -> None:
        super().__init__(theme, parent)
        self._isolation = isolation
        isolation.changed.connect(self._sync)

    def remove(self) -> None:
        try:
            self._isolation.changed.disconnect(self._sync)
        except (RuntimeError, TypeError):
            pass
        super().remove()

    def _context(self) -> dict[str, Any]:
        return {"isolation": self._isolation}

    def _wanted_host(self) -> Any:
        if not self._isolation.active():
            return None
        gui_doc = Gui.ActiveDocument
        if gui_doc is None \
                or gui_doc.Document.Name != self._isolation.document():
            return None
        return active_view_widget()


class EscapeToExit(QtCore.QObject):
    """Escape leaves the isolate mode from anywhere it means nothing else.

    An application event filter, so it works with the keyboard in the 3D
    view or anywhere else - not only in the model panel. It stands aside,
    and Escape does what it always did, whenever:
      * the mode is off;
      * a task panel is open or something is being edited, where Escape
        cancels the task;
      * a dialog, menu or popup is up;
      * the keyboard is in a text field or spin box, where Escape belongs
        to the field;
      * the keyboard is in the model panel, whose own Escape closes a
        detail strip first and then leaves the mode.
    """

    def __init__(self, isolation: Any,
                 parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._isolation = isolation

    def install(self) -> None:
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def remove(self) -> None:
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)

    def eventFilter(self, watched: Any, event: Any) -> bool:  # noqa: N802
        # Every event in the application passes here: cheap tests first.
        if event.type() != QtCore.QEvent.Type.KeyPress \
                or event.key() != QtCore.Qt.Key.Key_Escape:
            return False
        try:
            if not self._isolation.active() or not self._free():
                return False
            return bool(self._isolation.exit())
        except Exception as exc:
            App.Console.PrintLog("Nxt isolate Escape: %s\n" % exc)
            return False

    @staticmethod
    def _free() -> bool:
        """Whether Escape means nothing else right now."""
        app = QtWidgets.QApplication.instance()
        if app is None:
            return False
        if app.activeModalWidget() is not None \
                or app.activePopupWidget() is not None:
            return False
        try:
            if Gui.Control.activeDialog():
                return False
        except Exception:
            pass
        gui_doc = Gui.ActiveDocument
        if gui_doc is not None and gui_doc.getInEdit() is not None:
            return False
        focus = app.focusWidget()
        if isinstance(focus, (QtWidgets.QLineEdit, QtWidgets.QTextEdit,
                              QtWidgets.QPlainTextEdit,
                              QtWidgets.QAbstractSpinBox)):
            return False
        widget = focus
        while widget is not None:
            if widget.objectName() == "NxtModelPanel":
                return False            # the panel's own Escape
            widget = widget.parentWidget()
        return True
