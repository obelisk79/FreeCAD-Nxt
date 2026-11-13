"""The Contents card's rows, as a flat list model for a ListView.

Over sketch_contents.py's snapshot. Changes to the sketch mark it stale
and it is read again once they stop, so a drag costs one read at its
end, not one per frame; while the card is closed nothing is read. The
selection, the search and the filters only lay the rows out again, and
the new rows are diffed against the old, so the list keeps its scroll
and its delegates. A dimension's text is formatted when a row asks.
"""

from __future__ import annotations

import difflib
from collections.abc import Callable
from typing import Any

from ..core import log
from ..core.qt import QtCore
from . import sketch_contents as contents

_ROLE: int = QtCore.Qt.ItemDataRole.UserRole
#: The row fields QML reads, in role order; "value" is formatted late.
FIELDS = ("key", "kind", "title", "detail", "number", "mark", "dashed",
          "selected", "folded", "count", "index", "name", "editable",
          "driving", "active", "chips", "more", "fixes")
VALUE_ROLE = _ROLE + len(FIELDS) + 1
#: Changes closer together than this are one drag: read at its end.
SETTLE_MS = 150


class ContentsModel(QtCore.QAbstractListModel):
    """Rows for SketchContents.qml; `sketch` gives the edited sketch."""

    changed = QtCore.Signal()
    #: A row to scroll into view: the selection moved in the 3D view.
    reveal = QtCore.Signal(int)

    def __init__(self, sketch: Callable[[], Any],
                 parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._sketch = sketch
        self._snapshot = contents.Snapshot()
        self._view = contents.View()
        self._rows: list[dict[str, Any]] = []
        self._texts: dict[int, str] = {}
        self._counts: dict[str, int] = {}
        self._open = False
        self._stale = True
        #: Constraint indices the next layout keeps, from an element's +n.
        self._only: set[int] | None = None
        self._clock = QtCore.QElapsedTimer()
        self._read_timer = QtCore.QTimer(self)
        self._read_timer.setSingleShot(True)
        self._read_timer.timeout.connect(self._read)

    # -- the model -- #

    def roleNames(self) -> dict[int, QtCore.QByteArray]:  # noqa: N802
        # "index" is a delegate's own row number in QML: "ref" here.
        names = {_ROLE + 1 + i: QtCore.QByteArray(
            ("ref" if name == "index" else name).encode())
            for i, name in enumerate(FIELDS)}
        names[VALUE_ROLE] = QtCore.QByteArray(b"value")
        return names

    def rowCount(self, parent: Any = None) -> int:  # noqa: N802
        return 0 if parent is not None and parent.isValid() \
            else len(self._rows)

    def data(self, index: Any, role: int = _ROLE) -> Any:
        if not index.isValid() or index.row() >= len(self._rows):
            return None
        row = self._rows[index.row()]
        if role == VALUE_ROLE:
            return self._text(int(row["index"])) \
                if row["kind"] == "constraint" else ""
        position = role - _ROLE - 1
        return row[FIELDS[position]] if 0 <= position < len(FIELDS) \
            else None

    def _text(self, index: int) -> str:
        """A dimension's value as FreeCAD shows it, formatted once."""
        if index not in self._texts:
            constraint = self._snapshot.constraints[index]
            self._texts[index] = self._format(index) \
                if constraint.dimensional else ""
        return self._texts[index]

    def _format(self, index: int) -> str:
        sketch = self._sketch()
        try:
            return str(sketch.getDatum(index).UserString)
        except Exception:  # noqa: BLE001 - called by QML, any build
            return "%g" % self._snapshot.constraints[index].raw

    # -- what QML reads and sets -- #

    @QtCore.Property(bool, notify=changed)
    def open(self) -> bool:
        return self._open

    @QtCore.Property(str, notify=changed)
    def tab(self) -> str:
        return self._view.tab

    @QtCore.Property(str, notify=changed)
    def query(self) -> str:
        return self._view.query

    @QtCore.Property(list, notify=changed)
    def filters(self) -> list[str]:
        return sorted(self._view.filters)

    @QtCore.Property("QVariantMap", notify=changed)  # type: ignore[arg-type]
    def counts(self) -> dict[str, int]:
        return dict(self._counts)

    @QtCore.Slot(bool)
    def setOpen(self, on: bool) -> None:  # noqa: N802
        if on == self._open:
            return
        self._open = on
        self.changed.emit()
        if on and self._stale:
            self._read()
        else:
            self._layout()

    @QtCore.Slot(str)
    def setTab(self, tab: str) -> None:  # noqa: N802
        if tab in contents.FILTERS and tab != self._view.tab:
            self._view.tab = tab
            self._view.filters = frozenset()
            self._layout()

    @QtCore.Slot(str)
    def setQuery(self, text: str) -> None:  # noqa: N802
        if text != self._view.query:
            self._view.query = text
            self._layout()

    @QtCore.Slot(str)
    def toggleFilter(self, name: str) -> None:  # noqa: N802
        if name in contents.FILTERS[self._view.tab]:
            self._view.filters = self._view.filters ^ {name}
            self._layout()

    @QtCore.Slot(str, bool)
    def setFolded(self, key: str, folded: bool) -> None:  # noqa: N802
        self._view.folds[key.removeprefix("g:")] = folded
        self._layout()

    @QtCore.Slot()
    def showFree(self) -> None:  # noqa: N802
        """Open on the elements still free to move."""
        self._view.tab = contents.ELEMENTS
        self._view.filters = frozenset({contents.FREE})
        self._view.query = ""
        if self._open:
            self._layout()
        else:
            self.setOpen(True)

    @QtCore.Slot(int)
    def showConstraintsOn(self, geo: int) -> None:  # noqa: N802
        """Every constraint on one element, past its strip's chips."""
        self._view.tab = contents.CONSTRAINTS
        self._view.filters = frozenset()
        self._view.query = ""
        self._view.folds = {}
        self._only = set(self._snapshot.on.get(geo, []))
        self._layout()

    # -- what the panel tells it -- #

    def stale(self) -> None:
        """The sketch changed: read it again once the changes stop."""
        self._stale = True
        if not self._open:
            return
        quiet = not self._clock.isValid() \
            or self._clock.elapsed() > SETTLE_MS
        self._read_timer.start(0 if quiet and not
                               self._read_timer.isActive() else SETTLE_MS)

    def reselect(self, names: list[str],
                 vertex_geo: dict[str, int]) -> None:
        """The selection changed: lay out again, no reading."""
        selected = tuple(names)
        if selected == self._view.selected:
            return
        self._view.selected = selected
        self._view.vertex_geo = vertex_geo
        if self._open:
            self._layout(reveal=True)

    def clear(self) -> None:
        """No sketch is edited: forget the last one."""
        self._snapshot = contents.Snapshot()
        self._view.selected = ()
        self._stale = True
        self._read_timer.stop()
        self._apply([])

    # -- inside -- #

    def _read(self) -> None:
        sketch = self._sketch()
        if sketch is None:
            self.clear()
            return
        try:
            self._snapshot = contents.read(sketch)
        except Exception:  # noqa: BLE001 - called from a Qt timer
            log.error("could not read the sketch's contents")
            return
        self._clock.start()
        self._stale = False
        self._texts = {}
        self._counts = contents.counts(self._snapshot)
        self._layout(fresh=True)
        self.changed.emit()

    def _layout(self, reveal: bool = False, fresh: bool = False) -> None:
        if not self._open:
            self._apply([])
            return
        texts: dict[int, str] = {}
        if self._view.query.strip() and self._view.tab == \
                contents.CONSTRAINTS:
            texts = {c.index: self._text(c.index)
                     for c in self._snapshot.constraints if c.dimensional}
        rows = contents.rows(self._snapshot, self._view, texts)
        if self._only is not None:
            rows = [r for r in rows if r["kind"] in ("group", "summary")
                    or r["index"] in self._only]
            self._only = None
        self._apply(rows, refresh_values=fresh)
        self.changed.emit()
        if reveal:
            first = next((i for i, r in enumerate(self._rows)
                          if r["selected"]), -1)
            if first >= 0:
                self.reveal.emit(first)

    def _apply(self, rows: list[dict[str, Any]],
               refresh_values: bool = False) -> None:
        """The new rows, as inserts, removes and changed rows."""
        old_keys = [r["key"] for r in self._rows]
        new_keys = [r["key"] for r in rows]
        matcher = difflib.SequenceMatcher(None, old_keys, new_keys,
                                          autojunk=False)
        root = QtCore.QModelIndex()
        changed: list[int] = []
        offset = 0
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                for k in range(i2 - i1):
                    old, new = self._rows[i1 + offset + k], rows[j1 + k]
                    if old != new or refresh_values:
                        self._rows[i1 + offset + k] = new
                        changed.append(i1 + offset + k)
                continue
            if i2 > i1:
                self.beginRemoveRows(root, i1 + offset, i2 + offset - 1)
                del self._rows[i1 + offset:i2 + offset]
                self.endRemoveRows()
            if j2 > j1:
                self.beginInsertRows(root, i1 + offset,
                                     i1 + offset + j2 - j1 - 1)
                self._rows[i1 + offset:i1 + offset] = rows[j1:j2]
                self.endInsertRows()
            offset += (j2 - j1) - (i2 - i1)
        for row in changed:
            index = self.index(row, 0)
            self.dataChanged.emit(index, index)
