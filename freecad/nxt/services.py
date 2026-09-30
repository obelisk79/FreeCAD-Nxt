"""What Nxt does outside the model panel, running whether or not it is open.

The 3D double-click editor, the floating value field and the Property
Inspector's colours used to live on the panel, so closing the panel
switched them off. They belong to the application instead: this starts
them once the main window exists and keeps them for the session.

They still talk to the panel when it is there, through signals rather
than references: a face double-clicked here emits `featurePicked`, and an
open panel reveals the row - exactly as before. Nothing here imports the
panel.

    from freecad.nxt import services
    services.instance()        # the live Services, or None
"""

from __future__ import annotations

import traceback
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from .qt import QtCore, QtWidgets

#: Events on the main window that mean the stylesheet or palette changed.
_RESTYLE = (QtCore.QEvent.Type.StyleChange,
            QtCore.QEvent.Type.PaletteChange,
            QtCore.QEvent.Type.ApplicationPaletteChange)


def _err(message: str) -> None:
    App.Console.PrintError("Nxt: %s\n" % message)
    App.Console.PrintError(traceback.format_exc())


class Services(QtCore.QObject):
    """The application-lifetime half of Nxt."""

    #: A feature was opened for editing from outside the panel (a face
    #: double-clicked): (document, feature). The panel reveals its row.
    featurePicked = QtCore.Signal(str, str)  # noqa: N815 - Qt API

    def __init__(self, main_window: QtWidgets.QWidget) -> None:
        super().__init__(main_window)
        self._main_window = main_window
        self._theme: Any = None
        self._double_click: Any = None
        self._floating: Any = None
        self._isolation: Any = None
        self._isolation_observer: Any = None
        self._notice: Any = None
        self._escape: Any = None
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

    # -- lifecycle ---------------------------------------------------------- #

    def install(self) -> None:
        try:
            from .tree.face_edit import DoubleClickEditor
            self._double_click = DoubleClickEditor(self)
            self._double_click.install()
        except Exception:
            _err("could not install the 3D double-click editor")
            self._double_click = None
        try:
            from .tree.float_input import FloatingInput
            self._floating = FloatingInput(self)
            self._floating.install()
        except Exception:
            _err("could not install the floating value field")
            self._floating = None

    def remove(self) -> None:
        self._remove_isolation()
        self._edit_timer.stop()
        self._restyle_timer.stop()
        for part in (self._double_click, self._floating):
            if part is not None:
                try:
                    part.remove()
                except Exception:
                    _err("could not remove %s" % type(part).__name__)
        self._double_click = self._floating = None
        try:
            self._main_window.removeEventFilter(self)
        except RuntimeError:
            pass

    # -- isolate ------------------------------------------------------------ #

    def isolation(self) -> Any:
        """The isolate mode (isolate.py), with its 3D view notice."""
        if self._isolation is None:
            from . import isolate, isolate_notice
            self._isolation = isolate.Isolation(self)
            self._isolation_observer = isolate.Observer(self._isolation)
            try:
                App.addDocumentObserver(self._isolation_observer)
            except Exception:
                _err("could not follow documents for isolate")
            try:
                self._notice = isolate_notice.ViewNotice(
                    self._isolation, self.theme(), self)
                self._notice.install()
            except Exception:
                _err("could not set up the isolate notice")
                self._notice = None
            try:
                self._escape = isolate_notice.EscapeToExit(
                    self._isolation, self)
                self._escape.install()
            except Exception:
                _err("could not set up Escape for isolate")
                self._escape = None
        return self._isolation

    def _remove_isolation(self) -> None:
        if self._isolation is None:
            return
        try:
            self._isolation.exit()
        except Exception:
            _err("could not leave isolate")
        if self._notice is not None:
            try:
                self._notice.remove()
            except Exception:
                _err("could not remove the isolate notice")
        if self._escape is not None:
            try:
                self._escape.remove()
            except Exception:
                _err("could not remove Escape for isolate")
            self._escape = None
        try:
            App.removeDocumentObserver(self._isolation_observer)
        except Exception:
            pass
        self._isolation = self._isolation_observer = self._notice = None

    # -- theme -------------------------------------------------------------- #

    def theme(self) -> Any:
        """The colours of anything Nxt shows outside the panel.

        Made on first use and read from the application's stylesheet, like
        the panel's own, so the two agree without either owning the other.
        """
        if self._theme is None:
            from .tree import theme as theme_mod
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
            from .tree import theme as theme_mod
            self._theme.set_reference(
                theme_mod.find_reference_widget(self._main_window))
        except Exception:
            _err("could not refresh the colours")

    # -- editing ------------------------------------------------------------ #

    def edit_feature(self, doc_name: str, name: str) -> None:
        """Open a feature for editing from outside the panel.

        Announced first, so an open panel marks and reveals the row as a
        pick does; then edited, deferred, because this is reached from
        inside an input event.
        """
        self.featurePicked.emit(doc_name, name)
        self._pending_edit = (doc_name, name)
        self._edit_timer.start()

    def _enter_pending_edit(self) -> None:
        pending, self._pending_edit = self._pending_edit, None
        if pending is not None:
            from .tree import editing
            editing.enter_edit(*pending)


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
    try:
        _services.remove()
        _services.deleteLater()
    except RuntimeError:
        pass                    # the main window already took it down
    _services = None


def instance() -> Services | None:
    return _services


def isolation() -> Any:
    """The isolate mode, or None while the services are not running."""
    return None if _services is None else _services.isolation()


def theme() -> Any:
    """The shared Theme, or None while the services are not running."""
    return None if _services is None else _services.theme()
