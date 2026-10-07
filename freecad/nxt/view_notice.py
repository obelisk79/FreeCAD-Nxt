"""A QML notice kept at the top centre of the active 3D view.

What the isolate notice (isolate_notice.py) and the undo toast (toast.py)
share: a small see-through QQuickWidget over the view, sized to its QML
root and centred again whenever either changes size.
"""

from __future__ import annotations

from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from . import qtquick, resources
from .qt import QtCore, QtGui, QtWidgets

#: Gap between the top of the 3D view, or the notice above, and a notice.
TOP_MARGIN = 10


def alive(obj: Any) -> bool:
    if obj is None:
        return False
    try:
        import shiboken6
        return bool(shiboken6.isValid(obj))
    except ImportError:
        return True


def active_view_widget() -> Any:
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


class TopNotice(QtCore.QObject):
    """Shows SOURCE over whichever 3D view `_wanted_host` names."""

    #: The QML file shown, in resources/qml.
    SOURCE = ""

    def __init__(self, theme: Any,
                 parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._widget: Any = None
        self._host: Any = None
        self._area: Any = None

    def install(self) -> None:
        main = Gui.getMainWindow()
        area = main.findChild(QtWidgets.QMdiArea) if main is not None else None
        if area is not None:
            area.subWindowActivated.connect(self._view_changed)
            self._area = area

    def remove(self) -> None:
        if alive(self._area):
            try:
                self._area.subWindowActivated.disconnect(self._view_changed)
            except (RuntimeError, TypeError):
                pass
        self._drop()

    def bottom(self) -> int:
        """Where a notice under this one starts; 0 while it is not shown."""
        if not (alive(self._widget) and self._widget.isVisible()):
            return 0
        return int(self._widget.geometry().bottom()) + 1

    # -- for subclasses ----------------------------------------------------- #

    def _wanted_host(self) -> Any:
        """The 3D view widget to show over now, or None for nowhere."""
        raise NotImplementedError

    def _context(self) -> dict[str, Any]:
        """What the QML sees, besides `theme`."""
        return {}

    def _top(self) -> int:
        return TOP_MARGIN

    def _view_changed(self, *_args: Any) -> None:
        self._sync()

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
            App.Console.PrintLog("Nxt %s: %s\n" % (self.SOURCE, exc))

    def _ensure(self, host: Any) -> Any:
        if alive(self._widget) and self._host is host:
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
        context.setContextProperty("theme", self._theme)
        for name, value in self._context().items():
            context.setContextProperty(name, value)
        widget.setSource(QtCore.QUrl.fromLocalFile(
            str(resources.qml(self.SOURCE))))
        if widget.status() == QtQuickWidgets.QQuickWidget.Status.Error:
            detail = "; ".join(str(e.toString()) for e in widget.errors())
            App.Console.PrintError("Nxt: %s failed: %s\n"
                                   % (self.SOURCE, detail))
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
        if not (alive(self._widget) and alive(self._host)):
            return
        root = self._widget.rootObject()
        size = (QtCore.QSize(int(root.width()), int(root.height()))
                if root is not None else self._widget.sizeHint())
        self._widget.resize(size)
        self._widget.move(max(0, (self._host.width() - size.width()) // 2),
                          self._top())

    def eventFilter(self, watched: Any, event: Any) -> bool:  # noqa: N802
        if watched is self._host \
                and event.type() == QtCore.QEvent.Type.Resize:
            self._place()
        return False

    def _drop(self) -> None:
        if alive(self._host):
            self._host.removeEventFilter(self)
        if alive(self._widget):
            self._widget.hide()
            self._widget.deleteLater()
        self._widget = self._host = None
