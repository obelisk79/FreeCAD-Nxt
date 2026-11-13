"""Pad and Pocket's task dialogs, laid out by the inspector's template.

FreeCAD opens its own dialog whenever a feature is edited. The dialog
stays, for its preview and its OK and Cancel; its parameters box is
swapped, as it is filled, for the template's cards (TaskLayout.qml): the
Data tab only, with no "Everything else". Edits reach the dialog's fields
(task_sync.py), which OK writes back as usual.
"""

from __future__ import annotations

import contextlib
import traceback
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from ..core import widgets
from ..core.qt import QtCore, QtGui, QtWidgets
from ..inspector import bridge as inspector_bridge
from ..ui import quick_host
from ..ui import theme as theme_mod
from . import expressions
from .task_sync import SWAPPED

#: The dialog boxes replaced: FreeCAD's class for each feature's box.
REPLACED = frozenset({"TaskPadParameters", "TaskPocketParameters",
                      "TaskRevolutionParameters", "TaskLoftParameters",
                      "TaskPipeParameters"})
#: Further boxes of those dialogs, whose settings the cards also hold:
#: hidden, not replaced (a pipe's orientation and sections).
FOLDED = frozenset({"TaskPipeOrientation", "TaskPipeScaling"})
#: FreeCAD's task panel exists from startup, but is looked for until found.
FIND_MS = 500
#: After the swap: the dialog settles, then the view is drawn afresh.
RENEW_MS = (0, 120, 400)
#: What a dialog does on its way to being shown.
_FILLING = (QtCore.QEvent.Type.ChildAdded, QtCore.QEvent.Type.LayoutRequest,
            QtCore.QEvent.Type.Show, QtCore.QEvent.Type.Polish)


def _short(widget: Any) -> str:
    return widget.metaObject().className().split("::")[-1]


def _dialog_open() -> bool:
    try:
        return bool(Gui.Control.activeDialog())
    except Exception:
        return False


def _task_view() -> Any:
    main = Gui.getMainWindow()
    if main is None:
        return None
    for widget in main.findChildren(QtWidgets.QWidget):
        if widget.metaObject().className() == "Gui::TaskView::TaskView":
            return widget
    return None


class NativeChoices(QtCore.QObject):
    """A drop-down's list as a Qt menu: it may reach past the view."""

    def __init__(self, view: Any) -> None:
        super().__init__(view)
        self._view = view

    @QtCore.Slot(list, list, str, float, float, float, result=str)
    def choose(self, options: list[Any], labels: list[Any], current: str,
               x: float, y: float, width: float) -> str:
        menu = QtWidgets.QMenu(self._view)
        menu.setMinimumWidth(int(width))
        chosen: dict[Any, str] = {}
        for index, value in enumerate(options):
            label = labels[index] if index < len(labels) and labels[index] \
                else value
            action = menu.addAction(str(label))
            action.setCheckable(True)
            action.setChecked(str(value) == current)
            chosen[action] = str(value)
        picked = menu.exec(self._view.mapToGlobal(
            QtCore.QPoint(int(x), int(y))))
        menu.deleteLater()
        return chosen.get(picked, "")


class _Keyboard(QtCore.QObject):
    """A press in the view gives it the keyboard, as a field expects.

    In FreeCAD's overlay mode the panel floats over the 3D view, whose
    window keeps the keys unless the view's window is made active too, as
    the Nxt tree does (panel.takeKeyboard).
    """

    def __init__(self, view: Any) -> None:
        super().__init__(view)
        self._view = view
        view.installEventFilter(self)

    def eventFilter(self, _obj: Any, event: Any) -> bool:  # noqa: N802
        kind = event.type()
        if kind == QtCore.QEvent.Type.MouseButtonPress:
            with contextlib.suppress(RuntimeError):
                self._view.activateWindow()
                self._view.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
        elif kind == QtCore.QEvent.Type.FocusOut \
                and event.reason() in quick_host.LEAVING:
            # The view keeps its own focus item when the keyboard goes
            # elsewhere, and its focus ring stays lit: let it go.
            with contextlib.suppress(RuntimeError):
                quick_host.let_go(self._view)
        return False


class _Repaint(QtCore.QObject):
    """Repaint what holds the view after each frame it draws.

    In FreeCAD's overlay mode the task panel is drawn by its overlay,
    which does not notice the view's own frames: the cards changed, but
    showed their old picture until the window was redrawn.
    """

    def __init__(self, view: Any) -> None:
        super().__init__(view)
        self._view = view
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._repaint)
        # A QQuickWidget's scene draws offscreen: its window says when.
        view.quickWindow().afterRendering.connect(
            self._timer.start, QtCore.Qt.ConnectionType.QueuedConnection)

    def _repaint(self) -> None:
        widget = self._view
        while widgets.alive(widget):
            widget.update()
            if "Overlay" in widget.metaObject().className():
                break
            widget = widget.parentWidget()


class _OnShow(QtCore.QObject):
    """Calls `shown` after the watched widget is shown or reparented."""

    def __init__(self, widget: Any, shown: Any) -> None:
        super().__init__(widget)
        self._shown = shown
        widget.installEventFilter(self)

    def eventFilter(self, _obj: Any, event: Any) -> bool:  # noqa: N802
        if event.type() in (QtCore.QEvent.Type.Show,
                            QtCore.QEvent.Type.ParentChange):
            QtCore.QTimer.singleShot(0, self._shown)
        return False


class _Confirm(QtCore.QObject):
    """OK takes what is typed in the cards, as FreeCAD's own fields do.

    A field keeps its edit on Return or as it loses focus; OK's button
    takes no focus, so the cards are left first and their edit applied
    before the dialog writes its fields back.
    """

    def __init__(self, cards: Any, bridge: Any) -> None:
        super().__init__(cards)
        self._cards = cards
        self._bridge = bridge
        view = _task_view()
        boxes = (view.findChildren(QtWidgets.QDialogButtonBox)
                 if view is not None else [])
        for box in boxes:
            for button in box.buttons():
                if box.buttonRole(button) in (
                        QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole,
                        QtWidgets.QDialogButtonBox.ButtonRole.ApplyRole):
                    button.installEventFilter(self)

    def eventFilter(self, _obj: Any, event: Any) -> bool:  # noqa: N802
        if event.type() in (QtCore.QEvent.Type.MouseButtonPress,
                            QtCore.QEvent.Type.KeyPress):
            with contextlib.suppress(RuntimeError):
                root = self._cards.rootObject()
                if root is not None:
                    root.forceActiveFocus()     # the field keeps its edit
                self._bridge.apply_pending()
        return False


def tab_in_order(cards: Any) -> None:
    """Tab through the task panel in reading order, the cards included.

    Left to right, top to bottom: from the cards on to the dialog's own
    options and OK, not off to the rest of the window, which is where
    the focus chain leads from a view added after the dialog was built.
    """
    view = _task_view()
    if view is None or not widgets.alive(cards):
        return
    found = []
    for widget in view.findChildren(QtWidgets.QWidget):
        if widget is cards or (
                widget.isVisibleTo(view)
                and widget.focusPolicy() & QtCore.Qt.FocusPolicy.TabFocus
                and not cards.isAncestorOf(widget)):
            at = widget.mapTo(view, QtCore.QPoint(0, 0))
            found.append((at.y(), at.x(), widget))
    found.sort(key=lambda f: (f[0], f[1]))
    ordered = [w for _y, _x, w in found]
    for first, second in zip(ordered, ordered[1:]):
        QtWidgets.QWidget.setTabOrder(first, second)


def _discard(cards: Any, bridge: Any) -> None:
    with contextlib.suppress(RuntimeError):
        bridge.stop()
    if widgets.alive(cards):
        cards.hide()
        cards.setParent(None)
        cards.deleteLater()


def _with_choices(view: Any) -> None:
    view.rootContext().setContextProperty("nativeChoices",
                                          NativeChoices(view))


class TaskLayout(QtCore.QObject):
    """Watches FreeCAD's task panel and swaps the boxes it can lay out."""

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._view: Any = None
        self._busy = False
        self._find = QtCore.QTimer(self)
        self._find.setInterval(FIND_MS)
        self._find.timeout.connect(self._watch)
        self._later = QtCore.QTimer(self)
        self._later.setSingleShot(True)
        self._later.setInterval(0)
        self._later.timeout.connect(self._swap)

    def install(self) -> None:
        self._find.start()
        self._watch()

    def remove(self) -> None:
        self._find.stop()
        self._later.stop()
        if widgets.alive(self._view):
            self._view.removeEventFilter(self)
        self._view = None

    def _watch(self) -> None:
        if widgets.alive(self._view):
            return
        view = _task_view()
        if view is self._view:
            return
        if widgets.alive(self._view):
            self._view.removeEventFilter(self)
        self._view = view
        if view is not None:
            view.installEventFilter(self)
            self._swap()

    def eventFilter(self, watched: Any, event: Any) -> bool:  # noqa: N802
        # Never inside the event: FreeCAD's watcher update re-enters
        # itself if its panel is searched while it is being rebuilt.
        if watched is self._view and event.type() in _FILLING \
                and not self._busy:
            self._later.start()
        return False

    def _swap(self) -> None:
        """Each replaceable box, hidden, with the cards in its place."""
        view = self._view
        if not widgets.alive(view) or not _dialog_open():
            return
        self._busy = True
        try:
            for widget in view.findChildren(QtWidgets.QWidget):
                if _short(widget) in FOLDED:
                    widget.setProperty(SWAPPED, True)
                    if widget.isVisible():
                        widget.hide()
                    continue
                if _short(widget) not in REPLACED:
                    continue
                # The parameters class is the dialog's box itself (a
                # TaskBox): only it is hidden, never what holds it.
                box = widget
                if box.property(SWAPPED):
                    if box.isVisible():
                        box.hide()      # the dialog may show it again
                    continue
                box.setProperty(SWAPPED, True)
                self._replace(box)
        except Exception:
            App.Console.PrintError("Nxt: could not lay out the task\n")
            App.Console.PrintError(traceback.format_exc())
        finally:
            self._busy = False

    def _replace(self, box: Any) -> None:
        holder = box.parentWidget()
        layout = holder.layout() if holder is not None else None
        if layout is None:
            return
        bridge = inspector_bridge.InspectorBridge(task=True)
        cards = make_cards(holder, bridge)
        if isinstance(layout, QtWidgets.QBoxLayout):
            layout.insertWidget(layout.indexOf(box), cards)
        else:
            layout.addWidget(cards)
        box.hide()
        bridge.start()
        # Once laid out: positions decide the order.
        for delay in RENEW_MS:
            QtCore.QTimer.singleShot(delay, cards, lambda: tab_in_order(cards))
        confirm = _Confirm(cards, bridge)
        cards.nxt_confirm = confirm  # type: ignore[attr-defined]
        # The box goes with its dialog; what holds it stays for the next.
        box.destroyed.connect(lambda *_: _discard(cards, bridge))


def make_cards(holder: Any, bridge: Any) -> Any:
    """The template's cards for what `bridge` edits, sized to fit."""
    cards = fitted_view(
        holder, "TaskLayout.qml",
        {"expressions": expressions.helper(), "inspector": bridge,
         "nativeChoices": None},
        prepare=_with_choices)
    bridge.setParent(cards)
    return cards


def fitted_view(holder: Any, source: str, context: dict[str, Any],
                prepare: Any = None) -> Any:
    """A task panel's view of `source`, as tall as its QML asks to be."""
    from ..app import services
    reference = holder if holder is not None else Gui.getMainWindow()
    theme = services.theme() or theme_mod.Theme(
        reference, theme_mod.find_reference_widget(reference))
    cards = quick_host.make_view(
        holder, source, {"theme": theme, **context}, prepare=prepare)
    cards.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
    cards.nxt_keys = _Keyboard(cards)  # type: ignore[attr-defined]
    cards.nxt_paint = _Repaint(cards)  # type: ignore[attr-defined]
    cards.setClearColor(QtGui.QColor(theme.background))
    root = cards.rootObject()

    def fit() -> None:
        if widgets.alive(cards) and root is not None:
            cards.setFixedHeight(
                max(1, int(root.property("implicitHeight"))))

    def renew() -> None:
        """Resize the view once on screen, so it draws at its size.

        Made while the dialog is still being filled, the view keeps
        showing its first, half-sized frame (though it takes clicks)
        until it is resized, as a change of Sides does.
        """
        if not widgets.alive(cards) or root is None:
            return
        height = max(1, int(root.property("implicitHeight")))
        cards.setFixedHeight(height + 1)
        QtCore.QTimer.singleShot(0, cards, fit)

    # Never inside a frame: the height changes while the view renders,
    # and resizing it there starts a frame within the frame.
    root.implicitHeightChanged.connect(
        lambda: QtCore.QTimer.singleShot(0, cards, fit))
    fit()
    cards.nxt_shown = _OnShow(cards, renew)  # type: ignore[attr-defined]
    for delay in RENEW_MS:
        QtCore.QTimer.singleShot(delay, cards, renew)
    cards.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred,
                        QtWidgets.QSizePolicy.Policy.Fixed)
    return cards
