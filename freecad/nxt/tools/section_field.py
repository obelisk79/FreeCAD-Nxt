"""The section plane's offset as a value field beside its arrow.

The same box as a feature's floating fields (FloatingValue.qml), bound
to the section instead of a task panel: type a length, roll the wheel,
or "=" for an expression.
"""

from __future__ import annotations

from typing import Any

import FreeCAD as App

from ..app.i18n import translate
from ..core import units, view3d, widgets
from ..core.qt import QtCore
from ..ui import quick_host
from . import expressions, placement
from .float_input import Field

#: One wheel notch, in mm.
STEP = 1.0
#: The box sits this far right of and below its arrow tip, in pixels.
NUDGE = (14, 6)


def length_text(value: float) -> str:
    """A length as FreeCAD shows it, in the user's units."""
    try:
        return str(App.Units.Quantity(value, App.Units.Length).UserString)
    except Exception:
        return "%g mm" % value


class OffsetField(Field):
    """The section's offset, as the floating box reads and sets it."""

    def __init__(self, section: Any) -> None:
        super().__init__()
        self._section = section
        self._label = translate("Nxt", "Offset")

    def sync(self) -> None:
        """The offset, or while an arc is dragged, the tilt so far."""
        tilt = self._section.tilt_degrees
        label = translate("Nxt", "Offset" if tilt is None else "Tilt")
        text = (length_text(self._section.offset) if tilt is None
                else "%g °" % tilt)
        if label != self._label:
            self._label = label
            self.labelChanged.emit()
        if text != self._text:
            self._text = text
            self.textChanged.emit()

    def _type(self, text: str) -> bool:
        source = text.strip()
        if source.startswith("="):
            # Any object can evaluate an expression naming others.
            doc: Any = App.ActiveDocument
            owner: Any = (doc.Objects[0] if doc is not None and doc.Objects
                          else None)
            try:
                value = owner.evalExpression(
                    expressions.strip_marker(source))
                value = float(getattr(value, "Value", value))
            except Exception as exc:
                App.Console.PrintWarning(
                    "Nxt: could not evaluate %r: %s\n" % (text, exc))
                return False
        else:
            parsed = units.internal_value(text, "mm")
            if parsed is None:
                App.Console.PrintWarning(
                    "Nxt: %r is not a length FreeCAD can read\n" % text)
                return False
            value = parsed
        self._section.move(value)
        return True

    @QtCore.Slot(str)
    def finish(self, text: str) -> None:
        """Enter: keep the value; the section stays open."""
        self._type(text)
        self.sync()

    @QtCore.Slot(int, result=str)
    def stepped(self, steps: int) -> str:
        return length_text(self._section.offset + steps * STEP)


class _Floating:
    """A QML item floating in the 3D view beside a model point.

    Value boxes go through float_input.FloatingInput.show instead.
    """

    source = ""
    #: Where the item's top left sits from the point, in pixels; None
    #: centres the item on it.
    nudge: tuple[int, int] | None = NUDGE

    def __init__(self) -> None:
        self._widget: Any = None
        self._theme: Any = None

    def context(self) -> dict[str, Any]:
        return {}

    def refresh(self) -> None:
        """Before each placing: bring the item's values up to date."""

    def place(self, view: Any, tip: Any) -> None:
        """Put the item beside the model point `tip`, making it if needed."""
        viewport = view3d.active_viewport()
        if viewport is None:
            return
        widget = self._ensure(viewport)
        if widget is None:
            return
        self.refresh()
        x, y = view.getPointOnViewport(tip)
        ratio = viewport.devicePixelRatioF() or 1.0
        left, top = placement.from_viewport(
            x, y, viewport.height() * ratio, ratio)
        size = widget.sizeHint()
        widget.resize(size)
        dx, dy = (self.nudge if self.nudge is not None
                  else (-size.width() / 2, -size.height() / 2))
        widget.move(round(left + dx), round(top + dy))
        if not widget.isVisible():
            widget.show()
            widget.raise_()

    def _ensure(self, viewport: Any) -> Any:
        if widgets.alive(self._widget) and \
                self._widget.parentWidget() is viewport:
            return self._widget
        self.remove()
        from ..app import services
        theme = services.theme()
        if theme is None:
            from ..ui.theme import Theme
            theme = self._theme = Theme()
        try:
            widget = quick_host.make_view(
                viewport, self.source, {"theme": theme, **self.context()},
                floating=True,
                prepare=lambda w: w.setFocusPolicy(
                    QtCore.Qt.FocusPolicy.ClickFocus))
        except quick_host.QmlLoadError as exc:
            App.Console.PrintError("Nxt: %s\n" % exc)
            return None
        self._widget = widget
        return widget

    def hide(self) -> None:
        if widgets.alive(self._widget):
            self._widget.hide()

    def remove(self) -> None:
        if widgets.alive(self._widget):
            self._widget.hide()
            self._widget.deleteLater()
        self._widget = None


class ToolActions(QtCore.QObject):
    """What the frame's buttons may call."""

    def __init__(self, section: Any) -> None:
        super().__init__()
        self._section = section

    @QtCore.Slot()
    def flip(self) -> None:
        self._section.flip()

    # Deferred: both close the buttons' own view, from inside its click.
    @QtCore.Slot()
    def done(self) -> None:
        QtCore.QTimer.singleShot(0, lambda: self._section.set_editing(False))

    @QtCore.Slot()
    def remove(self) -> None:
        from . import section_view
        QtCore.QTimer.singleShot(
            0, lambda: section_view.end(self._section))


class ToolButtons(_Floating):
    """Flip, done and remove, on the frame's corner opposite the arrow."""

    source = "SectionTools.qml"
    nudge = None

    def __init__(self, section: Any) -> None:
        super().__init__()
        self.actions = ToolActions(section)

    def context(self) -> dict[str, Any]:
        return {"actions": self.actions}
