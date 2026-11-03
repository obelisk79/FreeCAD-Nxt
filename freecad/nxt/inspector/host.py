"""The Property Inspector: every property of the selection, beside the panel.

QML over a borrowed `Gui::PropertyView`, which is returned to its exact
place. A child of the main window, since Wayland cannot place top-levels.
"""

from __future__ import annotations

import contextlib
import traceback
from dataclasses import dataclass
from typing import Any, cast

import FreeCAD as App
import FreeCADGui as Gui

from ..app.i18n import translate
from ..core import settings
from ..core.qt import QtCore, QtGui, QtWidgets
from ..tools import expressions
from ..ui.glyphs import pin_icon


def table_icon(size: int, colour: QtGui.QColor,
               ratio: float = 1.0) -> QtGui.QIcon:
    """A small two-column table icon for FreeCAD's Property editor."""
    ratio = ratio or 1.0
    pixmap = QtGui.QPixmap(round(size * ratio), round(size * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
    painter.scale(size, size)
    pen = QtGui.QPen(colour)
    pen.setWidthF(0.08)
    pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(QtCore.QRectF(0.08, 0.14, 0.84, 0.72),
                            0.06, 0.06)
    for y in (0.38, 0.62):
        painter.drawLine(QtCore.QPointF(0.08, y), QtCore.QPointF(0.92, y))
    painter.drawLine(QtCore.QPointF(0.42, 0.14), QtCore.QPointF(0.42, 0.86))
    painter.end()
    return QtGui.QIcon(pixmap)


PROPERTY_VIEW_CLASS = "Gui::PropertyView"
PROPERTY_DOCK_NAME = "Property view"

INSPECTOR_SIZE = QtCore.QSize(330, 480)
INSPECTOR_MARGIN = 8
INSPECTOR_GAP = 6
INSPECTOR_RADIUS = 4
HEADER_SPACING = 4
TITLE_POLL_MS = 250
SAVE_DELAY_MS = 300


def _app() -> QtCore.QCoreApplication:
    """The running application."""
    return cast(QtCore.QCoreApplication, QtWidgets.QApplication.instance())


@dataclass
class _Home:
    """Where the Property editor lived before the inspector borrowed it."""

    widget: QtWidgets.QWidget
    container: QtWidgets.QWidget
    kind: str               # "dock", "splitter", "tab" or "layout"
    index: int
    visible: bool
    tab_label: str = ""
    current_tab: int = 0
    #: For a grid layout: row, column, row span, column span.
    cell: tuple[int, int, int, int] | None = None

    def restore(self) -> None:
        """Put the widget back where it came from, as it was."""
        widget = self.widget
        container: Any = self.container
        if self.kind == "tab":
            # QTabWidget owns page visibility; restore the current tab.
            container.insertTab(self.index, widget, self.tab_label)
            container.setCurrentIndex(self.current_tab)
            return
        if self.kind == "dock":
            container.setWidget(widget)
        elif self.kind == "splitter":
            container.insertWidget(self.index, widget)
        else:
            _insert_into_layout(container.layout(), widget, self)
        widget.setVisible(self.visible)


def _insert_into_layout(layout: QtWidgets.QLayout, widget: QtWidgets.QWidget,
                        home: _Home) -> None:
    """Put `widget` back into its layout; FreeCAD's dock uses a grid."""
    if isinstance(layout, QtWidgets.QGridLayout) and home.cell is not None:
        layout.addWidget(widget, *home.cell)
    elif isinstance(layout, QtWidgets.QBoxLayout):
        layout.insertWidget(home.index, widget)
    else:
        layout.addWidget(widget)


def _class_name(widget: QtWidgets.QWidget) -> str:
    return widget.metaObject().className()


def _property_views() -> list[QtWidgets.QWidget]:
    mw = Gui.getMainWindow()
    if mw is None:
        return []
    return [w for w in mw.findChildren(QtWidgets.QWidget)
            if _class_name(w) == PROPERTY_VIEW_CLASS]


def _preferred_view() -> QtWidgets.QWidget | None:
    """The Property view dock's editor if there is one, else any."""
    views = _property_views()
    for view in views:
        dock = _enclosing_dock(view)
        if dock is not None and dock.objectName() == PROPERTY_DOCK_NAME:
            return view
    return views[0] if views else None


def _enclosing_dock(widget: QtWidgets.QWidget) -> QtWidgets.QDockWidget | None:
    cursor = widget.parentWidget()
    while cursor is not None:
        if isinstance(cursor, QtWidgets.QDockWidget):
            return cursor
        cursor = cursor.parentWidget()
    return None


def _home_of(widget: QtWidgets.QWidget) -> _Home | None:
    """Record exactly where `widget` sits, or None if we cannot put it back."""
    parent = widget.parentWidget()
    visible = not widget.isHidden()    # its own flag, not its dock's
    if isinstance(parent, QtWidgets.QDockWidget) and parent.widget() is widget:
        return _Home(widget, parent, "dock", 0, visible)
    if isinstance(parent, QtWidgets.QSplitter):
        return _Home(widget, parent, "splitter", parent.indexOf(widget),
                     visible)
    tabs = parent.parentWidget() if parent is not None else None
    if isinstance(tabs, QtWidgets.QTabWidget):
        index = tabs.indexOf(widget)
        return _Home(widget, tabs, "tab", index, visible,
                     tabs.tabText(index), tabs.currentIndex())
    layout = parent.layout() if parent is not None else None
    index = layout.indexOf(widget) if layout is not None else -1
    if index < 0:
        return None
    cell: tuple[int, int, int, int] | None = None
    if isinstance(layout, QtWidgets.QGridLayout):
        position: Any = layout.getItemPosition(index)
        cell = (int(position[0]), int(position[1]),
                int(position[2]), int(position[3]))
    return _Home(widget, cast(QtWidgets.QWidget, parent), "layout", index,
                 visible, cell=cell)


def probe() -> None:
    """Report every Property editor and whether it can be borrowed."""
    views = _property_views()
    if not views:
        App.Console.PrintMessage("Nxt: no %s found\n" % PROPERTY_VIEW_CLASS)
        return
    chosen = _preferred_view()
    for view in views:
        chain: list[str] = []
        cursor = view.parentWidget()
        while cursor is not None and len(chain) < 6:
            chain.append("%s(%s)" % (_class_name(cursor),
                                     cursor.objectName() or "-"))
            cursor = cursor.parentWidget()
        home = _home_of(view)
        App.Console.PrintMessage(
            "Nxt: %s%s  visible=%s  home=%s\n    in %s\n"
            % (PROPERTY_VIEW_CLASS, "  <- inspector uses this"
               if view is chosen else "", view.isVisible(),
               "%s[%d]" % (home.kind, home.index) if home else "UNKNOWN",
               " < ".join(chain)))


class PropertyInspector(QtWidgets.QFrame):
    """A frame over the main window holding the borrowed editor."""

    def __init__(self, main_window: QtWidgets.QMainWindow) -> None:
        super().__init__(main_window)
        self.setObjectName("NxtPropertyInspector")
        # Without SubWindow, QSizeGrip resizes FreeCAD's main window.
        self.setWindowFlag(QtCore.Qt.WindowType.SubWindow)
        # Not a native window: that fights FreeCAD's overlay manager.
        self.setAutoFillBackground(True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self._home: _Home | None = None

        self._title = QtWidgets.QLabel(self)
        bold = self._title.font()
        bold.setBold(True)
        self._title.setFont(bold)
        self._title.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
        self._title.setToolTip(translate("Nxt", "Drag to move"))
        self._pin = self._tool_button(
            translate("Nxt", "Keep open and follow the selection"), "⊙",
            checkable=True)
        self._pin.setText("")
        self._pin.setChecked(settings.get("InspectorPinned"))
        self._pin.toggled.connect(self._on_pin_toggled)
        self._draw_pin()
        self._grab: QtCore.QPoint | None = None
        self._grab_origin = QtCore.QPoint()
        self._close = self._tool_button(translate("Nxt", "Close"), "✕")
        self._close.clicked.connect(self.close_inspector)
        self._table = self._tool_button(
            translate("Nxt", "Show FreeCAD's property table"), "",
            checkable=True)
        self._table.toggled.connect(self._on_table_toggled)
        self._draw_pin()

        header = QtWidgets.QHBoxLayout()
        header.setSpacing(HEADER_SPACING)
        header.addWidget(self._title, 1)
        header.addWidget(self._table)
        header.addWidget(self._pin)
        header.addWidget(self._close)

        self._back = self._tool_button(
            translate("Nxt", "Back to the inspector"), "←")
        self._back.clicked.connect(self.show_inspector)
        self._back.hide()
        header.insertWidget(0, self._back)

        self._body = QtWidgets.QVBoxLayout(self)
        self._body.setContentsMargins(INSPECTOR_GAP, INSPECTOR_GAP,
                                      INSPECTOR_GAP, INSPECTOR_GAP)
        self._body.addLayout(header)

        self._pages = QtWidgets.QStackedWidget(self)
        self._native = QtWidgets.QWidget(self._pages)
        native_layout = QtWidgets.QVBoxLayout(self._native)
        native_layout.setContentsMargins(0, 0, 0, 0)
        self._pages.addWidget(self._native)
        self._body.addWidget(self._pages, 1)
        self._inspector: QtWidgets.QWidget | None = None
        self._inspector_bridge: Any = None
        self._inspector_failed = False

        grip = QtWidgets.QSizeGrip(self)
        grip.setToolTip(translate("Nxt", "Drag to resize"))
        self._body.addWidget(grip, 0, QtCore.Qt.AlignmentFlag.AlignRight
                             | QtCore.Qt.AlignmentFlag.AlignBottom)

        self._save_timer = QtCore.QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(SAVE_DELAY_MS)
        self._save_timer.timeout.connect(self._save_geometry)

        self._title_timer = QtCore.QTimer(self)
        self._title_timer.setInterval(TITLE_POLL_MS)
        self._title_timer.timeout.connect(self._sync_title)

        self.resize(INSPECTOR_SIZE)
        self.hide()

    def _tool_button(self, tip: str, glyph: str,
                     checkable: bool = False) -> QtWidgets.QToolButton:
        button = QtWidgets.QToolButton(self)
        button.setText(glyph)
        button.setToolTip(tip)
        button.setAccessibleName(tip)
        button.setCheckable(checkable)
        button.setAutoRaise(True)
        # One square size so hover backgrounds line up.
        side = button.fontMetrics().height() + 8
        button.setFixedSize(side, side)
        return button

    # -- borrowing --

    def _borrow(self) -> bool:
        view = _preferred_view()
        if view is None:
            App.Console.PrintError("Nxt: no Property editor to borrow\n")
            return False
        home = _home_of(view)
        if home is None:
            App.Console.PrintError(
                "Nxt: the Property editor sits somewhere the inspector cannot "
                "put it back; run property_inspector.probe() and report it\n")
            return False
        self._home = home
        cast(QtWidgets.QLayout, self._native.layout()).addWidget(view)
        view.show()
        return True

    def _give_back(self) -> None:
        home, self._home = self._home, None
        if home is None:
            return
        try:
            home.restore()
        except Exception:
            # Detach it: the inspector is destroyed on reload.
            home.widget.setParent(self.parentWidget())
            home.widget.hide()
            App.Console.PrintError("Nxt: could not return the Property "
                                   "editor to its place; restart FreeCAD "
                                   "to get it back\n")
            App.Console.PrintError(traceback.format_exc())

    # -- showing --

    def open_at(self, left: int | None = None,
                top: int | None = None) -> None:
        """Open with its top-left at global (`left`, `top`)."""
        self._follow_theme()
        built = self._build_inspector()
        if built and settings.get("InspectorTable"):
            self.show_native()
        elif built:
            self.show_inspector()
        elif self._home is None and not self._borrow():
            return
        else:
            self._pages.setCurrentWidget(self._native)
        self._place(left, top)
        self._sync_title()
        self._title_timer.start()
        _app().installEventFilter(self)
        self.show()
        self.raise_()

    def close_inspector(self) -> None:
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._save_geometry()
        _app().removeEventFilter(self)
        self._title_timer.stop()
        if self._inspector_bridge is not None:
            self._inspector_bridge.stop()
        self.hide()
        self._give_back()

    # -- the two pages --

    def _build_inspector(self) -> bool:
        """Create the QML page once. False if QtQuick cannot."""
        if self._inspector is not None:
            return True
        if self._inspector_failed:
            return False
        try:
            self._inspector = _make_inspector(self._pages)
        except Exception:
            self._inspector_failed = True
            App.Console.PrintError("Nxt: the Property Inspector fell back to "
                                   "FreeCAD's editor\n")
            App.Console.PrintError(traceback.format_exc())
            return False
        self._inspector_bridge = getattr(self._inspector, "nxt_bridge")
        self._inspector_bridge.nativeRequested.connect(self.show_native)
        self._pages.insertWidget(0, self._inspector)
        return True

    def _on_table_toggled(self, on: bool) -> None:
        # Only this button records the page choice.
        settings.put("InspectorTable", on)
        if on:
            self.show_native()
        elif self._inspector is None:
            self._mark_table(True)
        else:
            self.show_inspector()

    def _mark_table(self, on: bool) -> None:
        """Show which page is up on the table button, without acting."""
        self._table.blockSignals(True)
        self._table.setChecked(on)
        self._table.blockSignals(False)

    def show_inspector(self) -> None:
        self._mark_table(False)
        self._give_back()
        self._back.hide()
        if self._inspector is None:
            return
        self._pages.setCurrentWidget(self._inspector)
        self._inspector_bridge.start()

    def show_native(self, prop: str = "") -> None:
        """FreeCAD's own editor, for a property the QML cannot edit."""
        if self._home is None and not self._borrow():
            self._mark_table(False)
            return
        self._mark_table(True)
        if self._inspector_bridge is not None:
            self._inspector_bridge.stop()
        self._back.setVisible(self._inspector is not None)
        self._pages.setCurrentWidget(self._native)

    @property
    def pinned(self) -> bool:
        return self._pin.isChecked()

    def _place(self, left: int | None, top: int | None) -> None:
        """Pinned: where it was last put. Unpinned: beside the row."""
        saved = self._saved_geometry()
        if self.pinned and saved is not None:
            self.setGeometry(saved)
            self._keep_inside()
            return
        mw = self.parentWidget()
        pointer = QtGui.QCursor.pos()
        corner = cast(QtWidgets.QWidget, mw).mapFromGlobal(QtCore.QPoint(
            left if left is not None else pointer.x(),
            top if top is not None else pointer.y()))
        if left is not None:
            x = corner.x() + INSPECTOR_GAP
        else:
            x = self._dock_edge(cast(QtWidgets.QWidget, mw))
        self.move(x, corner.y())
        self._keep_inside()

    @staticmethod
    def _dock_edge(mw: QtWidgets.QWidget) -> int:
        """Just past the Nxt dock's border, or the window's margin."""
        from ..tree import panel
        dock = panel.instance()
        if dock is None or not dock.isVisible():
            return INSPECTOR_MARGIN
        edge = dock.mapTo(mw, QtCore.QPoint(dock.width(), 0)).x()
        return edge + INSPECTOR_GAP

    def _keep_inside(self) -> None:
        """Clamp to the main window, shrinking only if it has to."""
        bounds = cast(QtWidgets.QWidget, self.parentWidget()).rect().adjusted(
            INSPECTOR_MARGIN, INSPECTOR_MARGIN,
            -INSPECTOR_MARGIN, -INSPECTOR_MARGIN)
        size = self.size().boundedTo(bounds.size())
        x = max(bounds.left(), min(self.x(), bounds.right() - size.width()))
        y = max(bounds.top(), min(self.y(), bounds.bottom() - size.height()))
        self.setGeometry(x, y, size.width(), size.height())

    # -- moving and remembering --

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._grab = event.globalPosition().toPoint()
            self._grab_origin = self.pos()
            self._title.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        # Global coordinates: local ones move with the inspector.
        if self._grab is not None:
            self.move(self._grab_origin
                      + event.globalPosition().toPoint() - self._grab)
            self._keep_inside()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(  # noqa: N802
            self, event: QtGui.QMouseEvent) -> None:
        if self._grab is not None:
            self._grab = None
            self._title.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
            self._save_geometry()
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self.isVisible():
            self._save_timer.start()

    def _draw_pin(self) -> None:
        """The header's drawn icons: the pin and, once made, the table."""
        colour = self._icon_colour()
        # Cap height, to match the neighbouring "✕".
        metrics = self._pin.fontMetrics()
        side = max(10, round(metrics.capHeight() * 1.35))
        self._pin.setIcon(pin_icon(side, self._pin.isChecked(), colour,
                                   self.devicePixelRatioF()))
        self._pin.setIconSize(QtCore.QSize(side, side))
        table = getattr(self, "_table", None)
        if table is not None:
            table.setIcon(table_icon(side, colour,
                                     self.devicePixelRatioF()))
            table.setIconSize(QtCore.QSize(side, side))

    def _follow_theme(self) -> None:
        """Redraw the header's icons now, and whenever the theme changes."""
        from ..app import services
        theme = services.theme()
        if theme is not None and not getattr(self, "_theme_hooked", False):
            theme.changed.connect(self._draw_pin)
            self._theme_hooked = True
        self._draw_pin()

    def _icon_colour(self) -> QtGui.QColor:
        """The theme's text colour; stylesheets can leave the palette wrong."""
        from ..app import services
        theme = services.theme()
        if theme is not None:
            with contextlib.suppress(Exception):
                return QtGui.QColor(theme.property("text"))
        return self._pin.palette().color(QtGui.QPalette.ColorRole.ButtonText)

    def changeEvent(self, event: QtCore.QEvent) -> None:  # noqa: N802
        super().changeEvent(event)
        if (event.type() == QtCore.QEvent.Type.PaletteChange
                and hasattr(self, "_pin")):
            self._draw_pin()

    def _on_pin_toggled(self, pinned: bool) -> None:
        self._draw_pin()
        settings.put("InspectorPinned", pinned)
        self._save_geometry()

    def _save_geometry(self) -> None:
        """Remember where a pinned inspector sits; unpinned is transient."""
        if not self.pinned:
            return
        for key, value in (("InspectorX", self.x()), ("InspectorY", self.y()),
                           ("InspectorWidth", self.width()),
                           ("InspectorHeight", self.height())):
            settings.put(key, value)

    @staticmethod
    def _saved_geometry() -> QtCore.QRect | None:
        width = settings.get("InspectorWidth")
        height = settings.get("InspectorHeight")
        if width <= 0 or height <= 0:
            return None
        return QtCore.QRect(settings.get("InspectorX"),
                            settings.get("InspectorY"), width, height)

    def _sync_title(self) -> None:
        try:
            names = [o.Label for o in Gui.Selection.getSelection()]
        except Exception:
            names = []
        if not names:
            text = translate("Nxt", "No selection")
        elif len(names) == 1:
            text = names[0]
        else:
            text = "%s · %d selected" % (", ".join(names[:2]), len(names))
        self._title.setText(text)

    # -- closing on a click elsewhere --

    def eventFilter(self, obj: QtCore.QObject,  # noqa: N802 - Qt API
                    event: QtCore.QEvent) -> bool:
        if (event.type() == QtCore.QEvent.Type.Resize
                and obj is self.parentWidget()):
            self._keep_inside()
        if (event.type() == QtCore.QEvent.Type.MouseButtonPress
                and not self.pinned
                and not (self._inspector_bridge is not None
                         and self._inspector_bridge.picking)
                and self._clicked_away(
                    obj, cast(QtGui.QMouseEvent, event)
                    .globalPosition().toPoint())):
            self.close_inspector()
        return False

    def _clicked_away(self, obj: QtCore.QObject,
                      where: QtCore.QPoint) -> bool:
        """Is this press outside the inspector and its popups?

        Judged by position: Qt re-delivers ignored presses to each parent.
        """
        if not isinstance(obj, QtWidgets.QWidget):
            return False
        if self.rect().contains(self.mapFromGlobal(where)):
            return False
        app = QtWidgets.QApplication
        if app.activePopupWidget() or app.activeModalWidget():
            return False
        return obj.window() is self.window()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(self.palette().color(QtGui.QPalette.ColorRole.Mid))
        painter.setBrush(self.palette().color(QtGui.QPalette.ColorRole.Window))
        painter.drawRoundedRect(QtCore.QRectF(self.rect()).adjusted(
            0.5, 0.5, -0.5, -0.5), INSPECTOR_RADIUS, INSPECTOR_RADIUS)


def _make_inspector(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """The QML page: Inspector.qml on its own QQuickWidget."""
    from ..app import services
    from ..ui import quick_host
    from ..ui.theme import Theme
    from . import bridge as inspector_bridge

    bridge = inspector_bridge.InspectorBridge(parent)
    theme = services.theme() or Theme(parent)
    view = quick_host.make_view(
        parent, "Inspector.qml",
        {"expressions": expressions.helper(), "inspector": bridge,
         "theme": theme})
    bridge.setParent(view)
    view.nxt_bridge = bridge  # type: ignore[attr-defined]
    view.nxt_lets_go = quick_host.LetsGo(view)  # type: ignore[attr-defined]
    return view


_inspector: PropertyInspector | None = None


def _instance() -> PropertyInspector | None:
    global _inspector
    mw = Gui.getMainWindow()
    if mw is None:
        return None
    if _inspector is None:
        _inspector = PropertyInspector(mw)
        _app().aboutToQuit.connect(close)
    return _inspector


def open_inspector(left: int | None = None, top: int | None = None) -> None:
    """Open the inspector with its top-left at global (`left`, `top`)."""
    inspector = _instance()
    if inspector is not None:
        inspector.open_at(left, top)


def close() -> None:
    """Return the editor and hide the inspector. Safe to call at any time."""
    if _inspector is not None:
        with contextlib.suppress(RuntimeError):
            _inspector.close_inspector()


def shutdown() -> None:
    """Close and destroy the inspector, before this module is reloaded."""
    global _inspector
    if _inspector is None:
        return
    with contextlib.suppress(RuntimeError):
        _inspector.close_inspector()
        _inspector.deleteLater()
    _inspector = None


def is_open() -> bool:
    return _inspector is not None and _inspector.isVisible()


def toggle() -> None:
    """Close the inspector, or open it beside the selected row."""
    if is_open():
        close()
        return
    from ..tree import panel
    bridge = panel.bridge() if panel.is_open() else None
    if bridge is not None:
        bridge.request_property_inspector()
    else:
        open_inspector()
