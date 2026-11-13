"""A QML notice kept at the top centre of the active 3D view."""

from __future__ import annotations

import contextlib
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from ..core import widgets
from ..core.qt import QtCore, QtWidgets
from . import quick_host

#: Gap between the top of the 3D view, or the notice above, and a notice.
TOP_MARGIN = 10


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
        # Resizing the view while it renders nests QQuickRenderControl
        # frames, so a new size is applied after the frame.
        self._resize = QtCore.QTimer(self)
        self._resize.setSingleShot(True)
        self._resize.setInterval(0)
        self._resize.timeout.connect(self._place)

    def install(self) -> None:
        main = Gui.getMainWindow()
        area = main.findChild(QtWidgets.QMdiArea) if main is not None else None
        if area is not None:
            area.subWindowActivated.connect(self._view_changed)
            self._area = area

    def remove(self) -> None:
        if widgets.alive(self._area):
            with contextlib.suppress(RuntimeError, TypeError):
                self._area.subWindowActivated.disconnect(self._view_changed)
        self._drop()

    def reposition(self) -> None:
        """Place the notice again: one above it moved or went."""
        self._place()

    def bottom(self) -> int:
        """Where a notice under this one starts; 0 while it is not shown."""
        if not (widgets.alive(self._widget) and self._widget.isVisible()):
            return 0
        return int(self._widget.geometry().bottom()) + 1

    # -- for subclasses --

    def _wanted_host(self) -> Any:
        """The 3D view widget to show over now, or None for nowhere."""
        raise NotImplementedError

    def _context(self) -> dict[str, Any]:
        """What the QML sees, besides `theme`."""
        return {}

    def _top(self) -> int:
        return TOP_MARGIN

    def _y(self, _height: int) -> int:
        """Where the notice's top goes, given its height."""
        return self._top()

    def _view_changed(self, *_args: Any) -> None:
        self._sync()

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
        if widgets.alive(self._widget) and self._host is host:
            return self._widget
        self._drop()
        try:
            widget = quick_host.make_view(
                host, self.SOURCE,
                {"theme": self._theme, **self._context()}, floating=True)
        except quick_host.QmlLoadError as exc:
            App.Console.PrintError("Nxt: %s\n" % exc)
            return None
        host.installEventFilter(self)
        self._widget, self._host = widget, host
        # Recentre once QML has sized the new text.
        root = widget.rootObject()
        if root is not None:
            root.widthChanged.connect(self._resize.start)
            root.heightChanged.connect(self._resize.start)
        return widget

    def _place(self) -> None:
        if not (widgets.alive(self._widget) and widgets.alive(self._host)):
            return
        root = self._widget.rootObject()
        size = (QtCore.QSize(int(root.width()), int(root.height()))
                if root is not None else self._widget.sizeHint())
        self._widget.resize(size)
        self._widget.move(max(0, (self._host.width() - size.width()) // 2),
                          self._y(size.height()))

    def eventFilter(self, watched: Any, event: Any) -> bool:  # noqa: N802
        if watched is self._host \
                and event.type() == QtCore.QEvent.Type.Resize:
            self._place()
        return False

    def _drop(self) -> None:
        self._resize.stop()
        if widgets.alive(self._host):
            self._host.removeEventFilter(self)
        if widgets.alive(self._widget):
            self._widget.hide()
            self._widget.deleteLater()
        self._widget = self._host = None
