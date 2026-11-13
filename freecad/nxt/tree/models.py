"""Flat list model over a scene snapshot; depth is a role, not structure."""

from __future__ import annotations

import difflib
from collections.abc import Callable, Iterable, Sequence
from typing import Any

import FreeCAD as App

from ..core.qt import QtCore
from ..inspector import properties
from . import cycle_time, icons

_ROLE: int = QtCore.Qt.ItemDataRole.UserRole


def _q(name: str) -> QtCore.QByteArray:
    return QtCore.QByteArray(name.encode("utf-8"))


#: What a row draws in one column of connector lines.
NO_LINE, LINE_THROUGH, LINE_TEE, LINE_END = 0, 1, 2, 3


def branch_lines(rows: Sequence[tuple[str, int]], active: str = "",
                 ) -> dict[str, tuple[tuple[int, ...], int]]:
    """Per row: its connector-line columns, and the active-from column.

    The second value is the column from which lines belong to the active
    container, or -1 when the row is not under it.
    """
    lines: dict[str, tuple[tuple[int, ...], int]] = {}
    more: list[bool] = []       # by depth: is a sibling still to come?
    for name, depth in reversed(rows):
        del more[depth + 1:]
        more += [False] * (depth + 1 - len(more))
        columns = [LINE_THROUGH if more[level] else NO_LINE
                   for level in range(1, depth)]
        if depth > 0:
            columns.append(LINE_TEE if more[depth] else LINE_END)
        more[depth] = True
        lines[name] = (tuple(columns), -1)
    path: list[str] = []
    for name, depth in rows:
        del path[depth:]
        if active and active in path:
            lines[name] = (lines[name][0], path.index(active))
        path.append(name)
    return lines


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
    BranchesRole = _ROLE + 30
    ActiveFromRole = _ROLE + 31
    ActivePartRole = _ROLE + 32
    CycleTimeRole = _ROLE + 33
    IsTotalRole = _ROLE + 34
    IsCamRole = _ROLE + 35
    SuppressedRole = _ROLE + 36
    AttachableRole = _ROLE + 37

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
        # Unrendered; kept as the hook for a document-level indicator.
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
        # Detail strip only; as row chips it would make rows too tall.
        ConsumersRole: "consumers",
        # Not IsProfile: Boolean tools and datums are lifted too.
        IsLiftedRole: "isLifted",
        # Model state, like selection: it comes from the Gui, not the doc.
        ActiveRole: "isActive",
        KeyPropsRole: "keyProps",
        PropertyCountRole: "propertyCount",
        BranchesRole: "branches",
        ActiveFromRole: "activeFrom",
        ActivePartRole: "isActivePart",
        # CAM: an operation's estimate; a total row's sum.
        CycleTimeRole: "cycleTime",
        IsTotalRole: "isTotal",
        # In a CAM Operations group: references there are icon chips.
        IsCamRole: "isCam",
        SuppressedRole: "suppressed",
        # Detail strip: offers "Edit attachment", even with no support.
        AttachableRole: "attachable",
    }

    countChanged = QtCore.Signal()
    #: Row sequence rebuilt; index-based consumers must recompute.
    rowsRefreshed = QtCore.Signal()

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._snapshot: Any = None
        self._rows: list[tuple[str, int]] = []
        self._expanded: set[str] = set()
        #: Expansion of each document left for another.
        self._kept: dict[str, set[str]] = {}
        #: Initial expansion for a newly shown document; set by the bridge.
        self.opening: Callable[[Any], Iterable[str]] = (
            lambda snap: snap.opening_expansion())
        self._selection: set[str] = set()
        self._highlight: set[str] = set()
        self._detail: set[str] = set()
        self._active = ""
        self._active_part = ""
        self._lines: dict[str, tuple[tuple[int, ...], int]] = {}
        self._icon_rev = 0
        self._known: set[str] = set()
        #: CAM Jobs' Operations groups with operations in them.
        self._cycle_groups: set[str] = set()

    #: Node fields a row draws; if unchanged, the row needs no redraw.
    _DISPLAYED = ("label", "visible", "in_error", "touched", "is_container",
                  "is_feature", "is_profile", "is_lifted", "after_tip",
                  "suppressed",
                  "severity",
                  "dof", "constrained", "body", "refs", "consumers", "notes",
                  "timeline")

    @classmethod
    def _shown(cls, node: Any) -> tuple[Any, ...]:
        return tuple(getattr(node, field) for field in cls._DISPLAYED)

    def _changed_since(self, previous: Any,
                       snapshot: Any) -> list[str] | None:
        """Rows that would now draw differently; None means all."""
        if previous is None or previous.doc_name != snapshot.doc_name:
            return None
        before = previous.nodes
        # Open strips show live values not in the snapshot.
        return [name for name, node in snapshot.nodes.items()
                if name not in before or name in self._detail
                or self._shown(before[name]) != self._shown(node)]

    def set_snapshot(self, snapshot: Any, bump_icons: bool = False) -> None:
        previous = self._snapshot
        first = (previous is None or previous.doc_name != snapshot.doc_name)
        # A new icon revision changes every row's icon URL.
        changed = None if bump_icons else self._changed_since(previous,
                                                              snapshot)
        self._snapshot = snapshot
        if bump_icons:
            self._icon_rev += 1

        if first:
            if previous is not None and previous.doc_name:
                self._kept[previous.doc_name] = set(self._expanded)
            self._known = set()
            kept = self._kept.get(snapshot.doc_name)
            self._expanded = (set(kept) & set(snapshot.nodes)
                              if kept is not None
                              else set(self.opening(snapshot)))
        else:
            self._expanded &= set(snapshot.nodes)
            fresh = set(snapshot.nodes) - self._known
            self._expanded |= (snapshot.default_expansion() & fresh)
        self._known = set(snapshot.nodes)
        self._detail &= set(snapshot.nodes)
        self._cycle_groups = {
            group for group in cycle_time.operation_groups(
                self._document())
            if group in snapshot.nodes and snapshot.nodes[group].children}
        self.refresh_rows(changed)

    def refresh_rows(self, changed: Iterable[str] | None = None) -> None:
        if self._snapshot is None:
            self._apply_rows([])
            return
        rows = self._snapshot.flatten(self._expanded)
        if self._cycle_groups:
            rows = cycle_time.with_totals(rows, self._cycle_groups,
                                          self._expanded)
        self._apply_rows(rows, changed)

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
        redrawn = self._reline()
        if changed is not None and redrawn:
            changed = set(changed) | redrawn
        # A blanket dataChanged re-reads every role of every visible row,
        # several times per recompute; announce only rows that moved.
        if changed is None:
            self._touch_all()
        elif changed:
            self._touch(changed)
        self.rowsRefreshed.emit()

    def _reline(self) -> set[str]:
        """Recompute connector lines; return rows whose lines changed."""
        lines = branch_lines(self._rows, self._active)
        changed = {name for name, drawn in lines.items()
                   if self._lines.get(name) != drawn}
        self._lines = lines
        return changed

    def _touch_all(self) -> None:
        if self._rows:
            self.dataChanged.emit(self.index(0, 0),
                                  self.index(len(self._rows) - 1, 0))

    def touch(self, names: Iterable[str]) -> None:
        """Announce changed rows, for when the snapshot is patched in place."""
        self._touch(names)

    def _touch(self, names: Iterable[str]) -> None:
        wanted = set(names)
        if self._cycle_groups and self._snapshot is not None:
            # An operation's new estimate changes its group's total.
            nodes = self._snapshot.nodes
            for n in list(wanted):
                # Up through dressups: each shows what it nests.
                seen = set()
                parent = nodes[n].parent if n in nodes else None
                while parent and parent not in seen and parent in nodes:
                    seen.add(parent)
                    if parent in self._cycle_groups:
                        wanted.add(cycle_time.total_name(parent))
                        break
                    wanted.add(parent)
                    parent = nodes[parent].parent
        for row, (name, _depth) in enumerate(self._rows):
            if name in wanted:
                idx = self.index(row, 0)
                self.dataChanged.emit(idx, idx)

    def expanded(self) -> frozenset[str]:
        return frozenset(self._expanded)

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
        """Expand everything except coordinate systems and joints."""
        if self._snapshot is None:
            return
        nodes = self._snapshot.nodes
        self._expanded |= {n for n, node in nodes.items()
                           if not (node.is_coordinate_system
                                   or node.is_joint)}
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

    def selection(self) -> frozenset[str]:
        return frozenset(self._selection)

    def set_selection(self, names: Iterable[str]) -> None:
        names = set(names)
        if names == self._selection:
            return
        # Assign before notifying: the view re-reads data() synchronously.
        changed = self._selection ^ names
        self._selection = names
        self._touch(changed)

    def set_active(self, name: str | None) -> None:
        """Mark which container is active. Two rows change, at most."""
        name = name or ""
        if name == self._active:
            return
        # Assign before notifying (see set_selection).
        changed = {n for n in (self._active, name) if n}
        self._active = name
        self._touch(changed | self._reline())

    def set_active_part(self, name: str | None) -> None:
        """Mark the active Part; it has its own mark, apart from a Body's."""
        name = name or ""
        if name == self._active_part:
            return
        changed = {n for n in (self._active_part, name) if n}
        self._active_part = name
        self._touch(changed)

    def toggle_detail(self, name: str,
                      open_it: bool | None = None) -> bool:
        """Open or close a row's detail strip (not persisted); new state."""
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
        """Emphasise rows related to a hovered reference chip."""
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

    def ancestor_rows(self, row: int) -> list[int]:
        """The rows `row` is shown nested in, outermost first."""
        found: list[int] = []
        depth = self.depth_at(row)
        for above in range(row - 1, -1, -1):
            if depth == 0:
                break
            if self._rows[above][1] < depth:
                depth = self._rows[above][1]
                found.append(above)
        return found[::-1]

    def row_index_map(self) -> dict[str, int]:
        """Name -> row, for callers that need many lookups at once."""
        return {name: row for row, (name, _depth) in enumerate(self._rows)}

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

    def _children_of(self, name: str) -> list[str]:
        node = self._snapshot.nodes.get(name)
        return list(node.children) if node is not None else []

    def _in_cycle_group(self, node: Any) -> bool:
        """Whether the node sits anywhere inside a CAM Operations group."""
        seen = set()
        parent = node.parent
        while parent and parent not in seen:
            if parent in self._cycle_groups:
                return True
            seen.add(parent)
            above = self._snapshot.nodes.get(parent)
            parent = above.parent if above is not None else None
        return False

    def _document(self) -> Any:
        try:
            return App.getDocument(self._snapshot.doc_name)
        except Exception:
            return None

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
        if cycle_time.is_total(name):
            return self._total_data(role, name, depth)
        node = self._snapshot.nodes.get(name)
        if node is None:
            return None
        if role == self.CycleTimeRole:
            if not self._in_cycle_group(node):
                return ""
            value = cycle_time.nested(name, self._children_of, self._object)
            return cycle_time.formatted(value) if value is not None else ""
        if role == self.IsTotalRole:
            return False
        if role == self.IsCamRole:
            return self._in_cycle_group(node)

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
        if role == self.AttachableRole:
            return node.attachable
        if role == self.SuppressedRole:
            return node.suppressed
        if role == self.IsProfileRole:
            return node.is_profile
        if role == self.IsLiftedRole:
            return node.is_lifted
        if role == self.ActiveRole:
            return name == self._active and name != self._active_part
        if role == self.ActivePartRole:
            return name == self._active_part
        if role == self.BranchesRole:
            return list(self._lines.get(name, ((), -1))[0])
        if role == self.ActiveFromRole:
            return self._lines.get(name, ((), -1))[1]
        if role == self.SeverityRole:
            return node.severity
        if role == self.NotesRole:
            return list(node.notes)
        if role == self.DofRole:
            return -1 if node.dof is None else node.dof
        if role == self.ConstrainedRole:
            # QML has no None: -1 unknown, 0 under-, 1 fully constrained.
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
            # Live document values, read only for an open strip.
            obj = self._object(name) if name in self._detail else None
            if role == self.KeyPropsRole:
                return properties.describe(obj) if obj is not None else []
            if obj is None and node.type_id == properties.VARSET:
                # Nothing else offers a VarSet a strip: its variables do.
                obj = self._object(name)
            return properties.visible_count(obj) if obj is not None else 0
        if role == self.ConsumersRole:
            return [{"name": n, "label": lbl, "props": list(props)}
                    for n, lbl, props in node.consumers]
        return None

    #: A total row's values for roles that describe an object.
    _TOTAL_DEFAULTS: dict[int, Any] = {
        HasChildrenRole: False, ExpandedRole: False, VisibleRole: True,
        SelectedRole: False, IconRole: "", TypeRole: "", RefsRole: [],
        IsContainerRole: False, ErrorRole: False, TouchedRole: False,
        HighlightRole: False, IsFeatureRole: False, AfterTipRole: False,
        IsProfileRole: False, SeverityRole: 0, NotesRole: [], DofRole: -1,
        ConstrainedRole: -1, DetailRole: False, TimelineRole: -1,
        BodyRole: "", ConsumersRole: [], IsLiftedRole: False,
        ActiveRole: False, ActivePartRole: False, KeyPropsRole: [],
        PropertyCountRole: 0, IsTotalRole: True, IsCamRole: True,
        SuppressedRole: False, AttachableRole: False,
    }

    def _total_data(self, role: int, name: str, depth: int) -> Any:
        """A "Total Cycle Time:" row: not an object, only a sum."""
        if role == self.NameRole:
            return name
        if role == self.LabelRole:
            return cycle_time.TOTAL_LABEL
        if role == self.DepthRole:
            return depth
        if role == self.CycleTimeRole:
            group = cycle_time.group_of_total(name)
            node = self._snapshot.nodes.get(group)
            return cycle_time.total(node.children if node else (),
                                    self._children_of, self._object)
        if role == self.BranchesRole:
            return list(self._lines.get(name, ((), -1))[0])
        if role == self.ActiveFromRole:
            return self._lines.get(name, ((), -1))[1]
        return self._TOTAL_DEFAULTS.get(role)
