"""Session-lifetime features that run whether or not the panel is open.

They reach the panel only through signals; nothing here imports it.
"""

from __future__ import annotations

import contextlib
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from ..core import log
from ..core.qt import QtCore, QtWidgets

#: Events on the main window that mean the stylesheet or palette changed.
_RESTYLE = (QtCore.QEvent.Type.StyleChange,
            QtCore.QEvent.Type.PaletteChange,
            QtCore.QEvent.Type.ApplicationPaletteChange)


class Services(QtCore.QObject):
    """The application-lifetime half of Nxt."""

    #: (document, feature) opened for editing from outside the panel.
    featurePicked = QtCore.Signal(str, str)  # noqa: N815 - Qt API

    def __init__(self, main_window: QtWidgets.QWidget) -> None:
        super().__init__(main_window)
        self._main_window = main_window
        self._theme: Any = None
        self._double_click: Any = None
        self._floating: Any = None
        self._sketch_repair: Any = None
        self._sketch_attach: Any = None
        self._face_snap: Any = None
        self._space: Any = None
        self._isolation: Any = None
        self._isolation_observer: Any = None
        self._notice: Any = None
        self._toasts: Any = None
        self._escape: Any = None
        self._mass_bar: Any = None
        self._pending_edit: tuple[str, str] | None = None
        self._edit_timer = self._deferral(self._enter_pending_edit)
        self._restyle_timer = self._deferral(self._restyle)
        main_window.installEventFilter(self)

    def _deferral(self, slot: Any) -> QtCore.QTimer:
        timer = QtCore.QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(0)
        timer.timeout.connect(slot)
        return timer

    # -- lifecycle -- #

    def install(self) -> None:
        try:
            from ..tools.face_edit import DoubleClickEditor
            self._double_click = DoubleClickEditor(self)
            self._double_click.install()
        except Exception:
            log.error("could not install the 3D double-click editor")
            self._double_click = None
        try:
            from ..tools.float_input import FloatingInput
            self._floating = FloatingInput(self)
            self._floating.install()
        except Exception:
            log.error("could not install the floating value field")
            self._floating = None
        try:
            from ..tools.sketch_repair import SketchRepair
            self._sketch_repair = SketchRepair(self)
            self._sketch_repair.install()
        except Exception:
            log.error("could not install the sketch profile repair")
            self._sketch_repair = None
        try:
            from ..tools.sketch_attach import SketchAttach
            self._sketch_attach = SketchAttach(self)
            self._sketch_attach.install()
        except Exception:
            log.error("could not install the new sketch attachment")
            self._sketch_attach = None
        try:
            from ..tools.face_snap import FaceSnap
            self._face_snap = FaceSnap(self)
            self._face_snap.install()
        except Exception:
            log.error("could not install the face snapping")
            self._face_snap = None
        try:
            from ..tools.task_layout import TaskLayout
            self._task_layout: Any = TaskLayout(self)
            self._task_layout.install()
        except Exception:
            log.error("could not install the Pad and Pocket task layout")
            self._task_layout = None
        try:
            from ..tools.visibility import SpaceInView
            self._space = SpaceInView(self)
            self._space.install()
        except Exception:
            log.error("could not install Space in the 3D view")
            self._space = None
        try:
            from ..tools.drag_guard import StaleDragGuard
            self._drag_guard: Any = StaleDragGuard(self)
            self._drag_guard.install()
        except Exception:
            log.error("could not install the stale drag guard")
            self._drag_guard = None
        self.quick_mass_changed()

    def remove(self) -> None:
        self._remove_isolation()
        if self._mass_bar is not None:
            try:
                self._mass_bar.remove()
            except Exception:
                log.error("could not remove Quick Mass")
            self._mass_bar = None
        if self._toasts is not None:
            try:
                self._toasts.remove()
            except Exception:
                log.error("could not remove the undo toast")
            self._toasts = None
        self._edit_timer.stop()
        self._restyle_timer.stop()
        for part in (self._double_click, self._floating,
                     self._sketch_repair, self._sketch_attach,
                     self._face_snap, self._space,
                     getattr(self, "_task_layout", None),
                     getattr(self, "_drag_guard", None)):
            if part is not None:
                try:
                    part.remove()
                except Exception:
                    log.error("could not remove %s" % type(part).__name__)
        self._double_click = self._floating = None
        self._sketch_repair = self._sketch_attach = None
        self._face_snap = self._space = None
        self._task_layout = self._drag_guard = None
        with contextlib.suppress(RuntimeError):
            self._main_window.removeEventFilter(self)

    # -- isolate -- #

    def isolation(self) -> Any:
        """The isolate mode (isolate.py), with its 3D view notice."""
        if self._isolation is None:
            from ..tools import isolate
            from ..ui import isolate_notice
            self._isolation = isolate.Isolation(self)
            self._isolation_observer = isolate.Observer(self._isolation)
            try:
                App.addDocumentObserver(self._isolation_observer)
            except Exception:
                log.error("could not follow documents for isolate")
            try:
                self._notice = isolate_notice.ViewNotice(
                    self._isolation, self.theme(), self)
                self._notice.install()
            except Exception:
                log.error("could not set up the isolate notice")
                self._notice = None
            try:
                self._escape = isolate_notice.EscapeToExit(
                    self._isolation, self)
                self._escape.install()
            except Exception:
                log.error("could not set up Escape for isolate")
                self._escape = None
        return self._isolation

    def _remove_isolation(self) -> None:
        if self._isolation is None:
            return
        try:
            self._isolation.exit()
        except Exception:
            log.error("could not leave isolate")
        if self._notice is not None:
            try:
                self._notice.remove()
            except Exception:
                log.error("could not remove the isolate notice")
        if self._escape is not None:
            try:
                self._escape.remove()
            except Exception:
                log.error("could not remove Escape for isolate")
            self._escape = None
        with contextlib.suppress(Exception):
            App.removeDocumentObserver(self._isolation_observer)
        self._isolation = self._isolation_observer = self._notice = None

    # -- quick mass -- #

    def quick_mass_changed(self) -> None:
        """Show or hide Quick Mass (quick_mass.py) to match its setting."""
        from ..core import settings
        if self._mass_bar is None:
            if not settings.get("QuickMass"):
                return
            try:
                from ..ui import quick_mass
                self._mass_bar = quick_mass.MassBar(self.theme(), self)
                self._mass_bar.install()
            except Exception:
                log.error("could not set up Quick Mass")
                self._mass_bar = None
            return
        try:
            self._mass_bar.sync()
        except Exception:
            log.error("could not update Quick Mass")

    # -- undo toast -- #

    def toasts(self) -> Any:
        """The undo toast (toast.py), under the isolate notice if any."""
        if self._toasts is None:
            from ..ui import toast as toast_mod
            self._toasts = toast_mod.Toast(
                self.theme(), lambda: self._notice, self)
            self._toasts.install()
        return self._toasts

    # -- theme -- #

    def theme(self) -> Any:
        """Colours for what Nxt shows outside the panel."""
        if self._theme is None:
            from ..ui import theme as theme_mod
            self._theme = theme_mod.Theme(
                self, theme_mod.find_reference_widget(self._main_window))
        return self._theme

    def eventFilter(self, watched: Any, event: Any) -> bool:  # noqa: N802
        if event.type() in _RESTYLE and self._theme is not None:
            self._restyle_timer.start()
        return False

    def _restyle(self) -> None:
        if self._theme is None:
            return
        try:
            from ..ui import theme as theme_mod
            self._theme.set_reference(
                theme_mod.find_reference_widget(self._main_window))
        except Exception:
            log.error("could not refresh the colours")

    # -- editing -- #

    def edit_feature(self, doc_name: str, name: str) -> None:
        """Announce, then edit a feature, deferred out of the input event."""
        self.featurePicked.emit(doc_name, name)
        self._pending_edit = (doc_name, name)
        self._edit_timer.start()

    def _enter_pending_edit(self) -> None:
        pending, self._pending_edit = self._pending_edit, None
        if pending is not None:
            from ..tools import editing
            editing.open_for_edit(*pending)


_services: Services | None = None


def start() -> Services | None:
    """Start the services, once the main window exists. Idempotent."""
    global _services
    if _services is not None:
        return _services
    main_window = Gui.getMainWindow()
    if main_window is None:
        return None
    _services = Services(main_window)
    _services.install()
    return _services


def stop() -> None:
    """Take the services down, before their modules are reloaded."""
    global _services
    if _services is None:
        return
    with contextlib.suppress(RuntimeError):
        _services.remove()
        _services.deleteLater()
    _services = None


def instance() -> Services | None:
    return _services


def isolation() -> Any:
    """The isolate mode, or None while the services are not running."""
    return None if _services is None else _services.isolation()


def theme() -> Any:
    """The shared Theme, or None while the services are not running."""
    return None if _services is None else _services.theme()


def toast(doc: Any, message: str, after_undo: Any = None,
          undoable: bool = True, actions: Any = (),
          sticky: bool = False) -> None:
    """Say what Nxt just did to `doc`, with Undo, if the services run.

    `actions` are extra (label, callable) buttons.
    """
    if _services is not None:
        _services.toasts().show(doc, message, after_undo, undoable,
                                actions, sticky)
