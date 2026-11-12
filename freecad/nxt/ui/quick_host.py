"""QQuickWidgets for Nxt's QML: engine, import path, context, placement."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .. import resources
from ..app import i18n
from ..core import qtquick
from ..core.qt import QtCore, QtGui, QtWidgets


class QmlLoadError(RuntimeError):
    """A QML file failed to load; the message lists QML's errors."""


def make_view(parent: QtWidgets.QWidget | None, source: str,
              context: Mapping[str, Any], *, floating: bool = False,
              prepare: Callable[[Any], None] | None = None) -> Any:
    """A QQuickWidget showing `source` from the QML folder.

    A floating view sizes itself to its QML and is see-through.
    """
    qtquick.use_shared_graphics_api()
    quick_widgets = qtquick.modules()[2]
    view = quick_widgets.QQuickWidget(parent)
    mode = quick_widgets.QQuickWidget.ResizeMode
    view.setResizeMode(mode.SizeViewToRootObject if floating
                       else mode.SizeRootObjectToView)
    if floating:
        view.setAttribute(QtCore.Qt.WidgetAttribute.WA_AlwaysStackOnTop)
        view.setClearColor(QtGui.QColor(0, 0, 0, 0))
    view.engine().addImportPath(str(resources.QML))
    root_context = view.rootContext()
    for name, value in context.items():
        root_context.setContextProperty(name, value)
    if prepare is not None:
        prepare(view)
    view.setSource(QtCore.QUrl.fromLocalFile(str(resources.qml(source))))
    if view.status() == quick_widgets.QQuickWidget.Status.Error:
        detail = "\n".join(str(e.toString()) for e in view.errors())
        view.deleteLater()
        raise QmlLoadError("%s failed to load:\n%s" % (source, detail))
    i18n.follow(view)
    return view


def window_offset(view: Any) -> QtCore.QPointF:
    """Where `view` sits in its top-level window, under Wayland only.

    Wayland places QML popups relative to the offscreen window's corner,
    so they must be shifted by this; elsewhere it is zero.
    """
    if view is None or not QtGui.QGuiApplication.platformName() \
            .startswith("wayland"):
        return QtCore.QPointF(0, 0)
    return QtCore.QPointF(view.mapTo(view.window(), QtCore.QPoint(0, 0)))


def room_in_window(view: Any) -> QtCore.QRectF:
    """Where a menu opened from `view` may go, in the view's coordinates.

    The screen's available area, less any part the window does not show
    of it. Under Wayland nobody can see where the window is on screen,
    so only the window itself is known to be visible.
    """
    if view is None:
        return QtCore.QRectF()
    top = view.window()
    corner = view.mapTo(top, QtCore.QPoint(0, 0))
    room = QtCore.QRect(-corner.x(), -corner.y(), top.width(), top.height())
    screen = view.screen()
    if screen is not None and not QtGui.QGuiApplication.platformName() \
            .startswith("wayland"):
        origin = view.mapToGlobal(QtCore.QPoint(0, 0))
        room = screen.availableGeometry().translated(-origin)
    return QtCore.QRectF(room)


def view_of(window: Any) -> Any:
    """The QQuickWidget whose offscreen window this is, or None."""
    try:
        quick_widget = qtquick.modules()[2].QQuickWidget
    except ImportError:
        return None
    for widget in QtWidgets.QApplication.allWidgets():
        if isinstance(widget, quick_widget) \
                and widget.quickWindow() is window:
            return widget
    return None


def popup_offset(item: Any) -> QtCore.QPointF:
    """window_offset for the view that holds the QML `item`."""
    return window_offset(view_of(item.window()) if item is not None
                         else None)


#: How the keyboard leaves a view for good, by the user's hand. Not to a
#: menu it opened, nor as the window loses focus (it comes back to the
#: same field), nor as the dialog rebuilds around the view.
LEAVING = (QtCore.Qt.FocusReason.TabFocusReason,
           QtCore.Qt.FocusReason.BacktabFocusReason,
           QtCore.Qt.FocusReason.MouseFocusReason,
           QtCore.Qt.FocusReason.ShortcutFocusReason)


def let_go(view: Any) -> None:
    """No item in `view` has the keyboard, nor gets it back."""
    root = view.rootObject()
    if root is None:
        return
    context = view.rootContext().contextProperty("inspector")
    if context is not None:
        context.setProperty("focused", "")
    root.forceActiveFocus()


class LetsGo(QtCore.QObject):
    """A view lets go of its focused item as the keyboard leaves it."""

    def __init__(self, view: Any) -> None:
        super().__init__(view)
        self._view = view
        view.installEventFilter(self)

    def eventFilter(self, _obj: Any, event: Any) -> bool:  # noqa: N802
        if event.type() == QtCore.QEvent.Type.FocusOut \
                and event.reason() in LEAVING:
            let_go(self._view)
        return False
