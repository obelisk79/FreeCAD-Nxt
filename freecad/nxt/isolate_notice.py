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

from . import qtquick, resources
from .qt import QtCore, QtGui, QtWidgets

#: Gap between the top of the 3D view and the notice.
TOP_MARGIN = 10


def _alive(obj: Any) -> bool:
    if obj is None:
        return False
    try:
        import shiboken6
        return bool(shiboken6.isValid(obj))
    except ImportError:
        return True


def _active_view_widget() -> Any:
    """The active MDI window's 3D view widget, or None."""
    main = Gui.getMainWindow()
    area = main.findChild(QtWidgets.QMdiArea) if main is not None else None
    sub = area.activeSubWindow() if area is not None else None
    holder = sub.widget() if sub is not None else None
    if holder is None \
            or holder.metaObject().className() != "Gui::View3DInventor":
        return None
    for child in holder.findChildren(QtWidgets.QWidget):
        if "GL" in child.metaObject().className() and child.isVisible():
            return child
    return None


class ViewNotice(QtCore.QObject):
    """Keeps the notice over the active 3D view while isolating."""

    def __init__(self, isolation: Any, theme: Any,
                 parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._isolation = isolation
        self._theme = theme
        self._widget: Any = None
        self._host: Any = None
        self._area: Any = None
        isolation.changed.connect(self._sync)

    def install(self) -> None:
        main = Gui.getMainWindow()
        area = main.findChild(QtWidgets.QMdiArea) if main is not None else None
        if area is not None:
            area.subWindowActivated.connect(self._sync)
            self._area = area

    def remove(self) -> None:
        try:
            self._isolation.changed.disconnect(self._sync)
        except (RuntimeError, TypeError):
            pass
        if _alive(self._area):
            try:
                self._area.subWindowActivated.disconnect(self._sync)
            except (RuntimeError, TypeError):
                pass
        self._drop()

    # ------------------------------------------------------------------ #

    def _sync(self, *_args: Any) -> None:
        try:
            host = self._wanted_host()
            if host is None:
                self._drop()
                return
            widget = self._ensure(host)
            if widget is not None:
                self._place()
                widget.show()
                widget.raise_()
        except Exception as exc:
            App.Console.PrintLog("Nxt isolate notice: %s\n" % exc)

    def _wanted_host(self) -> Any:
        if not self._isolation.active():
            return None
        gui_doc = Gui.ActiveDocument
        if gui_doc is None \
                or gui_doc.Document.Name != self._isolation.document():
            return None
        return _active_view_widget()

    def _ensure(self, host: Any) -> Any:
        if _alive(self._widget) and self._host is host:
            return self._widget
        self._drop()
        qtquick.use_shared_graphics_api()
        _QtQml, _QtQuick, QtQuickWidgets = qtquick.modules()  # noqa: N806
        widget = QtQuickWidgets.QQuickWidget(host)
        widget.setResizeMode(
            QtQuickWidgets.QQuickWidget.ResizeMode.SizeViewToRootObject)
        widget.setAttribute(QtCore.Qt.WidgetAttribute.WA_AlwaysStackOnTop)
        widget.setClearColor(QtGui.QColor(0, 0, 0, 0))
        widget.engine().addImportPath(str(resources.QML))
        context = widget.rootContext()
        context.setContextProperty("isolation", self._isolation)
        context.setContextProperty("theme", self._theme)
        widget.setSource(QtCore.QUrl.fromLocalFile(
            str(resources.qml("IsolationBanner.qml"))))
        if widget.status() == QtQuickWidgets.QQuickWidget.Status.Error:
            detail = "; ".join(str(e.toString()) for e in widget.errors())
            App.Console.PrintError("Nxt: isolate notice failed: %s\n"
                                   % detail)
            widget.deleteLater()
            return None
        host.installEventFilter(self)
        self._widget, self._host = widget, host
        # Sized to its text: a new text means a new width, and it has to
        # be centred again once QML has worked it out.
        root = widget.rootObject()
        if root is not None:
            root.widthChanged.connect(self._place)
        return widget

    def _place(self) -> None:
        if not (_alive(self._widget) and _alive(self._host)):
            return
        root = self._widget.rootObject()
        size = (QtCore.QSize(int(root.width()), int(root.height()))
                if root is not None else self._widget.sizeHint())
        self._widget.resize(size)
        self._widget.move(max(0, (self._host.width() - size.width()) // 2),
                          TOP_MARGIN)

    def eventFilter(self, watched: Any, event: Any) -> bool:  # noqa: N802
        if watched is self._host \
                and event.type() == QtCore.QEvent.Type.Resize:
            self._place()
        return False

    def _drop(self) -> None:
        if _alive(self._host):
            self._host.removeEventFilter(self)
        if _alive(self._widget):
            self._widget.hide()
            self._widget.deleteLater()
        self._widget = self._host = None


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
