"""Colours and metrics for the panel, taken from the stock tree view.

Not from `QApplication.palette()`: that follows the desktop theme and
knows nothing about FreeCAD's stylesheet. See DESIGN.md.
"""

from __future__ import annotations

from typing import Any

from ..qt import QtCore, QtGui, QtWidgets
from . import qss_colours, settings

#: How far each derived colour travels from the palette it is mixed from.
SURFACE_MIX = 0.55
DIM_MIX = 0.45
HOVER_MIX = 0.25
BORDER_MIX = 0.18
CHIP_MIX = 0.10
SEVERITY_MIX = 0.85

DARK_LIGHTNESS = 128
WARNING_HUE = QtGui.QColor(226, 140, 40)
DANGER_HUE = QtGui.QColor(214, 74, 68)
#: Dependency arrows, SolidWorks' convention: parents (what the selection
#: reads) blue, children (what reads it) purple.
PARENT_HUE = QtGui.QColor(66, 139, 230)
CHILD_HUE = QtGui.QColor(168, 92, 214)
ARROW_MIX = 0.85

#: A severity mark cuts its interior glyph out in whichever of these
#: contrasts with the fills, decided once against their mean lightness.
MARK_INK_PIVOT = 165
MARK_INK_ON_DARK = QtGui.QColor(255, 255, 255)
MARK_INK_ON_LIGHT = QtGui.QColor(28, 28, 28)

PILL_ALPHA = 0.88
PILL_HOVER_ALPHA = 0.94
PILL_BORDER_ALPHA = 0.14

#: The glyphs the panel draws itself - expand arrows, the tip bar - are
#: the text colour taken this far towards whatever is behind them, so they
#: read on a light theme and a dark one without shouting over the labels.
BRANCH_MIX = 0.3
BRANCH_ON_DARK = QtGui.QColor(235, 235, 235)
BRANCH_ON_LIGHT = QtGui.QColor(30, 30, 30)
#: FreeCAD's own defaults for the 3D view's background, for a profile that
#: has never saved them.
VIEW_SIMPLE = 3940932863
VIEW_TOP = 859006463
VIEW_BOTTOM = 2880154879

#: Metrics, as a fraction of the row height unless named otherwise.
MIN_ROW_HEIGHT = 20
ROW_TEXT_PADDING = 8
#: Space around a row's text, by the RowDensity preference. Everything else
#: in a row - icon, marks, fonts, chips - is a share of the row's height,
#: so this one number scales them all.
ROW_PADDING_BY_DENSITY = {"compact": 3, "normal": ROW_TEXT_PADDING,
                          "roomy": 14}
INDENT = 14
ROW_PAD = 4
MIN_TIP_GUTTER = 14
TIP_GUTTER_RATIO = 0.85
ICON_RATIO = 0.72
MARK_RATIO = 0.62
MARK_SMALL_RATIO = 0.50
FONT_ROW_RATIO = 0.48
FONT_SMALL_RATIO = 0.44
FONT_ASIDE_RATIO = 0.40
CHIP_RATIO = 0.68
FIELD_RATIO = 0.86


def _scaled(row_height: int, ratio: float) -> int:
    return int(round(row_height * ratio))


def _with_alpha(colour: QtGui.QColor, alpha: float) -> QtGui.QColor:
    out = QtGui.QColor(colour)
    out.setAlphaF(alpha)
    return out


#: Least lightness gap between text and background that still reads. Below
#: it the palette is not describing what is on screen - a stylesheet theme
#: such as FreeCAD Light paints the stock tree itself and can leave the
#: widget palette black on black.
MIN_CONTRAST = 90


def _readable(base: QtGui.QColor, text: QtGui.QColor) -> bool:
    return abs(base.lightness() - text.lightness()) >= MIN_CONTRAST


def _legible(candidates: list[tuple[QtGui.QColor, QtGui.QColor]]
             ) -> tuple[QtGui.QColor, QtGui.QColor]:
    """The first (base, text) pair that reads, else plain dark on light."""
    for base, text in candidates:
        if _readable(base, text):
            return base, text
    return QtGui.QColor(250, 250, 250), QtGui.QColor(30, 30, 30)


#: Where FreeCAD keeps the colour tokens a stylesheet names as `@Name`.
TOKEN_GROUP = "User parameter:BaseApp/Preferences/View"


def _token(name: str) -> str | int | None:
    """A FreeCAD colour token's stored value, whatever type it was saved as."""
    try:
        import FreeCAD as App
        for _kind, key, value in App.ParamGet(TOKEN_GROUP).GetContents() or ():
            if key == name:
                return value
    except Exception:  # noqa: BLE001 - no FreeCAD, or no such group
        return None
    return None


def _view_background() -> QtGui.QColor | None:
    """The 3D view's background, averaged down its gradient.

    What the drawn glyphs sit on in overlay mode, where the panel paints
    nothing behind them.
    """
    try:
        import FreeCAD as App
        view = App.ParamGet(TOKEN_GROUP)
        if view.GetBool("Simple", False):
            packed = [int(view.GetUnsigned("BackgroundColor", VIEW_SIMPLE))]
        else:
            packed = [int(view.GetUnsigned("BackgroundColor2", VIEW_TOP)),
                      int(view.GetUnsigned("BackgroundColor3", VIEW_BOTTOM))]
    except Exception:  # noqa: BLE001 - no FreeCAD, or a stand-in for it
        return None
    count = len(packed)
    return QtGui.QColor(sum(c >> 24 & 255 for c in packed) // count,
                        sum(c >> 16 & 255 for c in packed) // count,
                        sum(c >> 8 & 255 for c in packed) // count)


def _stylesheet_colours() -> tuple[QtGui.QColor | None,
                                   QtGui.QColor | None]:
    """(background, text) the applied stylesheet gives a tree."""
    app = QtWidgets.QApplication.instance()
    qss = app.styleSheet() if isinstance(app, QtWidgets.QApplication) else ""
    if not qss:
        return None, None
    return qss_colours.tree_colours(qss, _token)


def _sample(window: QtWidgets.QWidget,
            viewport: QtWidgets.QWidget) -> QtGui.QColor | None:
    """The colour at `viewport`'s empty bottom corner, drawn by `window`.

    Grabbed through the window rather than the viewport: the viewport is
    transparent and a stylesheet can paint its background on an ancestor,
    so a grab of the viewport alone comes back black.
    """
    size = viewport.size()
    if size.width() < 4 or size.height() < 4:
        return None
    corner = viewport.mapTo(window, QtCore.QPoint(size.width() - 3,
                                                  size.height() - 3))
    image = window.grab(QtCore.QRect(corner, QtCore.QSize(2, 2))).toImage()
    if image.isNull():
        return None
    colour = QtGui.QColor(image.pixel(0, 0))
    colour.setAlpha(255)
    return colour


def _painted_base(widget: Any) -> QtGui.QColor | None:
    """The background the stock tree is actually drawn with, or None.

    Only while it is on screen: the fallback when the stylesheet does not
    say, or says it in a way `qss_colours` cannot read.
    """
    try:
        viewport = widget.viewport() if widget is not None else None
        if viewport is None or not viewport.isVisible():
            return None
        return _sample(viewport.window(), viewport)
    except (RuntimeError, AttributeError):
        return None


def _mix(a: QtGui.QColor, b: QtGui.QColor, t: float) -> QtGui.QColor:
    return QtGui.QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
    )


def find_reference_widget(
        main_window: QtWidgets.QWidget | None) -> QtWidgets.QWidget | None:
    """The best available stand-in for 'a styled tree in this application'.

    Order matters: the stock tree carries the stylesheet rules written for
    trees specifically, which is what we want to match. Anything else is a
    consolation prize.
    """
    if main_window is None:
        return None
    for cls in (QtWidgets.QTreeWidget, QtWidgets.QTreeView,
                QtWidgets.QAbstractItemView):
        for widget in main_window.findChildren(cls):
            if widget.isVisible() or widget.parent() is not None:
                return widget
    # None rather than the main window: at startup the stock tree may not
    # exist yet, and returning something that merely works lets the panel
    # settle for it forever. None means "ask again later", and the Theme
    # falls back to the application palette in the meantime.
    return None


class Theme(QtCore.QObject):

    changed = QtCore.Signal()

    #: Overlay mode: the panel floats over the 3D view with no background of
    #: its own. Presentation state, so it lives here rather than on the
    #: bridge - and every delegate already sees `theme`.
    _overlay = False

    def __init__(self, parent: QtCore.QObject | None = None,
                 reference: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._reference: QtWidgets.QWidget | None = reference
        self._widget_palette = QtGui.QPalette()
        self._painted: QtGui.QColor | None = None
        self._qss_base: QtGui.QColor | None = None
        self._qss_text: QtGui.QColor | None = None
        self._viewport_palette = QtGui.QPalette()
        self._view_background: QtGui.QColor | None = None
        self._rebuild()                 # every colour exists before a read
        self.refresh()

    @QtCore.Property(bool, notify=changed)
    def overlay(self) -> bool:
        return self._overlay

    def set_overlay(self, on: bool) -> None:
        on = bool(on)
        if on == self._overlay:
            return
        self._overlay = on
        self._rebuild()
        self.changed.emit()

    def set_reference(self, widget: QtWidgets.QWidget | None) -> None:
        self._reference = widget
        self.refresh()

    def reference(self) -> QtWidgets.QWidget | None:
        return self._reference

    def refresh(self) -> None:
        widget_palette: QtGui.QPalette | None = None
        viewport_palette: QtGui.QPalette | None = None

        widget = self._reference
        if widget is not None:
            try:
                widget_palette = widget.palette()
                viewport = getattr(widget, "viewport", None)
                if callable(viewport):
                    target = viewport()
                    if target is not None:
                        viewport_palette = target.palette()
            except RuntimeError:
                # the reference widget was destroyed under us
                self._reference = None
                widget_palette = None
                viewport_palette = None

        if widget_palette is None:
            widget_palette = QtWidgets.QApplication.palette()

        self._qss_base, self._qss_text = _stylesheet_colours()
        self._painted = self._qss_base or _painted_base(widget)
        self._view_background = _view_background()
        self._widget_palette = widget_palette
        self._viewport_palette = viewport_palette or widget_palette
        self._header_max_percent: Any = settings.get("HeaderMaxPercent")
        self._header_min_width: Any = settings.get("HeaderMinWidth")
        self._density = str(settings.get("RowDensity"))
        self._chip_mode = str(settings.get("ReferenceChips"))
        self._under_constrained = bool(settings.get("UnderConstrainedMarks"))
        self._tool_tips = bool(settings.get("RowToolTips"))
        self._rebuild()
        self.changed.emit()

    # -- derived palette ---------------------------------------------------- #

    def _rebuild(self) -> None:
        """Compute every colour once, on refresh.

        Not on every read. These are bound from delegates, so a getter that
        mixes a fresh QColor each time is re-run for every row on every
        binding evaluation - and QML reported the churn as a binding loop on
        `color`, which it is not far from being.
        """
        widget = self._widget_palette.color(QtGui.QPalette.ColorGroup.Active,
                                            QtGui.QPalette.ColorRole.Window)
        base = self._viewport_palette.color(QtGui.QPalette.ColorGroup.Active,
                                            QtGui.QPalette.ColorRole.Base)
        text = self._widget_palette.color(QtGui.QPalette.ColorGroup.Active,
                                          QtGui.QPalette.ColorRole.Text)
        if self._painted is not None:
            # What the stylesheet says (or the stock tree shows) beats what
            # the palette says: a stylesheet theme paints over the palette
            # without changing it. Text from the stylesheet if it sets one,
            # else the palette's if it reads, else the far end of the
            # lightness range.
            base = self._painted
            if self._qss_text is not None:
                text = self._qss_text
            if not _readable(base, text):
                text = (QtGui.QColor(235, 235, 235)
                        if base.lightness() < DARK_LIGHTNESS
                        else QtGui.QColor(30, 30, 30))
            widget = base
        app = QtWidgets.QApplication.palette()
        group = QtGui.QPalette.ColorGroup.Active
        role = QtGui.QPalette.ColorRole
        base, text = _legible([
            (base, text),
            (widget, self._widget_palette.color(group, role.WindowText)),
            (app.color(group, role.Base), app.color(group, role.Text)),
            (app.color(group, role.Window), app.color(group, role.WindowText)),
        ])
        if not _readable(widget, text):
            widget = base
        accent = self._widget_palette.color(QtGui.QPalette.ColorGroup.Active,
                                            QtGui.QPalette.ColorRole.Highlight)
        accent_text = self._widget_palette.color(
            QtGui.QPalette.ColorGroup.Active,
            QtGui.QPalette.ColorRole.HighlightedText)

        self._background = base
        self._text = text
        self._accent = accent
        self._accentText = accent_text
        # Text links use the palette's Link role, as Qt's own labels do; the
        # Highlight role is a fill for selected text to sit on, and as text
        # on the panel's background it can be too faint to read.
        self._link = self._widget_palette.color(
            QtGui.QPalette.ColorGroup.Active, QtGui.QPalette.ColorRole.Link)
        self._dark = base.lightness() < DARK_LIGHTNESS
        self._surface = _mix(base, widget, SURFACE_MIX)
        self._textDim = _mix(text, base, DIM_MIX)
        self._hover = _mix(base, accent, HOVER_MIX)
        self._border = _mix(base, text, BORDER_MIX)
        self._chip = _mix(base, text, CHIP_MIX)
        self._warning = _mix(base, WARNING_HUE, SEVERITY_MIX)
        self._danger = _mix(base, DANGER_HUE, SEVERITY_MIX)
        self._arrowIn = _mix(base, PARENT_HUE, ARROW_MIX)
        self._arrowOut = _mix(base, CHILD_HUE, ARROW_MIX)
        # What a severity mark cuts its interior glyph out in. It has to
        # contrast with the warning and danger fills rather than with the
        # panel, because in overlay mode the panel has no colour at all -
        # binding this to the canvas would erase the glyph exactly when the
        # background behind it is least predictable. Both fills are mid-tone
        # and saturated, so the readable choice is the far end of the
        # lightness range from them, not from the theme.
        severity_lightness = (self._warning.lightness() +
                              self._danger.lightness()) / 2
        self._markInk = (MARK_INK_ON_DARK
                         if severity_lightness < MARK_INK_PIVOT
                         else MARK_INK_ON_LIGHT)

        # The drawn glyphs sit on the panel when docked and on the 3D view
        # in an overlay, so that is what they have to stand out from.
        behind = base
        if self._overlay and self._view_background is not None:
            behind = self._view_background
        ink = text
        if not _readable(behind, ink):
            ink = (BRANCH_ON_DARK if behind.lightness() < DARK_LIGHTNESS
                   else BRANCH_ON_LIGHT)
        self._branchInk = _mix(ink, behind, BRANCH_MIX)

        # Overlay backdrops. Per-row rather than panel-wide, which is what
        # keeps text legible over a dark model and a pale background in the
        # same frame - the scrim sits exactly where the text is and nowhere
        # else. Derived from the palette so it inverts with the stylesheet
        # instead of being a hard-coded white.
        self._pill = _with_alpha(base, PILL_ALPHA)
        self._pillHover = _with_alpha(_mix(base, accent, HOVER_MIX),
                                      PILL_HOVER_ALPHA)
        self._pillBorder = _with_alpha(text, PILL_BORDER_ALPHA)
        # Nothing behind the panel in overlay mode; the 3D view is the
        # backdrop. Kept as a colour rather than a flag so QML can bind it.
        self._canvasColor = (QtGui.QColor(0, 0, 0, 0) if self._overlay
                             else QtGui.QColor(base))

        # Metrics are cached here for the same reason the colours are, and
        # it matters more: a row height derived on every read built a
        # QFontMetrics per binding evaluation, and `rowHeight` is read a
        # dozen times per row - so a relayout of twenty visible rows
        # constructed a few hundred of them, sixty times a second while the
        # timeline bar was moving. That is what made the drag stutter.
        self._rowHeight = self._measure_row_height()
        self._tipGutter = max(MIN_TIP_GUTTER,
                              _scaled(self._rowHeight, TIP_GUTTER_RATIO))
        self._iconSize = _scaled(self._rowHeight, ICON_RATIO)
        self._markSize = _scaled(self._rowHeight, MARK_RATIO)
        self._markSizeSmall = _scaled(self._rowHeight, MARK_SMALL_RATIO)
        self._fontRow = _scaled(self._rowHeight, FONT_ROW_RATIO)
        self._fontSmall = _scaled(self._rowHeight, FONT_SMALL_RATIO)
        self._fontAside = _scaled(self._rowHeight, FONT_ASIDE_RATIO)
        self._chipHeight = _scaled(self._rowHeight, CHIP_RATIO)
        self._fieldHeight = _scaled(self._rowHeight, FIELD_RATIO)

    def _measure_row_height(self) -> int:
        widget = self._reference
        font: QtGui.QFont | None = None
        if widget is not None:
            try:
                font = widget.font()
            except RuntimeError:
                font = None
        if font is None:
            font = QtWidgets.QApplication.font()
        padding = ROW_PADDING_BY_DENSITY.get(
            getattr(self, "_density", "normal"), ROW_TEXT_PADDING)
        return max(MIN_ROW_HEIGHT - (ROW_TEXT_PADDING - padding),
                   QtGui.QFontMetrics(font).height() + padding)

    @QtCore.Property(str, notify=changed)
    def chipMode(self) -> str:  # noqa: N802 - QML API
        """Which reference chips a row shows: problems, all or none."""
        return getattr(self, "_chip_mode", "problems")

    @QtCore.Property(bool, notify=changed)
    def showUnderConstrained(self) -> bool:  # noqa: N802 - QML API
        """Whether a merely under-constrained sketch gets its ring."""
        return getattr(self, "_under_constrained", True)

    @QtCore.Property(bool, notify=changed)
    def showToolTips(self) -> bool:  # noqa: N802 - QML API
        """Whether hovering a row's controls shows what they do."""
        return getattr(self, "_tool_tips", True)

    @QtCore.Property(bool, notify=changed)
    def dark(self) -> bool:
        return self._dark

    @QtCore.Property(QtGui.QColor, notify=changed)
    def background(self) -> QtGui.QColor:
        return self._background

    @QtCore.Property(QtGui.QColor, notify=changed)
    def surface(self) -> QtGui.QColor:
        """A half step away from the canvas, for surfaces.

        A half step away from the canvas, for anything that needs to
        read as a surface laid on the panel rather than part of it.
        """
        return self._surface

    @QtCore.Property(QtGui.QColor, notify=changed)
    def text(self) -> QtGui.QColor:
        return self._text

    @QtCore.Property(QtGui.QColor, notify=changed)
    def textDim(self) -> QtGui.QColor:
        return self._textDim

    @QtCore.Property(QtGui.QColor, notify=changed)
    def accent(self) -> QtGui.QColor:
        return self._accent

    @QtCore.Property(QtGui.QColor, notify=changed)
    def accentText(self) -> QtGui.QColor:
        return self._accentText

    @QtCore.Property(QtGui.QColor, notify=changed)
    def link(self) -> QtGui.QColor:
        return self._link

    @QtCore.Property(QtGui.QColor, notify=changed)
    def arrowIn(self) -> QtGui.QColor:  # noqa: N802 - QML API
        """Dependency arrows from what the selection reads."""
        return self._arrowIn

    @QtCore.Property(QtGui.QColor, notify=changed)
    def arrowOut(self) -> QtGui.QColor:  # noqa: N802 - QML API
        """Dependency arrows to what reads the selection."""
        return self._arrowOut

    @QtCore.Property(QtGui.QColor, notify=changed)
    def hover(self) -> QtGui.QColor:
        """Pre-selection tint.

        A quarter of the way to the selection colour: clearly present
        while scanning, clearly not a selection.
        """
        return self._hover

    @QtCore.Property(QtGui.QColor, notify=changed)
    def border(self) -> QtGui.QColor:
        return self._border

    @QtCore.Property(QtGui.QColor, notify=changed)
    def chip(self) -> QtGui.QColor:
        return self._chip

    @QtCore.Property(QtGui.QColor, notify=changed)
    def markInk(self) -> QtGui.QColor:
        return self._markInk

    @QtCore.Property(QtGui.QColor, notify=changed)
    def warning(self) -> QtGui.QColor:
        return self._warning

    @QtCore.Property(QtGui.QColor, notify=changed)
    def danger(self) -> QtGui.QColor:
        return self._danger

    @QtCore.Property(QtGui.QColor, notify=changed)
    def canvas(self) -> QtGui.QColor:
        """What the panel paints behind everything.

        What the panel paints behind everything - the base colour when
        docked, fully transparent in overlay mode.
        """
        return self._canvasColor

    @QtCore.Property(QtGui.QColor, notify=changed)
    def pill(self) -> QtGui.QColor:
        return self._pill

    @QtCore.Property(QtGui.QColor, notify=changed)
    def pillHover(self) -> QtGui.QColor:
        return self._pillHover

    @QtCore.Property(QtGui.QColor, notify=changed)
    def pillBorder(self) -> QtGui.QColor:
        return self._pillBorder

    # -- metrics ------------------------------------------------------------ #

    @QtCore.Property(int, notify=changed)
    def rowHeight(self) -> int:
        return self._rowHeight

    @QtCore.Property(QtGui.QColor, notify=changed)
    def branchInk(self) -> QtGui.QColor:
        return self._branchInk

    @QtCore.Property(int, notify=changed)
    def iconSize(self) -> int:
        return self._iconSize

    @QtCore.Property(int, notify=changed)
    def markSize(self) -> int:
        return self._markSize

    @QtCore.Property(int, notify=changed)
    def markSizeSmall(self) -> int:
        return self._markSizeSmall

    @QtCore.Property(int, notify=changed)
    def fontRow(self) -> int:
        return self._fontRow

    @QtCore.Property(int, notify=changed)
    def fontSmall(self) -> int:
        return self._fontSmall

    @QtCore.Property(int, notify=changed)
    def fontAside(self) -> int:
        return self._fontAside

    @QtCore.Property(int, notify=changed)
    def chipHeight(self) -> int:
        return self._chipHeight

    @QtCore.Property(int, notify=changed)
    def fieldHeight(self) -> int:
        return self._fieldHeight

    @QtCore.Property(int, notify=changed)
    def headerMaxPercent(self) -> int:
        """Widest the header may grow, as a percentage of the screen."""
        return self._header_max_percent

    @QtCore.Property(int, notify=changed)
    def headerMinWidth(self) -> int:
        """The header is never capped below this, whatever the screen."""
        return self._header_min_width

    @QtCore.Property(int, notify=changed)
    def indent(self) -> int:
        return INDENT

    @QtCore.Property(int, notify=changed)
    def rowPad(self) -> int:
        """Left inset before the first slot.

        Shared with the timeline bar, which has to land on the same
        grid as the rows.
        """
        return ROW_PAD

    @QtCore.Property(int, notify=changed)
    def tipGutter(self) -> int:
        """Slot reserved on every row for the tip marker.

        It sits between the indentation and the disclosure triangle.

        On every row, not just a Body's features: reserving it selectively
        would indent the feature rows relative to their siblings, and in a
        tree an x offset reads as depth. Its own slot rather than sharing
        the disclosure's, because a MultiTransform is both a stack member
        and a parent, so one row can need the marker and the expander at
        once.
        """
        return self._tipGutter
