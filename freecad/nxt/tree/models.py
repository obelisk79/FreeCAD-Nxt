"""The list model over a scene snapshot.

One flat QAbstractListModel with `depth` as a role, rather than a tree
model: indentation here is presentation, not structure. See DESIGN.md.
"""

from __future__ import annotations

import difflib
from collections.abc import Iterable
from typing import Any

import FreeCAD as App

from ..qt import QtCore
from . import icons, properties

_ROLE: int = QtCore.Qt.ItemDataRole.UserRole


def _q(name: str) -> QtCore.QByteArray:
    return QtCore.QByteArray(name.encode("utf-8"))


class TreeRowModel(QtCore.QAbstractListModel):
    """Flattened, expansion-aware rows over a document snapshot."""

    NameRole = _ROLE + 1
    LabelRole = _ROLE + 2
    DepthRole = _ROLE + 3
    HasChildrenRole = _ROLE + 4
    ExpandedRole = _ROLE + 5
    VisibleRole = _ROLE + 6
    SelectedRole = _ROLE + 7
    IconRole = _ROLE + 8
    TypeRole = _ROLE + 9
    RefsRole = _ROLE + 10
    IsContainerRole = _ROLE + 11
    ErrorRole = _ROLE + 12
    TouchedRole = _ROLE + 13
    HighlightRole = _ROLE + 14
    IsFeatureRole = _ROLE + 15
    AfterTipRole = _ROLE + 16
    IsProfileRole = _ROLE + 17
    SeverityRole = _ROLE + 18
    NotesRole = _ROLE + 19
    DofRole = _ROLE + 20
    ConstrainedRole = _ROLE + 21
    DetailRole = _ROLE + 22
    TimelineRole = _ROLE + 23
    BodyRole = _ROLE + 24
    ConsumersRole = _ROLE + 25
    IsLiftedRole = _ROLE + 26
    ActiveRole = _ROLE + 27
    KeyPropsRole = _ROLE + 28
    PropertyCountRole = _ROLE + 29

    _ROLE_NAMES = {
        NameRole: "name",
        LabelRole: "label",
        DepthRole: "depth",
        HasChildrenRole: "hasChildren",
        ExpandedRole: "expanded",
        VisibleRole: "objectVisible",
        SelectedRole: "selected",
        IconRole: "iconUrl",
        TypeRole: "typeId",
        RefsRole: "refs",
        IsContainerRole: "isContainer",
        ErrorRole: "inError",
        # Nothing renders this at the moment - the per-row staleness dot was
        # removed as noise, since on a freshly opened old document almost
        # everything is touched and forty dots say one thing about the
        # document rather than forty about its rows. Kept because it costs
        # nothing and is the hook a document-level indicator would use.
        TouchedRole: "touched",
        HighlightRole: "highlighted",
        IsFeatureRole: "isFeature",
        AfterTipRole: "afterTip",
        IsProfileRole: "isProfile",
        SeverityRole: "severity",
        NotesRole: "notes",
        DofRole: "dof",
        ConstrainedRole: "constrained",
        DetailRole: "detailOpen",
        TimelineRole: "timeline",
        BodyRole: "bodyName",
        # Only read inside an open detail strip. This is the reuse
        # information the shelf existed to show; it is not a row chip,
        # because a sketch used by six features would grow a row six chips
        # tall and the timeline would stop being scannable.
        ConsumersRole: "consumers",
        # Lifted, but not necessarily a sketch: a Boolean's tool and a datum
        # a feature is attached to are lifted for the same reason and carry
        # the same "used by" list, while only a sketch has a solver to
        # report on. The two questions are asked separately because the
        # answers differ.
        IsLiftedRole: "isLifted",
        # The container new operations land in. Model state rather than
        # node state, like selection: it comes from the Gui, not from the
        # document, and two snapshots of the same document can disagree
        # about it.
        ActiveRole: "isActive",
        KeyPropsRole: "keyProps",
        PropertyCountRole: "propertyCount",
    }

    countChanged = QtCore.Signal()
    #: Emitted whenever the visible row sequence has been rebuilt. Anything
    #: that addresses rows by index - the tip bars, most obviously - has to
    #: recompute against the new layout.
    rowsRefreshed = QtCore.Signal()

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._snapshot: Any = None
        self._rows: list[tuple[str, int]] = []            # [(name, depth)]
        self._expanded: set[str] = set()
        self._selection: set[str] = set()
        self._highlight: set[str] = set()
        self._detail: set[str] = set()
        self._active = ""
        self._icon_rev = 0
        self._known: set[str] = set()

    # -- population -------------------------------------------------------- #

    #: The node fields a row draws. Two snapshots that agree on all of
    #: them describe a row that does not need redrawing, whatever else
    #: changed in the document.
    _DISPLAYED = ("label", "visible", "in_error", "touched", "is_container",
                  "is_feature", "is_profile", "is_lifted", "after_tip",
                  "severity",
                  "dof", "constrained", "body", "refs", "consumers", "notes",
                  "timeline")

    @classmethod
    def _shown(cls, node: Any) -> tuple[Any, ...]:
        return tuple(getattr(node, field) for field in cls._DISPLAYED)

    def _changed_since(self, previous: Any,
                       snapshot: Any) -> list[str] | None:
        """Which objects a row would now draw differently.

        None means 'everything', which is the honest answer when there
        is nothing to compare against.
        """
        if previous is None or previous.doc_name != snapshot.doc_name:
            return None
        before = previous.nodes
        # An open strip shows live property values the snapshot does not
        # carry, so its row is re-read on every rebuild.
        return [name for name, node in snapshot.nodes.items()
                if name not in before or name in self._detail
                or self._shown(before[name]) != self._shown(node)]

    def set_snapshot(self, snapshot: Any, bump_icons: bool = False) -> None:
        previous = self._snapshot
        first = (previous is None or previous.doc_name != snapshot.doc_name)
        # Worked out before the swap, and skipped entirely when the icon
        # revision moved - a new revision changes every row's icon URL, so
        # every row does have to be re-read.
        changed = None if bump_icons else self._changed_since(previous,
                                                              snapshot)
        self._snapshot = snapshot
        if bump_icons:
            self._icon_rev += 1

        if first:
            self._known = set()
            self._expanded = set(snapshot.default_expansion())
        else:
            # keep what the user opened, drop what is gone, and open any
            # container that appeared since the last snapshot
            self._expanded &= set(snapshot.nodes)
            fresh = set(snapshot.nodes) - self._known
            self._expanded |= (snapshot.default_expansion() & fresh)
        self._known = set(snapshot.nodes)
        self._detail &= set(snapshot.nodes)
        self.refresh_rows(changed)

    def refresh_rows(self, changed: Iterable[str] | None = None) -> None:
        if self._snapshot is None:
            self._apply_rows([])
            return
        self._apply_rows(self._snapshot.flatten(self._expanded), changed)

    def icon_revision(self) -> int:
        return self._icon_rev

    def _apply_rows(self, new_rows: list[tuple[str, int]],
                    changed: Iterable[str] | None = None) -> None:
        old_names = [r[0] for r in self._rows]
        new_names = [r[0] for r in new_rows]
        if old_names != new_names:
            matcher = difflib.SequenceMatcher(None, old_names, new_names,
                                              autojunk=False)
            for tag, i1, i2, j1, j2 in reversed(matcher.get_opcodes()):
                if tag == "equal":
                    continue
                if tag in ("replace", "delete"):
                    self.beginRemoveRows(QtCore.QModelIndex(), i1, i2 - 1)
                    del self._rows[i1:i2]
                    self.endRemoveRows()
                if tag in ("replace", "insert"):
                    self.beginInsertRows(QtCore.QModelIndex(), i1,
                                         i1 + (j2 - j1) - 1)
                    self._rows[i1:i1] = new_rows[j1:j2]
                    self.endInsertRows()
            self.countChanged.emit()
        self._rows = list(new_rows)
        # `changed` is None the first time, or when there is nothing to
        # compare against - then every row has to be re-read. Otherwise only
        # the rows whose displayed state actually moved are announced: a
        # blanket dataChanged makes the view re-read every role of every
        # visible row, and on a document where one recompute fires several
        # signals that is the same work several times over for rows that
        # did not move.
        if changed is None:
            self._touch_all()
        elif changed:
            self._touch(changed)
        self.rowsRefreshed.emit()

    def _touch_all(self) -> None:
        if self._rows:
            self.dataChanged.emit(self.index(0, 0),
                                  self.index(len(self._rows) - 1, 0))

    def touch(self, names: Iterable[str]) -> None:
        """Announce that these objects' displayed state has moved.

        Public because the bridge patches the snapshot in place during a tip
        drag and has to say what it changed; everything else here goes
        through the snapshot.
        """
        self._touch(names)

    def _touch(self, names: Iterable[str]) -> None:
        wanted = set(names)
        for row, (name, _depth) in enumerate(self._rows):
            if name in wanted:
                idx = self.index(row, 0)
                self.dataChanged.emit(idx, idx)

    # -- interaction state -------------------------------------------------- #

    def is_expanded(self, name: str) -> bool:
        return name in self._expanded

    def set_expanded(self, name: str, expanded: bool) -> None:
        if expanded:
            if name in self._expanded:
                return
            self._expanded.add(name)
        else:
            if name not in self._expanded:
                return
            self._expanded.discard(name)
        self.refresh_rows()

    def expand_all(self) -> None:
        if self._snapshot is None:
            return
        self._expanded = set(self._snapshot.nodes)
        self.refresh_rows()

    def collapse_all(self) -> None:
        self._expanded = set()
        self.refresh_rows()

    def reveal(self, name: str) -> None:
        """Expand every ancestor of `name` so it becomes a visible row."""
        if self._snapshot is None:
            return
        chain: list[str] = []
        node = self._snapshot.nodes.get(name)
        guard = set()
        while node is not None and node.parent and node.parent not in guard:
            guard.add(node.parent)
            chain.append(node.parent)
            node = self._snapshot.nodes.get(node.parent)
        if not chain:
            return
        before = len(self._expanded)
        self._expanded.update(chain)
        if len(self._expanded) != before:
            self.refresh_rows()

    def set_selection(self, names: Iterable[str]) -> None:
        names = set(names)
        if names == self._selection:
            return
        # Assign before notifying. dataChanged makes the view re-read data(),
        # which reads _selection - emitting first hands every affected row its
        # previous state, so rows light up one selection behind.
        changed = self._selection ^ names
        self._selection = names
        self._touch(changed)

    def set_active(self, name: str | None) -> None:
        """Mark which container is active. Two rows change, at most."""
        name = name or ""
        if name == self._active:
            return
        # Assign before notifying, for the same reason selection does: the
        # view re-reads data() synchronously, so emitting first hands both
        # rows their previous answer.
        changed = {n for n in (self._active, name) if n}
        self._active = name
        self._touch(changed)

    def toggle_detail(self, name: str,
                      open_it: bool | None = None) -> bool:
        """Open or close a row's detail strip. Returns the new state.

        Row-local and deliberately not persisted: it is a glance at why a
        row is marked, not a setting. Assign before notifying, for the same
        reason selection does.
        """
        want = (name not in self._detail) if open_it is None else bool(open_it)
        if want == (name in self._detail):
            return want
        if want:
            self._detail.add(name)
        else:
            self._detail.discard(name)
        self._touch({name})
        return want

    def close_details(self, names: Iterable[str] | None = None) -> bool:
        """Close these rows' detail strips, or every one. True if any was."""
        closing = self._detail & (set(names) if names is not None
                                  else set(self._detail))
        if not closing:
            return False
        self._detail -= closing
        self._touch(closing)
        return True

    def set_highlight(self, names: Iterable[str]) -> None:
        """Emphasise the rows related to a hovered reference chip.

        Transient "related to what you are pointing at" emphasis, driven
        by hovering a reference chip. Distinct from selection, which belongs
        to FreeCAD.
        """
        names = set(names)
        if names == self._highlight:
            return
        changed = self._highlight ^ names
        self._highlight = names
        self._touch(changed)

    def row_of(self, name: str) -> int:
        for row, (candidate, _depth) in enumerate(self._rows):
            if candidate == name:
                return row
        return -1

    def name_at(self, row: int) -> str | None:
        if 0 <= row < len(self._rows):
            return self._rows[row][0]
        return None

    def depth_at(self, row: int) -> int:
        if 0 <= row < len(self._rows):
            return self._rows[row][1]
        return 0

    def row_index_map(self) -> dict[str, int]:
        """Name -> row, for callers that need many lookups at once."""
        return {name: row for row, (name, _depth) in enumerate(self._rows)}

    # -- QAbstractListModel ------------------------------------------------ #

    def roleNames(self) -> dict[int, QtCore.QByteArray]:
        return {role: _q(name) for role, name in self._ROLE_NAMES.items()}

    def rowCount(
            self,
            parent: QtCore.QModelIndex | QtCore.QPersistentModelIndex = (
                QtCore.QModelIndex()),
    ) -> int:
        if parent.isValid():
            return 0
        return len(self._rows)

    def _object(self, name: str) -> Any:
        try:
            doc = App.getDocument(self._snapshot.doc_name)
            return doc.getObject(name) if doc is not None else None
        except Exception:
            return None

    def data(self, index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
             role: int = QtCore.Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or self._snapshot is None:
            return None
        row = index.row()
        if row < 0 or row >= len(self._rows):
            return None
        name, depth = self._rows[row]
        node = self._snapshot.nodes.get(name)
        if node is None:
            return None

        if role == self.NameRole:
            return name
        if role == self.LabelRole:
            return node.label
        if role == self.DepthRole:
            return depth
        if role == self.HasChildrenRole:
            return bool(node.children)
        if role == self.ExpandedRole:
            return name in self._expanded
        if role == self.VisibleRole:
            return node.visible
        if role == self.SelectedRole:
            return name in self._selection
        if role == self.IconRole:
            return icons.url_for(self._snapshot.doc_name, name, self._icon_rev)
        if role == self.TypeRole:
            return node.type_id
        if role == self.RefsRole:
            return [{"name": n, "label": lbl, "severity": sev,
                     "sub": part, "pinned": n in node.pinned,
                     "iconUrl": icons.url_for(self._snapshot.doc_name, n,
                                              self._icon_rev, gray=True)}
                    for n, lbl, sev, part in node.refs]
        if role == self.IsContainerRole:
            return node.is_container
        if role == self.ErrorRole:
            return node.in_error
        if role == self.TouchedRole:
            return node.touched
        if role == self.HighlightRole:
            return name in self._highlight
        if role == self.IsFeatureRole:
            return node.is_feature
        if role == self.AfterTipRole:
            return node.after_tip
        if role == self.IsProfileRole:
            return node.is_profile
        if role == self.IsLiftedRole:
            return node.is_lifted
        if role == self.ActiveRole:
            return name == self._active
        if role == self.SeverityRole:
            return node.severity
        if role == self.NotesRole:
            return list(node.notes)
        if role == self.DofRole:
            return -1 if node.dof is None else node.dof
        if role == self.ConstrainedRole:
            # Tri-state flattened for QML, which has no None: -1 unknown,
            # 0 not fully constrained, 1 fully constrained. "Unknown" is a
            # real answer here - a build whose solver does not answer must
            # not be drawn as if every sketch were fine.
            if node.constrained is None:
                return -1
            return 1 if node.constrained else 0
        if role == self.DetailRole:
            return name in self._detail
        if role == self.TimelineRole:
            return node.timeline
        if role == self.BodyRole:
            return node.body or ""
        if role in (self.KeyPropsRole, self.PropertyCountRole):
            # Read from the document, and only for an open strip: the
            # values are not in the snapshot, and nobody sees them shut.
            obj = self._object(name) if name in self._detail else None
            if role == self.KeyPropsRole:
                return properties.describe(obj) if obj is not None else []
            return properties.visible_count(obj) if obj is not None else 0
        if role == self.ConsumersRole:
            return [{"name": n, "label": lbl, "props": list(props)}
                    for n, lbl, props in node.consumers]
        return None
