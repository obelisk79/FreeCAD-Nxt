"""TreeBridge: the only path from the QML tree panel to the document."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from functools import partial
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from ..app import services
from ..app.i18n import translate
from ..core import fc, log, settings
from ..core.qt import QtCore, QtGui
from ..core.transaction import transaction
from ..inspector import properties
from ..tools import editing, visibility
from . import (
    activation,
    cycle_time,
    drag_drop,
    icons,
    links,
    models,
    picking,
    rollback,
    saved_expansion,
    scene,
)

#: Re-exported for callers that import it from here.
open_edit_transaction = editing.open_edit_transaction


#: Active-container poll interval; FreeCAD emits no signal for it.
ACTIVE_POLL_MS = 500


#: How long a click in the tree stands before its detail strip opens.
AUTO_DETAIL_MS = 300


class TreeBridge(QtCore.QObject):

    documentChanged = QtCore.Signal()
    activeChanged = QtCore.Signal()
    problemCountChanged = QtCore.Signal()
    revealTreeRow = QtCore.Signal(int)
    tipBarsChanged = QtCore.Signal()
    searchResultsChanged = QtCore.Signal()
    propertyInspectorRequested = QtCore.Signal(int)
    #: Scene position for the context menu.
    contextMenuRequested = QtCore.Signal(float, float)
    renameRowRequested = QtCore.Signal(int)
    flashRows = QtCore.Signal(list)
    pickOriginsChanged = QtCore.Signal()
    #: Hold this row in place on screen until rowReleased.
    rowHeld = QtCore.Signal(int)
    rowReleased = QtCore.Signal()
    detailAutoShowChanged = QtCore.Signal()
    pinnedDetailsChanged = QtCore.Signal()
    linkArrowsChanged = QtCore.Signal()

    def __init__(self, parent: QtCore.QObject | None = None,
                 widen: bool = False) -> None:
        super().__init__(parent)
        self._widen = widen
        self._tree = models.TreeRowModel(self)
        self._tree.opening = self._opening
        self._snapshot = scene.Snapshot()
        self._dirty = False
        self._icons_dirty = False
        self._pushing_selection = False
        self._related = False       # rows are lit up for the selection
        # Tip bars are addressed by row, so any relayout invalidates them.
        self._tree.rowsRefreshed.connect(self._row_layout_changed)
        self._rollback = rollback.Rollback(self)
        self._drag_drop = drag_drop.DragDrop(self)
        self._activation = activation.Activation(self)
        self._search: list[dict[str, Any]] = []
        # Range anchor and keyboard cursor, by name since rows shift.
        self._anchor: str | None = None
        self._cursor: str | None = None
        # Selection frozen when the context menu opened.
        self._menu_names: list[str] = []

        # Timers parented to self, not static singleShot: those outlive the
        # object and fire into deleted wrappers on reload.
        self._rebuild_timer = self._deferral(self._rebuild_if_dirty)
        self._auto_timer = self._deferral(self._auto_show_detail)
        self._auto_timer.setInterval(AUTO_DETAIL_MS)
        self._auto_name = ""        # the row the timer is running for
        self._auto_detail = ""      # the strip auto-show has open
        self._pinned: set[str] = set()
        self._recompute_timer = self._deferral(self._recompute_document)
        # Outside picks batched so a box selection reveals once.
        self._picked: list[str] = []
        # Features that made the last 3D pick, when not themselves selected.
        self._origins: list[str] = []
        # Dependency arrows now drawn (links.py).
        self._arrows: dict[str, Any] = {"source": -1, "links": []}
        self._arrows_timer = self._deferral(self._update_arrows)
        self._reveal_timer = self._deferral(self._reveal_picked)

        # Polled: activating a Body emits no document signal.
        self._active = ""
        self._active_part = ""
        self._active_timer = QtCore.QTimer(self)
        self._active_timer.setInterval(ACTIVE_POLL_MS)
        self._active_timer.timeout.connect(self._sync_active)
        self._active_timer.start()

        self.rebuild()

    #: getActiveObject keys, most specific first.
    ACTIVE_KEYS: tuple[str, ...] = ("pdbody", "part")

    def active_container(self) -> str:
        """The active Body or Part, as the panel currently sees it."""
        return self._active

    def _read_active(self, keys: tuple[str, ...] = ()) -> str:
        """The active container under the first key that has one."""
        try:
            view = fc.active_view()
        except Exception:
            return ""
        if view is None:
            return ""
        for key in keys or self.ACTIVE_KEYS:
            try:
                obj = view.getActiveObject(key)
            except Exception:
                continue
            # Some builds return a tuple (object, ...).
            if isinstance(obj, tuple):
                obj = obj[0] if obj else None
            name = getattr(obj, "Name", "")
            if name and name in self._snapshot.nodes:
                return name
        return ""

    def _opening(self, snap: Any) -> set[str]:
        """Initial expansion: as saved in the file, plus object State.

        Read from the file because FreeCAD restores State only later.
        """
        saved: set[str] = set()
        try:
            doc = App.getDocument(snap.doc_name)
            saved = saved_expansion.read(getattr(doc, "FileName", "") or "")
            saved |= {o.Name for o in doc.Objects
                      if "Expanded" in (getattr(o, "State", None) or ())}
        except Exception:
            pass
        return snap.opening_expansion(saved)

    def save_expansion(self, doc: Any) -> None:
        """Mirror the panel's expansion into the stock tree before a save.

        Parents first: a stock tree item exists only once its parent opens.
        """
        snap = self._snapshot
        if snap is None or doc is None or snap.doc_name != doc.Name:
            return
        try:
            gui_doc = Gui.getDocument(doc.Name)
        except Exception:
            return
        wanted = self._tree.expanded()
        depth: dict[str, int] = {}

        def level(name: str) -> int:
            if name not in depth:
                parent = snap.nodes[name].parent
                depth[name] = 0 if parent not in snap.nodes \
                    else level(parent) + 1
            return depth[name]

        names = [n for n, node in snap.nodes.items()
                 if node.is_container and not node.is_virtual]
        for name in sorted(names, key=level):
            obj = doc.getObject(name)
            if obj is None:
                continue
            want = name in wanted
            have = "Expanded" in (getattr(obj, "State", None) or ())
            if want == have:
                continue
            try:
                # 2 expands the stock tree's item, 1 collapses it.
                gui_doc.toggleTreeItem(obj, 2 if want else 1)
            except Exception:
                pass

    def _sync_active(self) -> None:
        part = self._read_active(("part",))
        if part != self._active_part:
            self._active_part = part
            self._tree.set_active_part(part)
            self.activeChanged.emit()
        name = self._read_active()
        if name == self._active:
            return
        self._active = name
        self._tree.set_active(name)
        self.activeChanged.emit()
        if name:
            self._tree.reveal(name)
            self._tree.set_expanded(name, True)
        self._rollback.publish()

    def _deferral(self, slot: Callable[[], Any]) -> QtCore.QTimer:
        timer = QtCore.QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(0)
        timer.timeout.connect(slot)
        return timer

    # -- properties for QML --

    @QtCore.Property(QtCore.QObject, constant=True)
    def treeModel(self) -> models.TreeRowModel:
        return self._tree

    @QtCore.Property(str, notify=documentChanged)
    def documentLabel(self) -> str:
        doc = App.ActiveDocument
        if doc is None:
            return ""
        return getattr(doc, "Label", doc.Name)

    @QtCore.Property(bool, notify=documentChanged)
    def hasDocument(self) -> bool:
        return App.ActiveDocument is not None

    @QtCore.Property(bool, notify=activeChanged)
    def atRoot(self) -> bool:
        """No Body or Part is active: new objects go in at the top."""
        return not self._active

    @QtCore.Property(int, notify=problemCountChanged)
    def problemCount(self) -> int:
        return len(self._snapshot.problem_profiles())

    def _row_layout_changed(self) -> None:
        # Mid-drag, a Repeater rebuild would destroy the bar under the
        # cursor and drop the grab, so hold until the drag ends.
        if self._rollback.drag is None:
            self._rollback.publish()
        self._arrows_timer.start()

    @QtCore.Property(list, notify=tipBarsChanged)
    def tipBars(self) -> list[dict[str, Any]]:
        return self._rollback.bars()

    # -- rebuild --

    def invalidate(self, icons: bool = False) -> None:
        """Mark the snapshot stale; coalesces bursts into one rebuild.

        During a tip drag the rebuild waits for the drag to end
        (see `Rollback._apply_tip`).
        """
        self._icons_dirty = self._icons_dirty or icons
        self._dirty = True
        if self._rollback.drag is None:
            self._rebuild_timer.start()

    def _rebuild_if_dirty(self) -> None:
        if not self._dirty:
            return
        self.rebuild()

    def rebuild(self) -> None:
        bump = self._icons_dirty
        self._dirty = False
        self._icons_dirty = False
        previous = self._snapshot.doc_name if self._snapshot else ""
        self._snapshot = scene.capture(
            widen=self._widen, part_layout=settings.get("PartLayout"))
        self._rollback.restore_model_tips()
        self._tree.set_snapshot(self._snapshot, bump_icons=bump)
        self.sync_selection()
        self._active = self._read_active()
        self._tree.set_active(self._active)
        self._active_part = self._read_active(("part",))
        self._tree.set_active_part(self._active_part)
        self.activeChanged.emit()
        if self._snapshot.doc_name != previous:
            self.documentChanged.emit()
        self.problemCountChanged.emit()

    # -- selection --

    def sync_selection(self, picked: bool = False) -> None:
        """Pull Gui.Selection into the model; reveal new rows if `picked`."""
        if self._pushing_selection:
            return
        if self._origins:
            self._origins = []
            self.pickOriginsChanged.emit()
            self._arrows_timer.start()
        names: list[str] = []
        try:
            for obj in Gui.Selection.getSelection(self._snapshot.doc_name):
                if obj.Name not in names:
                    names.append(obj.Name)
        except Exception:
            pass
        before = set(self._tree.selection())
        self._tree.set_selection(names)
        self._mark_related(names)
        self._arrows_timer.start()
        if picked:
            added = [n for n in names
                     if n not in before and n in self._snapshot.nodes]
            if added:
                self._picked += [n for n in added if n not in self._picked]
                self._reveal_timer.start()

    def picked(self, doc_name: str, top: str, subname: str) -> None:
        """Reveal the feature that made a pick outside the panel."""
        if self._pushing_selection:
            return
        full = subname
        try:
            top, full = picking.full_pick(
                top, subname, Gui.Selection.getSelectionEx(doc_name, 0))
            name = picking.target(App.getDocument(doc_name), top, full)
        except Exception:
            log.error("could not trace the pick %s.%s" % (top, subname))
            name = None
        App.Console.PrintLog("Nxt pick: %s -> %s.%s -> %s\n"
                             % (subname, top, full, name))
        if name and name in self._snapshot.nodes:
            if name not in self._picked:
                self._picked.append(name)
            self._reveal_timer.start()

    @QtCore.Property(list, notify=pickOriginsChanged)
    def pickOrigins(self) -> list[str]:  # noqa: N802 - QML API
        return list(self._origins)

    @QtCore.Property("QVariantMap",  # type: ignore[arg-type]
                     notify=linkArrowsChanged)
    def linkArrows(self) -> dict[str, Any]:  # noqa: N802 - QML API
        return dict(self._arrows)

    def _arrow_subject(self) -> str | None:
        """The pick origin or sole selected object, else None."""
        if len(self._origins) == 1:
            return self._origins[0]
        selected = list(self._tree.selection())
        return selected[0] if len(selected) == 1 else None

    def _update_arrows(self) -> None:
        arrows: dict[str, Any] = {"source": -1, "links": []}
        name = self._arrow_subject()
        if name is not None and settings.get("DependencyArrows"):
            try:
                arrows = links.arrows(self._snapshot, name,
                                      self._tree.row_of)
            except Exception:
                log.error("could not work out the links of %s" % name)
        if arrows != self._arrows:
            self._arrows = arrows
            self.linkArrowsChanged.emit()

    def _reveal_picked(self) -> None:
        """Mark picked origins; if FollowSelection, scroll and flash.

        Reference picks made for a task are skipped.
        """
        picked, self._picked = self._picked, []
        doc = App.ActiveDocument
        picked = [n for n in picked if n in self._snapshot.nodes
                  and not (doc is not None and editing.is_reference_pick(
                      doc.getObject(n)))]
        if not picked:
            return
        selected = self._tree.selection()
        origins = [n for n in picked if n not in selected]
        if origins != self._origins:
            self._origins = origins
            self.pickOriginsChanged.emit()
            self._arrows_timer.start()
        if not settings.get("FollowSelection"):
            return
        for name in picked:
            self._tree.reveal(name)
        rows = sorted(r for r in (self._tree.row_of(n) for n in picked)
                      if r >= 0)
        if rows:
            self.revealTreeRow.emit(rows[0])
            self.flashRows.emit(picked)

    def _push_selection(self, names: Iterable[str],
                        additive: bool) -> None:
        doc = App.ActiveDocument
        if doc is None:
            return
        # A "Total Cycle Time:" row is no object: it is never selected.
        names = [n for n in names if not cycle_time.is_total(n)]
        self._pushing_selection = True
        try:
            if not additive:
                Gui.Selection.clearSelection()
            for name in names:
                if not scene.is_virtual(name):
                    Gui.Selection.addSelection(doc.Name, name)
        except Exception:
            log.error("selection push failed")
        finally:
            self._pushing_selection = False
        self.sync_selection()

    @QtCore.Slot(str, bool)
    def select(self, name: str, additive: bool = False) -> None:
        self._anchor = self._cursor = name
        if additive:
            self._auto_timer.stop()
        else:
            self._auto_name = name
            self._auto_timer.start()
        if additive:
            try:
                doc: Any = App.ActiveDocument
                already = {o.Name for o
                           in Gui.Selection.getSelection(doc.Name)}
                if name in already:
                    Gui.Selection.removeSelection(doc.Name, name)
                    self.sync_selection()
                    return
            except Exception:
                pass
        self._push_selection([name], additive)

    @QtCore.Slot()
    def clearSelection(self) -> None:
        try:
            Gui.Selection.clearSelection()
        except Exception:
            log.error("clear selection failed")
        self.sync_selection()

    # -- visibility --

    def _show_alone(self, doc: Any, shown: Iterable[str]) -> None:
        """Hide a Body's other stack features when one is shown.

        Of several in the same Body, the latest in history wins.
        """
        nodes = getattr(self._snapshot, "nodes", None) or {}
        keep: dict[str, str] = {}           # Body -> the feature to show
        for name in shown:
            owner = getattr(nodes.get(name), "body", None) or ""
            body = nodes.get(owner)
            if body is None or name not in body.stack:
                continue
            held = keep.get(owner)
            if held is None or body.stack.index(name) > body.stack.index(
                    held):
                keep[owner] = name
        for body_name, name in keep.items():
            for other in nodes[body_name].stack:
                vo = getattr(doc.getObject(other), "ViewObject", None)
                if vo is None:
                    continue
                wanted = other == name
                if bool(vo.Visibility) != wanted:
                    vo.Visibility = wanted

    @QtCore.Slot(str)
    def toggleVisibility(self, name: str) -> None:
        doc = App.ActiveDocument
        if doc is None:
            return
        obj = doc.getObject(name)
        vo = getattr(obj, "ViewObject", None)
        if vo is None:
            return
        try:
            with transaction(doc, "Toggle visibility"):
                vo.Visibility = not bool(vo.Visibility)
                if vo.Visibility:
                    self._show_alone(doc, [name])
        except Exception:
            log.error("visibility toggle failed for %s" % name)
        self.invalidate()

    # -- tip --

    @QtCore.Slot(str)
    def beginTipDrag(self, body_name: str) -> None:
        self._rollback.begin_drag(body_name)

    @QtCore.Slot(str, int)
    def previewTipRow(self, body_name: str, row: int) -> None:
        self._rollback.preview_row(body_name, row)

    @QtCore.Slot(str)
    def endTipDrag(self, body_name: str) -> None:
        self._rollback.end_drag(body_name)

    @QtCore.Slot(str)
    def cancelTipDrag(self, body_name: str) -> None:
        self._rollback.cancel_drag(body_name)

    @QtCore.Slot(str, str)
    def setTip(self, body_name: str, feature_name: str) -> None:
        self._rollback.set_tip(body_name, feature_name)

    # -- expansion --

    @QtCore.Slot(str)
    def toggleExpanded(self, name: str) -> None:
        self._tree.set_expanded(name, not self._tree.is_expanded(name))

    @QtCore.Slot(bool)
    def collapseTree(self, expand: bool) -> None:  # noqa: N802
        """Collapse all (keeping the active container visible), or expand."""
        if expand:
            self._tree.expand_all()
            return
        self._tree.collapse_all()
        if self._active:
            self._tree.reveal(self._active)

    # -- navigation --

    @QtCore.Slot(str)
    def revealObjectRow(self, name: str) -> None:
        """Select an object and scroll its row into view."""
        self._push_selection([name], False)
        self._tree.reveal(name)
        row = self._tree.row_of(name)
        if row >= 0:
            self.revealTreeRow.emit(row)

    def _mark_related(self, names: Iterable[str]) -> None:
        """Highlight consumers and references of the selection, if enabled."""
        related: list[str] = []
        if settings.get("HighlightRelated"):
            chosen = set(names)
            for name in chosen:
                node = self._snapshot.nodes.get(name)
                if node is None:
                    continue
                related += [n for n, _l, _p in node.consumers]
                related += [n for n, _l, _s, _part in node.refs]
            related = [n for n in related if n not in chosen]
        if related or self._related:
            self._related = bool(related)
            self._tree.set_highlight(related)

    def refresh_related(self) -> None:
        """Reapply related highlighting after the preference changes."""
        self._mark_related(self._tree.selection())

    # -- per-row detail --

    @QtCore.Slot(str, str, "QVariant")
    def setKeyProperty(self, name: str, prop: str, value: Any) -> None:
        """Edit one of the strip's key values, as one undo step."""
        doc = App.ActiveDocument
        obj = doc.getObject(name) if doc is not None else None
        if obj is not None and properties.apply(obj, prop, value):
            self.invalidate()

    @QtCore.Slot(str, float, float)
    def openPropertyInspector(self, name: str, left: float,
                              top: float) -> None:
        """Select `name` and open the Property Inspector at a position.

        Negative coordinates mean no anchor (docked panel).
        """
        from ..inspector import host as property_inspector
        if name:
            self._push_selection([name], False)
        property_inspector.open_inspector(
            left=int(left) if left >= 0 else None,
            top=int(top) if top >= 0 else None)

    def request_property_inspector(self) -> None:
        """Open the inspector for the selection, anchored to its row."""
        name = self._sole_selection()
        row = self._tree.row_of(name) if name else -1
        if row >= 0:
            self.propertyInspectorRequested.emit(row)
        else:
            self.openPropertyInspector(name or "", -1.0, -1.0)

    # -- context menu --

    @QtCore.Slot(str, float, float)
    def requestContextMenu(self, name: str, x: float, y: float) -> None:
        """Select the row unless already selected; open the menu there.

        (x, y) is in scene coordinates: Wayland hides the global pointer.
        """
        if name and name not in self._selected_names():
            self.select(name, False)
        # Deferred: observers are still receiving the selection change.
        QtCore.QTimer.singleShot(
            0, self, lambda: self.contextMenuRequested.emit(x, y))

    @QtCore.Slot(result=int)
    def contextMenuRow(self) -> int:
        """Row for a keyboard-opened menu, or -1."""
        selected = self._selected_names()
        if self._cursor in selected:
            return self._tree.row_of(self._cursor or "")
        rows = [r for r in (self._tree.row_of(n) for n in selected)
                if r >= 0]
        return min(rows) if rows else -1

    @QtCore.Slot(result="QVariant")
    def contextMenu(self) -> dict[str, Any]:
        """The menu for the current selection, as plain data."""
        from . import menu_actions
        self._menu_names = self._selected_names()
        try:
            return menu_actions.build(self, self._menu_names)
        except Exception:
            log.error("the context menu could not be built")
            return {}

    @QtCore.Slot(result="QVariant")
    def headerMenu(self) -> dict[str, Any]:
        """The header's menu; its items act on the document."""
        from . import menu_actions
        self._menu_names = []
        try:
            return menu_actions.build_header()
        except Exception:
            log.error("the header menu could not be built")
            return {}

    @QtCore.Slot(str)
    def runMenuItem(self, command: str) -> None:
        # Outside QML's call stack: a command's dialog runs its own event
        # loop, and the tree may rebuild under it.
        from . import menu_actions
        QtCore.QTimer.singleShot(0, partial(
            menu_actions.run, self, command, list(self._menu_names)))

    @QtCore.Slot()
    def deleteSelected(self) -> None:
        """Delete the selection, as FreeCAD's Delete shortcut would."""
        from . import menu_actions
        names = self._selected_names()
        if names:
            QtCore.QTimer.singleShot(0, partial(
                menu_actions.run, self, "Std_Delete", names))

    @QtCore.Slot(str, result=bool)
    def toggleDetail(self, name: str) -> bool:
        """Open or close a row's detail strip."""
        opened = self._tree.toggle_detail(name)
        if not opened and name in self._pinned:
            self._pinned.discard(name)      # closed by hand: unpinned
            self.pinnedDetailsChanged.emit()
        return opened

    def _auto_show_detail(self) -> None:
        """Open the clicked row's strip and close the last unpinned one."""
        name = self._auto_name
        if not settings.get("DetailAutoShow") or not name \
                or self._selected_names() != [name]:
            return
        last = self._auto_detail
        if last == name:
            return
        self.rowHeld.emit(self._tree.row_of(name))
        if last and last not in self._pinned:
            self._tree.close_details([last])
        self._tree.toggle_detail(name, True)
        self._auto_detail = name
        self.rowReleased.emit()

    def refresh_auto_detail(self) -> None:
        """Apply a DetailAutoShow change; turning it off clears pins."""
        if not settings.get("DetailAutoShow"):
            self._auto_timer.stop()
            self._auto_detail = ""
            if self._pinned:
                self._pinned = set()
                self.pinnedDetailsChanged.emit()
        self.detailAutoShowChanged.emit()

    @QtCore.Property(bool, notify=detailAutoShowChanged)
    def detailAutoShow(self) -> bool:  # noqa: N802 - QML API
        return bool(settings.get("DetailAutoShow"))

    @QtCore.Property(list, notify=pinnedDetailsChanged)
    def pinnedDetails(self) -> list[str]:  # noqa: N802 - QML API
        return sorted(self._pinned)

    @QtCore.Slot(str)
    def toggleDetailPin(self, name: str) -> None:  # noqa: N802
        """Toggle whether auto-show leaves this strip open."""
        self._pinned ^= {name}
        self.pinnedDetailsChanged.emit()

    @QtCore.Slot(result=bool)
    def mouseHeld(self) -> bool:  # noqa: N802 - QML API
        """Whether any mouse button is down: a drag without one is over."""
        return QtGui.QGuiApplication.mouseButtons() \
            != QtCore.Qt.MouseButton.NoButton

    @QtCore.Slot(result=bool)
    def closeDetail(self) -> bool:
        """Escape: close the selected rows' strips, else every open one."""
        return (self._tree.close_details(self._selected_names())
                or self._tree.close_details())

    # -- search --

    @QtCore.Property(list, notify=searchResultsChanged)
    def searchResults(self) -> list[dict[str, Any]]:
        return self._search

    @QtCore.Slot(str)
    def setSearch(self, text: str) -> None:
        results: list[dict[str, Any]] = []
        for node in self._snapshot.search(text):
            path = self._snapshot.path_of(node.name)
            results.append({
                "name": node.name,
                "label": node.label,
                "context": " \u203a ".join(path),
                "isProfile": node.is_profile,
                "iconUrl": icons.url_for(self._snapshot.doc_name, node.name,
                                         self._tree.icon_revision()),
            })
        if results != self._search:
            self._search = results
            self.searchResultsChanged.emit()

    @QtCore.Slot()
    def revealFirstProblem(self) -> None:
        """Reveal the first problem profile and open its strip."""
        problems = self._snapshot.problem_profiles()
        if problems:
            self.revealObjectRow(problems[0])
            self._tree.toggle_detail(problems[0], True)

    @QtCore.Slot(str)
    def revealObject(self, name: str) -> None:
        """Reveal a search hit."""
        if name in self._snapshot.nodes:
            self.revealObjectRow(name)

    # -- keyboard and rename --

    def _sole_selection(self) -> str | None:
        """The one selected object, or None."""
        try:
            selected = Gui.Selection.getSelection(self._snapshot.doc_name)
        except Exception:
            return None
        if len(selected) != 1:
            return None
        return selected[0].Name

    @QtCore.Slot(result=int)
    def treeRenameRow(self) -> int:
        name = self._sole_selection()
        if name is None:
            return -1
        return self._tree.row_of(name)

    @QtCore.Slot()
    def toggleSelectedVisibility(self) -> None:
        """Hide all selected if any is shown, else show all; one undo."""
        doc = App.ActiveDocument
        if doc is None:
            return
        # targets() maps a Body-filed selection back to the feature.
        visibility.toggle(doc, visibility.targets(doc), self._show_alone)
        self.invalidate()

    def _selected_names(self) -> list[str]:
        try:
            doc = App.ActiveDocument
            if doc is None:
                return []
            return [o.Name for o in Gui.Selection.getSelection(doc.Name)]
        except Exception:
            return []

    @QtCore.Slot(str)
    def selectRange(self, name: str) -> None:
        """Select every row from the anchor to `name`, inclusive."""
        start = self._tree.row_of(self._anchor) if self._anchor else -1
        end = self._tree.row_of(name)
        if end < 0:
            return
        if start < 0:
            start = end
        self._cursor = name
        low, high = sorted((start, end))
        names = [self._tree.name_at(row) for row in range(low, high + 1)]
        self._push_selection([n for n in names if n is not None], False)

    @QtCore.Slot(int, bool, result=int)
    def stepSelection(self, step: int, extend: bool) -> int:
        """Move the selection by `step` rows; return the row or -1."""
        count = self._tree.rowCount()
        if count == 0:
            return -1
        here = self._tree.row_of(self._cursor) if self._cursor else -1
        if here < 0:
            selected = self._selected_names()
            rows = [self._tree.row_of(n) for n in selected]
            rows = [r for r in rows if r >= 0]
            here = (max(rows) if step > 0 else min(rows)) if rows else -1
        target = 0 if here < 0 else max(0, min(count - 1, here + step))
        return self._select_row(target, extend)

    @QtCore.Slot(bool, bool, result=int)
    def jumpSelection(self, to_end: bool, extend: bool) -> int:  # noqa: N802
        """Select the first or last row; return the row or -1."""
        return self._select_row(
            self._tree.rowCount() - 1 if to_end else 0, extend)

    def _select_row(self, target: int, extend: bool) -> int:
        """Move the cursor to a row; return it, or -1 if none."""
        name = self._tree.name_at(target)
        if name is None:
            return -1
        self._cursor = name
        if extend:
            self.selectRange(name)
        else:
            self._anchor = name
            self._push_selection([name], False)
        return target

    @QtCore.Slot(int, result="QVariantList")
    def breadcrumb(self, row: int) -> list[dict[str, Any]]:
        """Ancestor rows and labels of a row, outermost first."""
        crumbs = []
        for above in self._tree.ancestor_rows(row):
            name = self._tree.name_at(above)
            node = self._snapshot.nodes.get(name) if name else None
            if node is not None:
                crumbs.append({"row": above, "label": node.label})
        return crumbs

    @QtCore.Slot(int, result=int)
    def stepBranch(self, step: int) -> int:
        """Right/Left tree navigation; return the current row or -1."""
        name = self._cursor
        if name is None or self._tree.row_of(name) < 0:
            selected = self._selected_names()
            name = selected[-1] if selected else None
        here = self._tree.row_of(name) if name else -1
        if name is None or here < 0:
            return -1
        node = self._snapshot.nodes.get(name)
        branch = node is not None and bool(node.children)
        open_ = self._tree.is_expanded(name)
        depth = self._tree.depth_at(here)
        if step > 0:
            if branch and not open_:
                self._tree.set_expanded(name, True)
                return here
            target = here + 1
            if not (branch and open_ and self._tree.depth_at(target) > depth):
                return -1
        else:
            if branch and open_:
                self._tree.set_expanded(name, False)
                return self._tree.row_of(name)
            target = here - 1
            while target >= 0 and self._tree.depth_at(target) >= depth:
                target -= 1
            if target < 0:
                return -1
        found = self._tree.name_at(target)
        if found is None:
            return -1
        self._cursor = self._anchor = found
        self._push_selection([found], False)
        return target

    @QtCore.Slot(str, str)
    def rename(self, name: str, label: str) -> None:
        """Set an object's Label (Name is immutable)."""
        doc = App.ActiveDocument
        if doc is None:
            return
        obj = doc.getObject(name)
        label = (label or "").strip()
        if obj is None or not label or label == obj.Label:
            return
        try:
            old = obj.Label
            with transaction(doc, "Rename"):
                obj.Label = label
            self._toast(doc, translate("Nxt", "Renamed %s to %s")
                        % (old, label))
        except Exception:
            log.error("could not rename %s" % name)
        self.invalidate()

    # -- undo toast --

    @staticmethod
    def _named(doc: Any, names: Iterable[Any]) -> str:
        """One object by its label; several by how many there are."""
        names = [str(n) for n in names]
        if len(names) != 1:
            return translate("Nxt", "%d objects") % len(names)
        obj = doc.getObject(names[0]) if doc is not None else None
        return str(getattr(obj, "Label", names[0]))

    def _toast(self, doc: Any, message: str, body: str = "") -> None:
        """Show an undoable toast; `body` is a Body whose tip moved."""
        services.toast(
            doc, message,
            partial(self._rollback.show_through_tip, body) if body else None)

    # -- activation --

    @QtCore.Slot(str)
    def activate(self, name: str) -> None:
        self._activation.activate(name)

    @QtCore.Slot()
    def activateRoot(self) -> None:
        """Deactivate the active Body and Part."""
        view = fc.active_view()
        for key in self.ACTIVE_KEYS:
            try:
                if view is not None:
                    view.setActiveObject(key, None)
            except Exception:
                log.error("could not clear the active %s" % key)
        self._sync_active()

    def edit_feature(self, doc_name: str, name: str) -> None:
        """Reveal a feature opened for editing from the 3D view."""
        if doc_name != getattr(App.ActiveDocument, "Name", None):
            return
        if name in self._snapshot.nodes:
            if name not in self._picked:
                self._picked.append(name)
            self._reveal_timer.start()

    def _recompute_document(self) -> None:
        doc = App.ActiveDocument
        if doc is None:
            return
        try:
            doc.recompute()
        except Exception:
            log.error("could not recompute after a drop")

    # -- drag and drop --

    @QtCore.Slot(str, result="QVariantList")
    def dragNames(self, name: str) -> list[str]:  # noqa: N802
        return self._drag_drop.drag_names(name)

    @QtCore.Slot("QVariantList", result=str)
    def slideContainer(self, names: list[Any]) -> str:  # noqa: N802
        return self._drag_drop.slide_container(names)

    @QtCore.Slot("QVariantList", str, result=bool)
    def canReorderOn(self, sources: list[Any], target_name: str) -> bool:  # noqa: N802
        return self._drag_drop.can_reorder_on(sources, target_name)

    @QtCore.Slot("QVariantList", str, result=bool)
    def canDropInto(self, sources: list[Any], target_name: str) -> bool:  # noqa: N802
        return self._drag_drop.can_drop_into(sources, target_name)

    @QtCore.Slot("QVariantList", str, result=bool)
    def reorderOn(self, sources: list[Any], target_name: str) -> bool:  # noqa: N802
        return self._drag_drop.reorder_on(sources, target_name)

    @QtCore.Slot("QVariantList", str, result=bool)
    def dropInto(self, sources: list[Any], target_name: str) -> bool:  # noqa: N802
        return self._drag_drop.drop_into(sources, target_name)

    @QtCore.Slot("QVariantList", str, result=str)
    def dropHint(self, sources: list[Any], target_name: str) -> str:  # noqa: N802
        return self._drag_drop.drop_hint(sources, target_name)

    @QtCore.Slot("QVariantList", str, result=bool)
    def dropOn(self, sources: list[Any], target_name: str) -> bool:
        return self._drag_drop.drop_on(sources, target_name)

    # -- document root as drop target --

    @QtCore.Slot("QVariantList", result=bool)
    def canDropOnRoot(self, sources: list[Any]) -> bool:  # noqa: N802
        return self._drag_drop.can_drop_on_root(sources)

    @QtCore.Slot("QVariantList", result=bool)
    def dropOnRoot(self, sources: list[Any]) -> bool:  # noqa: N802
        return self._drag_drop.drop_on_root(sources)

    @QtCore.Slot()
    def refresh(self) -> None:
        self.rebuild()
