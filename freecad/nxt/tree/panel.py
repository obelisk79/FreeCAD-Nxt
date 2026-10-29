"""QDockWidget hosting the Nxt model panel beside the stock tree."""

from __future__ import annotations

import traceback
from collections.abc import Callable
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from .. import resources
from ..app.i18n import QT_TRANSLATE_NOOP, translate
from ..core import fc, qtquick
from ..core import settings as settings_mod
from ..core.qt import QtCompat, QtCore, QtGui, QtWidgets
from ..tools import expressions
from ..ui import prefs as prefs_mod
from ..ui import quick_host
from ..ui import theme as theme_mod
from . import bridge as bridge_mod
from . import icons as icons_mod
from . import observers as observers_mod

OBJECT_NAME = "NxtModelPanel"
TITLE = QT_TRANSLATE_NOOP("Nxt", "Model (Nxt)")

#: Events that mean "you may have been moved into, or out of, an overlay".
_REPARENT_EVENTS = (
    QtCore.QEvent.Type.ParentChange,
    QtCore.QEvent.Type.Show,
    QtCore.QEvent.Type.Hide,
    QtCore.QEvent.Type.Move,
    QtCore.QEvent.Type.Resize,
)

#: Events that mean "the colours under you just changed".
_RESTYLE_EVENTS = (
    QtCore.QEvent.Type.StyleChange,
    QtCore.QEvent.Type.PaletteChange,
    QtCore.QEvent.Type.ApplicationPaletteChange,
)

SAVE_DEBOUNCE_MS = 400
LATE_REPAINT_MS = 180
OVERLAY_VERIFY_MS = 1200
OVERLAY_REQUEST_MS = 600
OVERLAY_RETRY_MS = 1500
OVERLAY_ATTEMPTS = 2
DETECT_SETTLE_MS = 250

#: The stock tree (colour source) may not exist yet at startup.
THEME_RETRY_MS = (400, 1500, 4000)

#: How far up the parent chain to look for FreeCAD's overlay container.
_ANCESTOR_LIMIT = 12

#: Acts on the dock under the cursor, i.e. ours when our button is clicked.
HOST_OVERLAY_COMMAND = "Std_DockOverlayToggle"

_panel: ModelPanel | None = None


_DOCK_AREAS = (
    QtCore.Qt.DockWidgetArea.LeftDockWidgetArea,
    QtCore.Qt.DockWidgetArea.RightDockWidgetArea,
    QtCore.Qt.DockWidgetArea.TopDockWidgetArea,
    QtCore.Qt.DockWidgetArea.BottomDockWidgetArea,
)


def _dock_area(stored: Any) -> QtCore.Qt.DockWidgetArea:
    """Stored number to dock area; anything unexpected maps to left."""
    try:
        area = QtCore.Qt.DockWidgetArea(int(stored))
    except Exception:
        return QtCore.Qt.DockWidgetArea.LeftDockWidgetArea
    if area not in _DOCK_AREAS:
        return QtCore.Qt.DockWidgetArea.LeftDockWidgetArea
    return area


def _err_overlay() -> None:
    App.Console.PrintError("Nxt: FreeCAD's overlay command failed\n")
    App.Console.PrintError(traceback.format_exc())


def _overlay_icon(size: int, floating: bool,
                  colour: QtGui.QColor) -> QtGui.QIcon:
    """Draw the overlay button's icon (drawn so it scales cleanly)."""
    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
    pen = QtGui.QPen(colour)
    pen.setWidthF(max(1.0, size * 0.08))
    painter.setPen(pen)

    inset = size * 0.14
    painter.drawRoundedRect(
        QtCore.QRectF(inset, inset, size - 2 * inset, size - 2 * inset),
        size * 0.12, size * 0.12)

    panel = QtCore.QRectF(size * 0.30, size * 0.34,
                          size * 0.46, size * 0.22)
    if floating:
        painter.setBrush(QtGui.QBrush(colour))
    painter.drawRoundedRect(panel, size * 0.08, size * 0.08)
    painter.end()
    return QtGui.QIcon(pixmap)


class PanelTitleBar(QtWidgets.QWidget):
    """Dock title bar with an overlay button.

    Replacing the title bar loses the stock float and close buttons, so
    they are rebuilt here.
    """

    def __init__(self, dock: ModelPanel) -> None:
        super().__init__(dock)
        self._dock = dock

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 2, 2)
        layout.setSpacing(1)

        self._logo = QtWidgets.QLabel(self)
        logo = QtGui.QIcon(str(resources.LOGO))
        side = self.fontMetrics().height()
        self._logo.setPixmap(logo.pixmap(side, side))
        layout.addWidget(self._logo)
        layout.addSpacing(4)
        dock.setWindowIcon(logo)

        self._label = QtWidgets.QLabel(dock.windowTitle(), self)
        font = self._label.font()
        font.setBold(True)
        self._label.setFont(font)
        layout.addWidget(self._label)
        layout.addStretch(1)

        self._overlay = self._button(
            translate("Nxt", "Activate overlay mode over the 3D view"))
        self._overlay.setCheckable(True)
        self._overlay.clicked.connect(self._on_overlay_clicked)
        layout.addWidget(self._overlay)

        style = self.style()
        self._float = self._button(translate("Nxt", "Float the panel"))
        self._float.setIcon(style.standardIcon(
            QtWidgets.QStyle.StandardPixmap.SP_TitleBarNormalButton))
        self._float.clicked.connect(
            lambda: dock.setFloating(not dock.isFloating()))
        layout.addWidget(self._float)

        self._close = self._button(translate("Nxt", "Close the panel"))
        self._close.setIcon(style.standardIcon(
            QtWidgets.QStyle.StandardPixmap.SP_TitleBarCloseButton))
        self._close.clicked.connect(dock.close)
        layout.addWidget(self._close)

        self.refresh()

    def _on_overlay_clicked(self) -> None:
        """Ask FreeCAD to overlay the dock; detection switches painting."""
        if settings_mod.get("OverlayMode") == "nxt":
            self._dock.set_view_overlay(True)
        elif not self._dock.request_host_overlay():
            self._dock.toggle_overlay()
        self.refresh()

    def _button(self, tip: str) -> QtWidgets.QToolButton:
        button = QtWidgets.QToolButton(self)
        button.setAutoRaise(True)
        button.setToolTip(tip)
        button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        return button

    def refresh(self) -> None:
        palette = self._label.palette()
        colour = palette.color(QtGui.QPalette.ColorRole.WindowText)
        size = max(12, self._label.fontMetrics().height())
        on = self._dock.overlay()
        self._overlay.setIcon(_overlay_icon(size, on, colour))
        self._overlay.setChecked(on)
        self._label.setText(self._dock.windowTitle())


class ModelPanel(QtWidgets.QDockWidget):

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(translate("Nxt", TITLE), parent)
        self.setObjectName(OBJECT_NAME)

        # QML calls back into these while loading, so set before setWidget.
        self._view: Any = None     # QQuickWidget; the module loads lazily
        self._provider: icons_mod.IconProvider | None = None
        self._title_bar: PanelTitleBar | None = None
        self._hidden_title: QtWidgets.QWidget | None = None
        self._detected_overlay = False
        self._wants_host_overlay = False
        self._host_overlay_attempts = 0
        self._restoring = True   # suppress writes while applying saved state
        self._view_overlay: Any = None   # Nxt's own overlay, when used
        self._wants_view_overlay = False

        # Owned timers: a static singleShot outlives the dock on reload.
        self._save_timer = self._timer(SAVE_DEBOUNCE_MS, self._flush_save)
        self._repaint_timer = self._timer(0, self._flush_repaint)
        self._repaint_late_timer = self._timer(
            LATE_REPAINT_MS, self._flush_repaint)
        self._detect_timer = self._timer(0, self._sync_overlay_detection)
        self._detect_late_timer = self._timer(
            DETECT_SETTLE_MS, self._sync_overlay_detection)
        self._restyle_timer = self._timer(0, self.refresh_theme)
        self._verify_timer = self._timer(
            OVERLAY_VERIFY_MS, self._verify_host_overlay)
        self._release_timer = self._timer(0, self._release_scenegraph)
        self._host_overlay_timer = self._timer(
            OVERLAY_REQUEST_MS, self.restore_host_overlay)

        self._theme = theme_mod.Theme(
            self, theme_mod.find_reference_widget(parent))
        self._bridge = bridge_mod.TreeBridge(self)
        self._prefs = prefs_mod.Preferences(self)
        self._observers = observers_mod.Observers(self._bridge)

        self.setWidget(self._build_body())
        self._observers.install()
        # Deferred: parameter observers run inside whatever set the value.
        self._background_watch = theme_mod.ViewBackgroundWatch(
            self._restyle_timer.start)
        self._background_watch.attach()

        self._title_bar = PanelTitleBar(self)
        self.setTitleBarWidget(
                self._title_bar)  # type: ignore[arg-type]
        self._hidden_title = QtWidgets.QWidget(self)

        # The host overlay is detected from reparenting; see eventFilter.
        self.installEventFilter(self)

    def _timer(self, interval: int,
               slot: Callable[[], object]) -> QtCore.QTimer:
        timer = QtCore.QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(interval)
        timer.timeout.connect(slot)
        return timer

    def _build_body(self) -> QtWidgets.QWidget:
        if not qtquick.available():
            return self._failure(
                translate("Nxt",
                          "QtQuick is not available in this FreeCAD's Qt "
                          "packaging.\nThe panel needs "
                          "PySide6.QtQuickWidgets."))
        try:
            view = quick_host.make_view(
                self, "NxtTree.qml",
                {"expressions": expressions.helper(), "nxt": self._bridge,
                 "theme": self._theme, "host": self, "prefs": self._prefs,
                 "isolation": self._isolation()},
                prepare=self._prepare_view)
        except quick_host.QmlLoadError as exc:
            App.Console.PrintError("Nxt: %s\n" % exc)
            return self._failure(str(exc))
        except Exception:
            return self._failure(traceback.format_exc())

        self._view = view
        return view

    def _prepare_view(self, view: Any) -> None:
        self._apply_clear_colour(view)
        self._provider = icons_mod.IconProvider()
        view.engine().addImageProvider(icons_mod.PROVIDER_ID, self._provider)

    def _isolation(self) -> Any:
        """The services' isolation, or an idle one so the QML binds."""
        from ..app import services
        from ..tools import isolate
        live = services.isolation()
        return live if live is not None else isolate.Isolation(self)

    def _failure(self, detail: str) -> QtWidgets.QWidget:
        holder = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(holder)
        label = QtWidgets.QLabel(
            translate("Nxt", "The Nxt model panel could not start."), holder)
        label.setWordWrap(True)
        detail_box = QtWidgets.QPlainTextEdit(detail, holder)
        detail_box.setReadOnly(True)
        layout.addWidget(label)
        layout.addWidget(detail_box, 1)
        return holder

    def _apply_clear_colour(self, view: Any = None) -> None:
        """Make the QML surface transparent in overlay mode.

        The widget attributes must agree with the clear colour, or the
        scene graph composites over black.
        """
        view = view or self._view
        if view is None:
            return
        overlay = self._theme.overlay
        view.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground,
                          overlay)
        view.setAttribute(QtCore.Qt.WidgetAttribute.WA_AlwaysStackOnTop,
                          overlay)
        view.setClearColor(QtGui.QColor(0, 0, 0, 0) if overlay
                           else self._theme.background)

    def set_overlay(self, on: bool) -> None:
        """Switch overlay painting; the dock placement is left alone."""
        self._theme.set_overlay(on)
        self._apply_clear_colour()
        self._sync_title_bar()
        self.repaintBehind()
        self.save_state()

    def overlay(self) -> bool:
        return bool(self._theme.overlay)

    def toggle_overlay(self) -> None:
        if self.in_view_overlay():
            self.set_view_overlay(False)
        elif settings_mod.get("OverlayMode") == "nxt":
            self.set_view_overlay(not self.overlay())
        else:
            self.set_overlay(not self.overlay())

    viewOverlayChanged = QtCore.Signal()

    @QtCore.Property(bool, notify=viewOverlayChanged)
    def viewOverlay(self) -> bool:  # noqa: N802 - QML API
        """Whether the panel is inside the 3D view, passing clicks on."""
        return self.in_view_overlay()

    def in_view_overlay(self) -> bool:
        return self._view_overlay is not None \
            and self._view_overlay.attached()

    def set_view_overlay(self, on: bool) -> None:
        """Into the 3D view as Nxt's own overlay, or back into the dock."""
        if on == self.in_view_overlay():
            return
        from . import view_overlay
        if on:
            if self._view_overlay is None:
                self._view_overlay = view_overlay.ViewOverlay(self)
            self._theme.set_overlay(True)
            self._apply_clear_colour()
            if not self._view_overlay.attach():
                self._theme.set_overlay(False)
                self._apply_clear_colour()
                return
        else:
            if self._view_overlay is not None:
                self._view_overlay.detach()
            self._theme.set_overlay(False)
            self._apply_clear_colour()
        self._sync_title_bar()
        self.viewOverlayChanged.emit()
        self.save_state()

    @QtCore.Slot()
    def leaveViewOverlay(self) -> None:  # noqa: N802 - QML API
        """Return to the dock, deferred past the press that asked."""
        QtCore.QTimer.singleShot(0, lambda: self.set_view_overlay(False))

    def apply_overlay_mode(self) -> None:
        """The OverlayMode setting changed: leave ours if it is off."""
        if self.in_view_overlay() \
                and settings_mod.get("OverlayMode") != "nxt":
            self.set_view_overlay(False)

    def _in_host_overlay(self) -> bool:
        """Whether FreeCAD's overlay manager has reparented this dock.

        There is no API for this, so it is a class-name heuristic.
        """
        widget = self.parentWidget()
        for _step in range(_ANCESTOR_LIMIT):
            if widget is None:
                return False
            try:
                if "Overlay" in widget.metaObject().className():
                    return True
            except Exception:
                return False
            widget = widget.parentWidget()
        return False

    def request_host_overlay(self) -> bool:
        """Run FreeCAD's overlay command on this dock. False if unavailable."""
        try:
            if HOST_OVERLAY_COMMAND not in fc.list_commands():
                return False
        except Exception:
            return False
        try:
            Gui.runCommand(HOST_OVERLAY_COMMAND)
        except Exception:
            _err_overlay()
            return False
        self._detect_timer.start()
        self._detect_late_timer.start()
        return True

    def _sync_overlay_detection(self) -> None:
        detected = self._in_host_overlay()
        if detected == self._detected_overlay:
            return
        self._detected_overlay = detected
        self.set_overlay(detected)

    def _sync_title_bar(self) -> None:
        """Hide the title bar only while FreeCAD's overlay hosts the dock."""
        if self._detected_overlay:
            self.setTitleBarWidget(
                self._hidden_title)  # type: ignore[arg-type]
        else:
            self.setTitleBarWidget(
                self._title_bar)  # type: ignore[arg-type]
            self._title_bar.refresh()  # type: ignore[union-attr]

    def eventFilter(self, obj: QtCore.QObject,
                    event: QtCore.QEvent) -> bool:
        if obj is self and event.type() in _REPARENT_EVENTS:
            self._detect_timer.start()
            self.save_state()
        if obj is self and event.type() == QtCore.QEvent.Type.ParentChange:
            self._release_timer.start()
        return super().eventFilter(obj, event)

    def apply_saved_state(self, main_window: Any) -> None:
        """Replay saved float and overlay state Qt cannot restore itself."""
        self._restoring = True
        try:
            if settings_mod.get("Floating"):
                self.setFloating(True)
                width = settings_mod.get("FloatWidth")
                height = settings_mod.get("FloatHeight")
                if width > 0 and height > 0:
                    self.setGeometry(settings_mod.get("FloatX"),
                                     settings_mod.get("FloatY"),
                                     width, height)
            # Host overlay waits until the dock is visible and active.
            self._wants_host_overlay = bool(settings_mod.get("HostOverlay"))
            self._wants_view_overlay = bool(
                settings_mod.get("ViewOverlay")
                and settings_mod.get("OverlayMode") == "nxt")
            if self._wants_view_overlay:
                self._wants_host_overlay = False
            elif not self._wants_host_overlay and settings_mod.get("Overlay"):
                self.set_overlay(True)
        finally:
            self._restoring = False

    def restore_view_overlay(self) -> None:
        """Re-enter the 3D view overlay if the last session ended there."""
        if self._wants_view_overlay:
            self._wants_view_overlay = False
            QtCore.QTimer.singleShot(
                0, lambda: self.set_view_overlay(True))

    def schedule_host_overlay(self) -> None:
        if self._wants_host_overlay:
            self._host_overlay_attempts = 0
            self._host_overlay_timer.setInterval(OVERLAY_REQUEST_MS)
            self._host_overlay_timer.start()

    def restore_host_overlay(self) -> None:
        """Ask FreeCAD to overlay this dock, now that it is on screen."""
        self._wants_host_overlay = False
        self._host_overlay_attempts += 1
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)
        if not self.request_host_overlay():
            return
        self._verify_timer.start()

    def _verify_host_overlay(self) -> None:
        if self._detected_overlay:
            return
        # Early in a session the window is still settling; retry once.
        if self._host_overlay_attempts < OVERLAY_ATTEMPTS:
            self._host_overlay_timer.setInterval(OVERLAY_RETRY_MS)
            self._host_overlay_timer.start()
            return
        if self.overlay():
            self.set_overlay(False)
        App.Console.PrintMessage(
            "Nxt: the panel was overlaid last session, but %s did not land "
            "on it. Use the title bar button to overlay it again, and run "
            "'from freecad.nxt.diagnostics import probe; probe.overlay()' "
            "to show what "
            "this build offers for aiming it.\n" % HOST_OVERLAY_COMMAND)

    def save_state(self) -> None:
        """Schedule a debounced save of the dock state."""
        if self._restoring:
            return
        self._save_timer.start()

    def _flush_save(self) -> None:
        try:
            # In Nxt's overlay the dock is hidden but the panel is showing.
            settings_mod.put("Visible", self.isVisible()
                             or self.in_view_overlay())
            settings_mod.put("ViewOverlay", self.in_view_overlay())
            settings_mod.put("Floating", self.isFloating())
            settings_mod.put("Overlay", self.overlay())
            settings_mod.put("HostOverlay", self._detected_overlay)
            if self.isFloating():
                rect = self.geometry()
                settings_mod.put("FloatX", rect.x())
                settings_mod.put("FloatY", rect.y())
                settings_mod.put("FloatWidth", rect.width())
                settings_mod.put("FloatHeight", rect.height())
            else:
                parent = self.parentWidget()
                area = getattr(parent, "dockWidgetArea", None)
                if callable(area):
                    settings_mod.put("DockArea", QtCompat.enum_int(area(self)))
        except Exception:
            App.Console.PrintError("Nxt: could not save panel state\n")
            App.Console.PrintError(traceback.format_exc())

    def _release_scenegraph(self) -> None:
        """Drop scene graph resources after a reparent.

        A new top-level window means a new QRhi; old textures are invalid.
        """
        view = self._view
        if view is None:
            return
        try:
            window = view.quickWindow()
            if window is not None:
                window.releaseResources()
            view.update()
        except Exception:
            pass

    @QtCore.Slot(result=QtCore.QPointF)
    def menuAnchorOffset(self) -> QtCore.QPointF:  # noqa: N802 - QML API
        """Offset of the panel's scene in FreeCAD's window (Wayland only).

        Wayland places popups relative to the QQuickWidget's offscreen
        window, so menus must be shifted; elsewhere this is zero.
        """
        return quick_host.window_offset(self._view)

    @QtCore.Slot(result=QtCore.QRectF)
    def menuRoom(self) -> QtCore.QRectF:  # noqa: N802 - QML API
        """The panel's corner in FreeCAD's window, and the window's size."""
        return quick_host.room_in_window(self._view)

    @QtCore.Slot()
    def takeKeyboard(self) -> None:  # noqa: N802 - QML API
        """Give the view keyboard focus before a field starts editing.

        In the 3D view overlay the keys otherwise go to the view.
        """
        view = self._view
        if view is None:
            return
        try:
            view.activateWindow()
            view.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)
        except RuntimeError:
            pass

    @QtCore.Slot()
    def repaintBehind(self) -> None:
        """Repaint what is under the panel, coalesced.

        A translucent QQuickWidget does not make what is behind it redraw.
        The later pass catches animated relayouts.
        """
        if not self._theme.overlay:
            return
        self._repaint_timer.start()
        self._repaint_late_timer.start()

    def _flush_repaint(self) -> None:
        if self._view is not None:
            self._view.update()
        parent = self.parentWidget()
        if parent is not None:
            parent.update()
        self.update()

    def adopt_reference(self, widget: QtWidgets.QWidget | None) -> None:
        """Take colours from a better reference widget, if one appeared."""
        if widget is None or widget is self._theme.reference():
            return
        self._theme.set_reference(widget)
        self._apply_clear_colour()
        if self._title_bar is not None:
            self._title_bar.refresh()

    def refresh_theme(self) -> None:
        if self._theme.reference() is None:
            self._theme.set_reference(
                theme_mod.find_reference_widget(self.parentWidget()))
        else:
            self._theme.refresh()
        self._apply_clear_colour()
        if self._title_bar is not None:
            self._title_bar.refresh()

    def changeEvent(self, event: QtCore.QEvent) -> None:
        super().changeEvent(event)
        if getattr(self, "_restyle_timer", None) is None:
            return          # still constructing; refresh_theme runs anyway
        if event.type() in _RESTYLE_EVENTS:
            # Deferred: we may be polished before our colour reference.
            self._restyle_timer.start()

    def shutdown(self) -> None:
        """Tear the panel down by deleting the view.

        Never null the context properties: bindings would fire against null.
        """
        if self.in_view_overlay():
            try:
                self._view_overlay.detach()
            except Exception:
                App.Console.PrintError("Nxt: view overlay detach failed\n")
        for timer in (self._save_timer, self._repaint_timer,
                      self._repaint_late_timer, self._detect_timer,
                      self._detect_late_timer, self._restyle_timer,
                      self._verify_timer, self._release_timer,
                      self._host_overlay_timer):
            try:
                timer.stop()
            except Exception:
                pass

        self._background_watch.detach()
        try:
            self._observers.remove()
        except Exception:
            App.Console.PrintError("Nxt: observer removal failed\n")

        view, self._view = self._view, None
        self._provider = None
        if view is not None:
            try:
                self.setWidget(None)  # type: ignore[arg-type]
                view.setParent(None)
                view.deleteLater()
            except Exception:
                App.Console.PrintError("Nxt: view teardown failed\n")
                App.Console.PrintError(traceback.format_exc())
        else:
            self.setWidget(None)  # type: ignore[arg-type]

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        # Saved now: on quit there may be no further event loop turn.
        self._save_timer.stop()
        # In Nxt's overlay a close means FreeCAD is quitting.
        if not self.in_view_overlay():
            settings_mod.put("Visible", False)
        super().closeEvent(event)


def _teardown() -> None:
    global _panel
    if _panel is None:
        return
    try:
        _panel.shutdown()
        _panel.setParent(None)
        _panel.deleteLater()
    except Exception:
        App.Console.PrintError("Nxt: panel teardown failed\n")
        App.Console.PrintError(traceback.format_exc())
    _panel = None


def _on_quit() -> None:
    """Destroy the QML view before what it binds to, on quit."""
    panel = _panel
    if panel is None:
        return
    try:
        view, panel._view = panel._view, None
        if view is None:
            return
        view.hide()
        view.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(
            view, QtCompat.enum_int(QtCore.QEvent.Type.DeferredDelete))
    except RuntimeError:
        pass                    # already destroyed with the main window


def show() -> ModelPanel | None:
    """Create the dock if needed, tab it beside the stock tree, raise it."""
    global _panel
    mw = Gui.getMainWindow()
    if mw is None:
        return None

    if _panel is None:
        _panel = ModelPanel(mw)
        app = QtCore.QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(_on_quit)
        first_run = not settings_mod.get("Configured")

        existing: QtWidgets.QDockWidget | None = None
        if first_run:
            for dock in mw.findChildren(QtWidgets.QDockWidget):
                if dock is _panel:
                    continue
                name = dock.objectName() or ""
                if name in ("Model", "Combo View", "ComboView", "Tree view"):
                    existing = dock
                    break

        # The window layout is read before this dock exists; Qt keeps its
        # place for restoreDockWidget.
        if existing is not None or not mw.restoreDockWidget(_panel):
            if existing is not None:
                area = mw.dockWidgetArea(existing)
            else:
                area = _dock_area(settings_mod.get("DockArea"))
            mw.addDockWidget(area, _panel)

            # First run only, so the user's arrangement is not undone.
            if existing is not None:
                mw.tabifyDockWidget(existing, _panel)
                settings_mod.put("Configured", True)

        _panel.apply_saved_state(mw)

    _panel.show()
    _panel.raise_()
    _panel.refresh_theme()
    _panel.schedule_host_overlay()
    _panel.restore_view_overlay()
    settings_mod.put("Visible", True)

    for delay in THEME_RETRY_MS:
        QtCore.QTimer.singleShot(delay, _upgrade_theme_reference)
    return _panel


def _upgrade_theme_reference() -> None:
    if _panel is None:
        return
    try:
        widget = theme_mod.find_reference_widget(_panel.parentWidget())
        if widget is not None:
            _panel.adopt_reference(widget)
    except Exception:
        pass


def theme() -> Any:
    """The panel's live Theme, or None, for the inspector's colours."""
    return None if _panel is None else _panel._theme


def bridge() -> bridge_mod.TreeBridge | None:
    """The live TreeBridge, or None. For `probe` and the console."""
    return None if _panel is None else _panel._bridge


def restore() -> None:
    """Bring the panel back as the user left it. Called once at startup."""
    try:
        if settings_mod.get("Visible"):
            show()
    except Exception:
        App.Console.PrintError("Nxt: could not restore the panel\n")
        App.Console.PrintError(traceback.format_exc())


def hide() -> None:
    if _panel is not None:
        _panel.hide()


def close() -> None:
    _teardown()


def set_overlay(on: bool) -> None:
    if _panel is not None:
        _panel.set_overlay(on)


def toggle_overlay() -> None:
    if _panel is not None:
        _panel.set_overlay(not _panel.overlay())


def toggle() -> None:
    if _panel is None or not _panel.isVisible():
        show()
    else:
        hide()


def is_open() -> bool:
    return _panel is not None


def instance() -> ModelPanel | None:
    return _panel
