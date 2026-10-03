"""The QML-facing object.

Everything QML is allowed to do to the document goes through a slot here.
QML never touches FreeCAD directly: it emits intent ("select this", "drop
these onto that") and this layer decides whether the intent is legal, wraps
it in a transaction, and lets the observers push the result back into the
models.

That one-way discipline is what keeps the panel consistent with the rest of
the UI. A visibility change made in the stock tree, the Python console or a
macro arrives here by exactly the same path as one made in our own delegate.
"""

from __future__ import annotations

import time
import traceback
from collections.abc import Callable, Iterable
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from ..qt import QtCore
from . import (
    editing,
    icons,
    links,
    models,
    picking,
    properties,
    reorder,
    scene,
    settings,
)

#: Kept importable from here: tests and older callers use this name.
open_edit_transaction = editing.open_edit_transaction


def _err(message: str) -> None:
    App.Console.PrintError("Nxt: %s\n" % message)
    App.Console.PrintError(traceback.format_exc())


#: How often to ask the Gui which container is active. There is no signal
#: for it, so this is the one poll in the panel.
ACTIVE_POLL_MS = 500

#: Past this, one drag step costs more than a frame and live preview gives
#: up in favour of applying once on release.
LIVE_PREVIEW_BUDGET_S = 0.12


class TreeBridge(QtCore.QObject):

    documentChanged = QtCore.Signal()
    profileCountChanged = QtCore.Signal()
    problemCountChanged = QtCore.Signal()
    revealTreeRow = QtCore.Signal(int)
    tipBarsChanged = QtCore.Signal()
    searchResultsChanged = QtCore.Signal()
    propertyInspectorRequested = QtCore.Signal(int)
    #: Open the context menu for the selection at this point in the
    #: panel's scene: where the row was right-clicked.
    contextMenuRequested = QtCore.Signal(float, float)
    #: Start renaming this row, as F2 does; asked for by the menu.
    renameRowRequested = QtCore.Signal(int)
    #: Briefly light up these rows: objects just picked outside the panel.
    flashRows = QtCore.Signal(list)
    pickOriginsChanged = QtCore.Signal()
    linkArrowsChanged = QtCore.Signal()

    def __init__(self, parent: QtCore.QObject | None = None,
                 widen: bool = False) -> None:
        super().__init__(parent)
        self._widen = widen
        self._tree = models.TreeRowModel(self)
        self._snapshot = scene.Snapshot()
        self._dirty = False
        self._icons_dirty = False
        self._pushing_selection = False
        self._highlight_source: str | None = None
        # Tip bars are addressed by row index, so they are invalidated by any
        # relayout - an expand/collapse moves them without the document
        # changing at all.
        self._tree.rowsRefreshed.connect(self._row_layout_changed)
        self._tip_drag: dict[str, Any] | None = None
        # Where each Body's bar was last put down, as the *object* whose row
        # it sits under rather than a row index - indices move whenever a
        # branch is expanded. Only a resting place that still resolves to
        # the current tip is honoured, so any other route to moving the tip
        # falls back to the tip's own row without having to know about this.
        self._bar_anchor: dict[str, str] = {}
        self._search: list[dict[str, Any]] = []
        # Where Shift+click and Shift+arrow ranges start, and where the
        # arrow keys last moved to. Names, not rows: rows shift whenever a
        # branch opens or closes.
        self._anchor: str | None = None
        self._cursor: str | None = None
        # What the open context menu is for: the selection when it opened,
        # which an item that changes the selection must not change under it.
        self._menu_names: list[str] = []

        # Deferrals go through timers parented to this object, never through
        # the static QTimer.singleShot. A static single-shot holds a bound
        # method and outlives the object it was scheduled for, so on reload
        # it fires into a deleted C++ wrapper and raises RuntimeError from a
        # callback with nothing to catch it - which is exactly what filled
        # the report view with save-state errors on the panel. Restarting a
        # timer also debounces for free.
        self._rebuild_timer = self._deferral(self._rebuild_if_dirty)
        self._bars_timer = self._deferral(self.tipBarsChanged.emit)
        self._drain_timer = self._deferral(self._drain_tip_drag)
        self._finish_timer = self._deferral(self._finish_pending_drag)
        self._edit_timer = self._deferral(self._enter_pending_edit)
        self._recompute_timer = self._deferral(self._recompute_document)
        self._restore_timer = self._deferral(self._show_finished_models)
        # Objects picked outside the panel since the last reveal, collected
        # so a box selection - one observer call per object - reveals once.
        self._picked: list[str] = []
        # The features that made what was last picked in the 3D view, when
        # that is not the selected object itself: marked in the tree as
        # SolidWorks marks the feature a picked face belongs to, until the
        # selection next changes.
        self._origins: list[str] = []
        # The dependency arrows now drawn (links.py), and a deferral so a
        # burst of selection and layout changes recomputes them once.
        self._arrows: dict[str, Any] = {"source": -1, "links": []}
        self._arrows_timer = self._deferral(self._update_arrows)
        self._reveal_timer = self._deferral(self._reveal_picked)
        self._pending_edit: tuple[str, str] | None = None
        # model -> (tip, steps it was set against)
        self._model_tips: dict[str, tuple[str, tuple[str, ...]]] = {}
        self._pending_restore: list[str] = []
        self._pending_finish: tuple[str, bool] | None = None

        # Which container new operations land in. There is no observer for
        # this - activating a Body is a Gui action and emits no document
        # signal - so it is polled. One attribute read every half second is
        # far below the noise floor of everything else the panel does, and
        # the alternative is an indicator that silently goes stale, which
        # is worse than no indicator at all.
        self._active = ""
        self._active_timer = QtCore.QTimer(self)
        self._active_timer.setInterval(ACTIVE_POLL_MS)
        self._active_timer.timeout.connect(self._sync_active)
        self._active_timer.start()

        self.rebuild()

    #: Keys `ActiveView.getActiveObject` answers to, in the order the
    #: panel prefers them: a Body inside a Part is the more specific
    #: answer, and the one an operation would actually land in.
    ACTIVE_KEYS: tuple[str, ...] = ("pdbody", "part")

    def active_container(self) -> str:
        """The active Body or Part, as the panel currently sees it."""
        return self._active

    def _read_active(self) -> str:
        try:
            view = Gui.ActiveDocument.ActiveView
        except Exception:
            return ""
        for key in self.ACTIVE_KEYS:
            try:
                obj = view.getActiveObject(key)
            except Exception:
                continue
            # Some builds answer with (object, placement, ...) rather than
            # a bare object. Unwrap rather than assume either shape.
            if isinstance(obj, tuple):
                obj = obj[0] if obj else None
            name = getattr(obj, "Name", "")
            if name and name in self._snapshot.nodes:
                return name
        return ""

    def _sync_active(self) -> None:
        name = self._read_active()
        if name == self._active:
            return
        self._active = name
        self._tree.set_active(name)

    def _deferral(self, slot: Callable[[], Any]) -> QtCore.QTimer:
        timer = QtCore.QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(0)
        timer.timeout.connect(slot)
        return timer

    # ------------------------------------------------------------------ #
    # properties for QML
    # ------------------------------------------------------------------ #

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

    @QtCore.Property(int, notify=profileCountChanged)
    def profileCount(self) -> int:
        return len(self._snapshot.profiles)

    @QtCore.Property(int, notify=problemCountChanged)
    def problemCount(self) -> int:
        return len(self._snapshot.problem_profiles())

    def _row_layout_changed(self) -> None:
        # Repeater rebuilds every delegate when its model changes, which
        # mid-drag would destroy the bar under the cursor and drop the mouse
        # grab. The live preview relays out constantly, so hold the signal
        # until the drag finishes.
        if self._tip_drag is None:
            self._publish_tip_bars()
        self._arrows_timer.start()

    def _publish_tip_bars(self) -> None:
        """Announce new marker positions on the next event-loop turn.

        Never synchronously. `Repeater` destroys and rebuilds every delegate
        when its model changes, and this is reached from slots QML calls out
        of a marker's own `onReleased`. Destroying an object while one of
        its signal handlers is still on the stack is not merely unsupported
        in QML - `QQmlData::destroyed` calls qFatal, which aborts the
        process. One turn of the event loop is enough for the handler to
        have returned.
        """
        self._bars_timer.start()

    @QtCore.Property(list, notify=tipBarsChanged)
    def tipBars(self) -> list[dict[str, Any]]:
        """One descriptor per Body whose timeline is currently visible.

        `pos` is the row the bar sits *below*. A collapsed Body contributes
        nothing: there is no gap to put a bar in.
        """
        index = self._tree.row_index_map()
        bars: list[dict[str, Any]] = []
        for name, node in self._snapshot.nodes.items():
            if not node.stack:
                continue
            feature_rows = [index[f] for f in node.stack if f in index]
            if not feature_rows:
                continue
            child_rows = [index[c] for c in node.children if c in index]
            first_feature = min(feature_rows)
            last_child = max(child_rows) if child_rows else max(feature_rows)
            pos = self._resting_position(name, node, index)
            if pos is None and node.is_model and node.tip == name:
                pos = max(feature_rows)
            if pos is None:
                pos = index.get(node.tip) if node.tip else None
            if pos is None:
                pos = first_feature
            bars.append({
                "body": name,
                "label": node.label,
                "pos": pos,
                "minPos": first_feature,
                "maxPos": max(last_child, first_feature),
                "depth": self._tree.depth_at(first_feature),
            })
        return bars

    def _resting_position(self, name: str, node: Any,
                          index: dict[str, int]) -> int | None:
        """Where the bar was last put down, if it still sets this tip."""
        anchor = self._bar_anchor.get(name)
        resting = index.get(anchor) if anchor is not None else None
        if (resting is not None and
                self._tip_for_row(name, resting) == node.tip):
            return resting
        return None

    def _tip_for_row(self, body_name: str, row: int) -> str | None:
        """The feature a bar dropped below `row` sets.

        Only a solid feature can be a tip, so a bar parked under a sketch
        sets the last feature above it and stays where it was put. Scanning
        rows rather than timeline positions makes this agree with what is
        on screen even when part of the Body is collapsed.
        """
        node = self._snapshot.nodes.get(body_name)
        if node is None or not node.stack:
            return None
        stack = set(node.stack)
        if node.is_model and row >= max(
                (self._tree.row_index_map().get(n, -1) for n in node.stack),
                default=-1):
            return body_name    # below the last step: the finished model
        cursor = min(row, self._tree.rowCount() - 1)
        while cursor >= 0:
            name = self._tree.name_at(cursor)
            if name in stack:
                return name
            cursor -= 1
        return None

    # ------------------------------------------------------------------ #
    # rebuild plumbing
    # ------------------------------------------------------------------ #

    def invalidate(self, icons: bool = False) -> None:
        """Mark the snapshot stale.

        Coalesces a burst of document signals into a single rebuild on
        the next event-loop turn, which matters a lot during recompute
        of a large document.

        A tip drag is the one case where even that is too often. Moving the
        tip writes Tip, writes visibilities and recomputes, and every one of
        those reaches an observer - so each feature the bar crosses would
        re-walk the whole document, re-read every sketch's solver state and
        rebuild every row, to learn a handful of facts the bridge itself
        just wrote. The snapshot is patched in place instead (see
        `_apply_tip`), and the staleness is remembered until the drag ends.
        """
        self._icons_dirty = self._icons_dirty or icons
        self._dirty = True
        if self._tip_drag is None:
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
        self._restore_model_tips()
        self._tree.set_snapshot(self._snapshot, bump_icons=bump)
        self.sync_selection()
        # The snapshot may have replaced the node the mark was on, so the
        # model is told again rather than left holding a name from the
        # document that was open a moment ago.
        self._active = self._read_active()
        self._tree.set_active(self._active)
        if self._snapshot.doc_name != previous:
            self.documentChanged.emit()
        self.profileCountChanged.emit()
        self.problemCountChanged.emit()

    # ------------------------------------------------------------------ #
    # selection
    # ------------------------------------------------------------------ #

    def sync_selection(self, picked: bool = False) -> None:
        """Pull Gui.Selection into the model. Called by the observer.

        `picked` says the selection grew from outside the panel - a click
        in the 3D view, most often - and the rows it added should be
        brought into view; see _reveal_picked. The panel's own selections
        go through _push_selection, which this ignores while it runs.
        """
        if self._pushing_selection:
            return
        if self._origins:
            self._origins = []
            self.pickOriginsChanged.emit()
            self._arrows_timer.start()
        names: list[str] = []
        try:
            # Resolved (the default): a face picked on a Body's solid
            # gives the feature that made it, not the Body.
            for obj in Gui.Selection.getSelection(self._snapshot.doc_name):
                if obj.Name not in names:
                    names.append(obj.Name)
        except Exception:
            pass
        before = set(self._tree.selection())
        self._tree.set_selection(names)
        self._arrows_timer.start()
        if picked:
            added = [n for n in names
                     if n not in before and n in self._snapshot.nodes]
            if added:
                self._picked += [n for n in added if n not in self._picked]
                self._reveal_timer.start()

    def picked(self, doc_name: str, top: str, subname: str) -> None:
        """Something was picked outside the panel: reveal what made it.

        Called by the selection observer with what it was given. A face on
        a Body's solid is reported against the tip; picking.target goes
        back to the feature that made the face (see picking.py).
        """
        if self._pushing_selection:
            return
        full = subname
        try:
            top, full = picking.full_pick(
                top, subname, Gui.Selection.getSelectionEx(doc_name, 0))
            name = picking.target(App.getDocument(doc_name), top, full)
        except Exception:
            _err("could not trace the pick %s.%s" % (top, subname))
            name = None
        # Log level: shown in the Report view only with log messages on.
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
        """Whose links to draw, if anyone's.

        The feature a 3D pick traced to, else the one selected object;
        nothing when several are selected.
        """
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
                _err("could not work out the links of %s" % name)
        if arrows != self._arrows:
            self._arrows = arrows
            self.linkArrowsChanged.emit()

    def _reveal_picked(self) -> None:
        """Mark what made the pick; open its path, scroll to it, flash it.

        The mark is always made. Scrolling, and the flash that says where
        the list moved to, follow the "Show objects picked in the 3D view"
        setting - SolidWorks' "Scroll selected item into view". Scrolls to
        the first picked row in tree order, so a box selection lands at
        the top of what it caught; every picked row flashes.
        """
        picked, self._picked = self._picked, []
        picked = [n for n in picked if n in self._snapshot.nodes]
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
        self._pushing_selection = True
        try:
            if not additive:
                Gui.Selection.clearSelection()
            for name in names:
                if not scene.is_virtual(name):
                    Gui.Selection.addSelection(doc.Name, name)
        except Exception:
            _err("selection push failed")
        finally:
            self._pushing_selection = False
        self.sync_selection()

    @QtCore.Slot(str, bool)
    def select(self, name: str, additive: bool = False) -> None:
        self._anchor = self._cursor = name
        if additive:
            try:
                doc = App.ActiveDocument
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
            _err("clear selection failed")
        self.sync_selection()

    # ------------------------------------------------------------------ #
    # visibility
    # ------------------------------------------------------------------ #

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
            doc.openTransaction("Toggle visibility")
            vo.Visibility = not bool(vo.Visibility)
            doc.commitTransaction()
        except Exception:
            doc.abortTransaction()
            _err("visibility toggle failed for %s" % name)
        self.invalidate()

    # ------------------------------------------------------------------ #
    # tip
    # ------------------------------------------------------------------ #

    @QtCore.Slot(str)
    def beginTipDrag(self, body_name: str) -> None:
        """Start an interactive tip move.

        One transaction spans the whole drag, so a rollback that crossed six
        features is still a single undo step rather than six.
        """
        if self._tip_drag is not None:
            self.endTipDrag(self._tip_drag["body"])
        node = self._snapshot.nodes.get(body_name)
        doc = App.ActiveDocument
        if doc is None or node is None or not node.stack:
            return
        try:
            doc.openTransaction("Move tip")
        except Exception:
            _err("could not open a transaction for the tip drag")
            return
        self._tip_drag = {
            "body": body_name,
            "original": node.tip,
            "current": node.tip,    # what the document is actually showing
            "wanted": node.tip,     # which feature the bar would set
            "anchor": None,         # the row the bar is resting under
            "live": True,
            "applying": False,
            "ending": False,
        }

    @QtCore.Slot(str, int)
    def previewTipRow(self, body_name: str, row: int) -> None:
        """Note where the marker now is; the apply happens off this stack.

        Deliberately does not recompute here. This runs inside QML's delivery
        of a mouse-move event, and Qt's contract is that an exception must
        not propagate out of an event handler - it terminates the process
        rather than unwinding. A recompute on an old or damaged model is
        exactly where a feature throws, so the work is queued onto a
        zero-timer and performed from the event loop instead, where an
        exception has a Python frame to be caught in.

        Queuing also collapses a burst of moves: crossing four features
        while one recompute is still running applies only the last.
        """
        drag = self._tip_drag
        if drag is None or drag["body"] != body_name:
            return
        # Recorded before the early return, not after: a move between two
        # consecutive sketches changes where the bar is without changing
        # what it sets, and that is exactly the case this has to remember.
        drag["anchor"] = self._tree.name_at(row)
        name = self._tip_for_row(body_name, row)
        if name is None or name == drag["wanted"]:
            return

        drag["wanted"] = name
        if not drag["live"] or drag["applying"]:
            return  # the running apply picks this up when it drains
        self._drain_timer.start()

    def _drain_tip_drag(self) -> None:
        """Apply the marker's latest position until it stops moving.

        Apply the marker's latest position, repeatedly, until it stops
        moving. Re-entrant by design rather than by accident: a recompute
        can spin the event loop - FreeCAD's progress indicator calls
        processEvents - so another mouse move can arrive mid-apply. The
        guard turns that into another lap of this loop instead of a nested
        recompute on a document already inside one.
        """
        drag = self._tip_drag
        if drag is None or drag["applying"]:
            return

        drag["applying"] = True
        try:
            while (self._tip_drag is drag and not drag["ending"] and
                   drag["wanted"] != drag["current"]):
                target = drag["wanted"]
                started = time.perf_counter()
                if not self._apply_tip(drag["body"], target):
                    break
                drag["current"] = target

                # A heavy document can make a per-feature recompute slower
                # than the drag itself. Measure the real cost once and fall
                # back to commit-on-release rather than stuttering, or
                # queueing work faster than it can be done.
                if time.perf_counter() - started > LIVE_PREVIEW_BUDGET_S:
                    drag["live"] = False
                    App.Console.PrintMessage(
                        "Nxt: recompute is slow here, so the tip will update "
                        "on release rather than live\n")
                    break
        finally:
            drag["applying"] = False

    def _defer_finish(self, body_name: str, commit: bool) -> None:
        """Retry a finish once the apply that is on the stack has unwound."""
        self._pending_finish = (body_name, commit)
        self._finish_timer.start()

    def _finish_pending_drag(self) -> None:
        pending, self._pending_finish = self._pending_finish, None
        if pending is not None:
            self._finish_tip_drag(*pending)

    @QtCore.Slot(str)
    def endTipDrag(self, body_name: str) -> None:
        self._finish_tip_drag(body_name, commit=True)

    @QtCore.Slot(str)
    def cancelTipDrag(self, body_name: str) -> None:
        self._finish_tip_drag(body_name, commit=False)

    def _finish_tip_drag(self, body_name: str, commit: bool) -> None:
        drag = self._tip_drag
        if drag is None:
            return
        if drag["applying"]:
            # Closing the transaction from inside the apply would close it
            # in the middle of the change it is meant to contain: a
            # recompute spins the event loop, so the release can arrive
            # there. Let the apply unwind first.
            drag["ending"] = True
            self._defer_finish(body_name, commit)
            return

        self._tip_drag = None
        if commit and drag["anchor"]:
            self._bar_anchor[body_name] = drag["anchor"]
        elif not commit:
            self._bar_anchor.pop(body_name, None)

        doc = App.ActiveDocument
        try:
            if commit:
                self._commit_tip_drag(doc, drag, body_name)
            elif doc is not None:
                doc.abortTransaction()
                node = self._snapshot.nodes.get(body_name)
                if node is not None and node.is_model:
                    # Visibility is view state; undo does not restore it.
                    self._show_model_state(body_name, drag["original"])
                doc.recompute()
        except Exception:
            _err("could not finish the tip drag on %s" % body_name)
        self.invalidate(icons=True)
        self._publish_tip_bars()

    def _commit_tip_drag(self, doc: Any, drag: dict[str, Any],
                         body_name: str) -> None:
        # Whatever the live drain did not reach - because it was behind, or
        # because live preview had given up - is applied once here.
        if drag["wanted"] != drag["current"]:
            if self._apply_tip(body_name, drag["wanted"]):
                drag["current"] = drag["wanted"]
        if doc is None:
            return
        if drag["current"] == drag["original"]:
            doc.abortTransaction()      # nothing moved; no undo entry
        else:
            doc.commitTransaction()

    def _restore_model_tips(self) -> None:
        """Carry each model's history position across a rebuild.

        A Part model has no Tip property, so where its bar was is the
        panel's to remember. It is honoured only while the model has the
        same steps: a new operation always lands at the end, so the bar
        snaps back to the finished model rather than implying an insertion
        point that does not exist.
        """
        kept: dict[str, tuple[str, tuple[str, ...]]] = {}
        for name, (tip, stack) in self._model_tips.items():
            node = self._snapshot.nodes.get(name)
            if node is None or not node.is_model:
                continue
            if tuple(node.stack) == stack:
                self._snapshot.retip(name, tip)
                kept[name] = (tip, stack)
            else:
                self._pending_restore.append(name)
                self._bar_anchor.pop(name, None)
        self._model_tips = kept
        if self._pending_restore:
            self._restore_timer.start()

    def _show_finished_models(self) -> None:
        pending, self._pending_restore = self._pending_restore, []
        for name in pending:
            if name in self._snapshot.nodes:
                self._show_model_state(name, name)

    def _show_model_state(self, model_name: str, tip_name: str) -> None:
        doc = App.ActiveDocument
        if doc is None:
            return
        for name, (_built, shown) in self._snapshot.model_state(
                model_name, tip_name).items():
            vo = getattr(doc.getObject(name), "ViewObject", None)
            if vo is not None and bool(vo.Visibility) != shown:
                vo.Visibility = shown
        self._tree.touch(self._snapshot.retip(model_name, tip_name))
        if tip_name == model_name:
            self._model_tips.pop(model_name, None)
        else:
            self._model_tips[model_name] = (
                tip_name, tuple(self._snapshot.nodes[model_name].stack))

    def _apply_tip(self, body_name: str, feature_name: str) -> bool:
        """Set Tip and the stack's visibility.

        No transaction of its own - the caller owns that, whether it is
        a drag or a one-shot move.
        """
        doc = App.ActiveDocument
        if doc is None:
            return False
        body = doc.getObject(body_name)
        feature = doc.getObject(feature_name)
        body_node = self._snapshot.nodes.get(body_name)
        if body is None or feature is None or body_node is None:
            return False
        if body_node.is_model:
            try:
                self._show_model_state(body_name, feature_name)
                return True
            except Exception:
                _err("could not roll %s back to %s"
                     % (body_name, feature_name))
                return False
        try:
            body.Tip = feature
            # Only the visibilities that actually differ. A Body shows
            # through exactly one feature, so a move changes two of them -
            # writing all of them touched the document once per stack
            # member and woke an observer for each, which on a long history
            # was most of the cost of a drag step.
            for other in body_node.stack:
                obj = doc.getObject(other)
                vo = getattr(obj, "ViewObject", None)
                if vo is None:
                    continue
                wanted = (other == feature_name)
                if bool(getattr(vo, "Visibility", not wanted)) != wanted:
                    vo.Visibility = wanted
            self._recompute(doc, body)
            # Patch the snapshot rather than waiting for a rebuild that a
            # drag suppresses anyway. Everything a tip move changes is
            # derivable from what the snapshot already holds, and
            # `Snapshot.retip` is tested against a full rebuild so the two
            # cannot drift.
            self._tree.touch(self._snapshot.retip(body_name, feature_name))
            return True
        except Exception:
            _err("could not set the tip of %s to %s"
                 % (body_name, feature_name))
            return False

    @staticmethod
    def _recompute(doc: Any, body: Any) -> None:
        """Recompute the Body, not the document.

        Moving the tip touches the Body and nothing else - the features
        themselves are already up to date - so a whole-document recompute
        is work nobody asked for. It is also the difference between a
        recompute fast enough to pass unnoticed and one slow enough to
        raise FreeCAD's progress indicator, which spins the event loop and
        invites exactly the re-entrancy this drag path has to survive.
        """
        try:
            doc.recompute([body])
        except TypeError:
            doc.recompute()     # older signature, no object list

    @QtCore.Slot(str, int)
    def setTipToRow(self, body_name: str, row: int) -> None:
        name = self._tip_for_row(body_name, row)
        if name is not None:
            self.setTip(body_name, name)

    @QtCore.Slot(str, str)
    def setTip(self, body_name: str, feature_name: str) -> None:
        """Roll a Body's history to end at `feature_name`.

        Setting Tip is only half of it: FreeCAD shows a Body through exactly
        one visible feature, so the stock Move-tip command also hides every
        other member of the stack. Skip that and the Body keeps drawing the
        old state regardless of what Tip says.
        """
        doc = App.ActiveDocument
        if doc is None:
            return
        body = doc.getObject(body_name)
        feature = doc.getObject(feature_name)
        if body is None or feature is None:
            return

        node = self._snapshot.nodes.get(feature_name)
        body_node = self._snapshot.nodes.get(body_name)
        if node is None or body_node is None:
            return
        if node.body != body_name and feature_name != body_name:
            return              # not this Body's feature; refuse quietly
        if body_node.tip == feature_name:
            return

        # Moved by something other than the bar, so any place the bar was
        # resting is no longer a statement about this tip.
        self._bar_anchor.pop(body_name, None)
        try:
            doc.openTransaction("Move tip")
            if self._apply_tip(body_name, feature_name):
                doc.commitTransaction()
            else:
                doc.abortTransaction()
        except Exception:
            doc.abortTransaction()
            _err("could not move the tip of %s to %s"
                 % (body_name, feature_name))
        self.invalidate(icons=True)

    # ------------------------------------------------------------------ #
    # expansion
    # ------------------------------------------------------------------ #

    @QtCore.Slot(str, bool)
    def setExpanded(self, name: str, expanded: bool) -> None:
        self._tree.set_expanded(name, expanded)

    @QtCore.Slot(str)
    def toggleExpanded(self, name: str) -> None:
        self._tree.set_expanded(name, not self._tree.is_expanded(name))

    @QtCore.Slot()
    def expandAll(self) -> None:
        self._tree.expand_all()

    @QtCore.Slot()
    def collapseAll(self) -> None:
        self._tree.collapse_all()

    # ------------------------------------------------------------------ #
    # cross-panel navigation
    # ------------------------------------------------------------------ #

    @QtCore.Slot(str)
    def revealObjectRow(self, name: str) -> None:
        """Select an object and scroll its row into view, opening the path.

        One destination now. When profiles lived in a shelf this had to
        choose a half first, and the choice was the only reason two of
        these existed.
        """
        self._push_selection([name], False)
        self._tree.reveal(name)
        row = self._tree.row_of(name)
        if row >= 0:
            self.revealTreeRow.emit(row)

    @QtCore.Slot(str)
    def highlightRelated(self, name: str) -> None:
        """Point at a row, light up the rows it is related to.

        Both directions, in one list now that both live in it: hovering a
        profile marks every feature that consumes it, hovering a feature
        marks the profiles it reads. Timeline order puts a sketch near its
        consumer most of the time, but not when it is reused - which is
        exactly when this is worth having.
        """
        node = self._snapshot.nodes.get(name)
        if node is None:
            return
        self._highlight_source = name
        # Both directions at once, rather than picking one by what the row
        # is. A sketch that reads another sketch's external geometry has
        # consumers *and* references, and choosing between them meant the
        # panel answered a different question depending on which row was
        # under the pointer.
        related = [n for n, _l, _p in node.consumers]
        related += [n for n, _l, _s, _part in node.refs]
        self._tree.set_highlight(related)

    @QtCore.Slot(str)
    def clearHighlightFor(self, name: str) -> None:
        """Only the row that set the highlight may clear it.

        Moving between adjacent rows can deliver the new row's enter before
        the old row's exit, and an unconditional clear would then wipe the
        highlight that had just been set.
        """
        if self._highlight_source != name:
            return
        self.clearHighlight()

    @QtCore.Slot()
    def clearHighlight(self) -> None:
        self._highlight_source = None
        self._tree.set_highlight([])

    # ------------------------------------------------------------------ #
    # per-row detail
    # ------------------------------------------------------------------ #

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
        """Open the Property Inspector for `name` at a global position.

        `left` is the edge of the widest pill on screen when the panel is
        in the 3D view, and negative when docked, where the inspector lines
        up with the dock instead. The object is selected first: the borrowed
        editor always shows the selection.
        """
        from .. import property_inspector
        if name:
            self._push_selection([name], False)
        property_inspector.open_inspector(
            left=int(left) if left >= 0 else None,
            top=int(top) if top >= 0 else None)

    def request_property_inspector(self) -> None:
        """Open the inspector for the selection, from its row if it has one.

        The row knows where its edge is, so QML is asked to open it; with
        no row on screen the inspector opens with no anchor.
        """
        name = self._sole_selection()
        row = self._tree.row_of(name) if name else -1
        if row >= 0:
            self.propertyInspectorRequested.emit(row)
        else:
            self.openPropertyInspector(name or "", -1.0, -1.0)

    # ------------------------------------------------------------------ #
    # context menu
    # ------------------------------------------------------------------ #

    @QtCore.Slot(str, float, float)
    def requestContextMenu(self, name: str, x: float, y: float) -> None:
        """Right-click on a row: select it, then open the menu at (x, y).

        The point is in the panel's scene, not on the screen: under
        Wayland an application cannot read the pointer's position on the
        screen, so a menu told to open "at the pointer" opened in a corner.

        A row that is already part of the selection keeps the selection as
        it is, as every file manager does, so a menu can act on several.
        """
        if name and name not in self._selected_names():
            self.select(name, False)
        # Opened on the next turn of the event loop, not inside the press
        # that asked for it: the selection change above is still being
        # delivered to FreeCAD's observers, and the menu is built from it.
        QtCore.QTimer.singleShot(
            0, self, lambda: self.contextMenuRequested.emit(x, y))

    @QtCore.Slot(result=int)
    def contextMenuRow(self) -> int:
        """The row the keyboard's menu opens beside.

        The cursor's row if it is selected, else the first selected row;
        -1 with nothing selected.
        """
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
            _err("the context menu could not be built")
            return {}

    @QtCore.Slot(str)
    def runMenuItem(self, command: str) -> None:
        from . import menu_actions
        menu_actions.run(self, command, list(self._menu_names))

    @QtCore.Slot(str, result=bool)
    def toggleDetail(self, name: str) -> bool:
        """Open or close a row's detail strip."""
        return self._tree.toggle_detail(name)

    @QtCore.Slot(result=bool)
    def closeDetail(self) -> bool:
        """Escape: close the selected rows' strips, else every open one."""
        return (self._tree.close_details(self._selected_names())
                or self._tree.close_details())

    # ------------------------------------------------------------------ #
    # search
    # ------------------------------------------------------------------ #

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
        """Header count -> the first profile with something wrong with it."""
        problems = self._snapshot.problem_profiles()
        if problems:
            self.revealObjectRow(problems[0])
            self._tree.toggle_detail(problems[0], True)

    @QtCore.Slot(str)
    def revealObject(self, name: str) -> None:
        """Go to a search hit: select it, open the path to it, scroll it in."""
        if name in self._snapshot.nodes:
            self.revealObjectRow(name)

    # ------------------------------------------------------------------ #
    # rename
    # ------------------------------------------------------------------ #

    def _sole_selection(self) -> str | None:
        """The one selected object, or None.

        Keyboard actions work on the selection rather than on a list's
        current index, so the same key does the same thing wherever the
        row happens to be.
        """
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
        """Space: show or hide everything selected, as one undo step.

        All the same way rather than each flipped: with a mix of shown and
        hidden objects, flipping each would swap them, which is never what
        is wanted. If any is shown they are all hidden, otherwise shown.
        """
        doc = App.ActiveDocument
        if doc is None:
            return
        found = (getattr(doc.getObject(name), "ViewObject", None)
                 for name in self._selected_names())
        views: list[Any] = [vo for vo in found if vo is not None]
        if not views:
            return
        show = not any(bool(vo.Visibility) for vo in views)
        try:
            doc.openTransaction("Toggle visibility")
            for vo in views:
                vo.Visibility = show
            doc.commitTransaction()
        except Exception:
            doc.abortTransaction()
            _err("visibility toggle failed")
        self.invalidate()

    def _selected_names(self) -> list[str]:
        try:
            doc = App.ActiveDocument
            return [o.Name for o in Gui.Selection.getSelection(doc.Name)]
        except Exception:
            return []

    @QtCore.Slot(str)
    def selectRange(self, name: str) -> None:
        """Shift+click: every row from the anchor to `name`, inclusive.

        The anchor is the last row clicked without Shift, or moved to with
        an arrow key; without one, the range is just this row.
        """
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
        """Up/Down: select the row above or below; with Shift, extend.

        Moves from the last row stepped to or clicked, so repeated presses
        walk the list even while a range is selected. Returns the new row,
        for the view to scroll to, or -1 when there is nowhere to go.
        """
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

    @QtCore.Slot(int, result=int)
    def stepBranch(self, step: int) -> int:
        """Right/Left: open or close a branch, else move into or out of it.

        Right opens a closed branch, and on an open one moves to its first
        child. Left closes an open branch, and elsewhere moves to the
        parent. Acts on the row last stepped to or clicked. Returns the row
        now current, for the view to scroll to, or -1 when nothing moved.
        """
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
        """Set an object's Label.

        Label, not Name: Name is the immutable internal identifier every
        link in the document is written against, and the panel addresses
        rows by it. Renaming touches only what is displayed.
        """
        doc = App.ActiveDocument
        if doc is None:
            return
        obj = doc.getObject(name)
        label = (label or "").strip()
        if obj is None or not label or label == obj.Label:
            return
        try:
            doc.openTransaction("Rename")
            obj.Label = label
            doc.commitTransaction()
        except Exception:
            doc.abortTransaction()
            _err("could not rename %s" % name)
        self.invalidate()

    # ------------------------------------------------------------------ #
    # activation
    # ------------------------------------------------------------------ #

    @QtCore.Slot(str)
    def activate(self, name: str) -> None:
        """Double-click: open a container, edit anything else."""
        doc = App.ActiveDocument
        if doc is None:
            return
        node = self._snapshot.nodes.get(name)
        if node is not None and node.is_container and not node.is_lifted:
            self.toggleExpanded(name)
            return
        if doc.getObject(name) is None:
            return
        # Deferred: this is reached from a delegate's onDoubleClicked, and
        # setEdit opens a task dialog, which nests an event loop and tears
        # down docks. Anything that destroys the delegate while its handler
        # is still on the stack aborts the process.
        self._pending_edit = (doc.Name, name)
        self._edit_timer.start()

    def edit_feature(self, doc_name: str, name: str) -> None:
        """Mark and reveal a feature opened for editing outside the panel.

        Connected to `services.featurePicked` (a face double-clicked in the
        3D view). The edit itself is the services' job, so it happens with
        the panel closed too; this is only what the panel adds when open.
        """
        if doc_name != getattr(App.ActiveDocument, "Name", None):
            return
        if name in self._snapshot.nodes:
            if name not in self._picked:
                self._picked.append(name)
            self._reveal_timer.start()

    def _enter_pending_edit(self) -> None:
        pending, self._pending_edit = self._pending_edit, None
        if pending is not None:
            self._enter_edit(*pending)

    def _recompute_document(self) -> None:
        doc = App.ActiveDocument
        if doc is None:
            return
        try:
            doc.recompute()
        except Exception:
            _err("could not recompute after a drop")

    def _enter_edit(self, doc_name: str, name: str) -> None:
        """Edit an object inside an undo step of its own (editing.py)."""
        editing.enter_edit(doc_name, name)

    # ------------------------------------------------------------------ #
    # drag and drop
    # ------------------------------------------------------------------ #

    @QtCore.Slot(str, result="QVariantList")
    def dragNames(self, name: str) -> list[str]:  # noqa: N802
        """What a drag begun on this row carries, in tree order.

        The whole selection when the row is one of several selected - the
        gesture every file manager has - and otherwise the row alone.
        Selected objects with no row (inside a collapsed branch) stay
        where they are: nothing moves that was not visibly picked up.
        """
        selected = self._selected_names()
        if name not in selected or len(selected) < 2:
            return [name]
        rows = sorted((self._tree.row_of(n), n) for n in set(selected))
        names = [n for row, n in rows if row >= 0]
        return names if name in names and len(names) > 1 else [name]

    @QtCore.Slot("QVariantList", result=bool)
    def inOneBody(self, names: list[Any]) -> bool:  # noqa: N802
        """Are these all members of the same Part Design Body?

        Then dragging them is a reorder, and they slide as a group.
        """
        doc = App.ActiveDocument
        if doc is None or not names:
            return False
        try:
            bodies = {getattr(reorder.body_of(doc.getObject(str(n))),
                              "Name", None) for n in names}
        except Exception:
            return False
        return len(bodies) == 1 and None not in bodies

    @QtCore.Slot("QVariantList", str, result=bool)
    def canDropOn(self, sources: list[Any], target_name: str) -> bool:
        doc = App.ActiveDocument
        if doc is None or not sources:
            return False
        body, plan = self._body_reorder(sources, target_name)
        if body is not None:
            return plan.ok
        target = doc.getObject(target_name)
        tvo = getattr(target, "ViewObject", None)
        if tvo is None:
            return False
        try:
            probe = getattr(tvo, "canDropObjects", None)
            if callable(probe) and not probe():
                return False
        except Exception:
            return False
        for source_name in sources:
            source_name = str(source_name)
            if source_name == target_name:
                return False
            if self._snapshot.is_ancestor(target_name, source_name):
                return False
            source = doc.getObject(source_name)
            if source is None:
                return False
            try:
                check = getattr(tvo, "canDropObject", None)
                if callable(check) and not check(source):
                    return False
            except Exception:
                return False
        return True

    @QtCore.Slot("QVariantList", str, result=bool)
    def dropOn(self, sources: list[Any], target_name: str) -> bool:
        body, plan = self._body_reorder(sources, target_name)
        if body is not None:
            # Within a Body a drop reorders: onto a member, just after it;
            # onto the Body, first. See reorder.py.
            if not plan.ok:
                reorder.report(plan.problem)
                return False
            try:
                reorder.apply(body, plan)
            except Exception:
                _err("could not reorder %s" % body.Name)
                return False
            self.invalidate(icons=True)
            return True
        if not self.canDropOn(sources, target_name):
            return False
        doc = App.ActiveDocument
        target = doc.getObject(target_name)
        tvo = target.ViewObject
        moved = False
        try:
            doc.openTransaction("Move in tree")
            for source_name in sources:
                source = doc.getObject(str(source_name))
                if source is None:
                    continue
                self._detach(doc, source)
                drop = getattr(tvo, "dropObject", None)
                if callable(drop):
                    drop(source)
                    moved = True
            doc.commitTransaction()
        except Exception:
            doc.abortTransaction()
            _err("drop onto %s failed" % target_name)
            moved = False
        # Same reasoning as activate(): a recompute inside a drop handler can
        # spin the event loop through FreeCAD's progress indicator, and the
        # relayout that follows destroys the row the handler belongs to.
        self._recompute_timer.start()
        self.invalidate(icons=True)
        return moved

    # -- the document root: the header's name, empty space when docked ---- #

    @staticmethod
    def _container_of(source: Any) -> Any:
        """The group-like object that really holds `source`, or None.

        Asked of the document, not the snapshot: the panel lifts sketches
        out of the features that claim them, so a row's parent in the tree
        is not always the object that owns it.
        """
        for parent in getattr(source, "InList", None) or ():
            group = getattr(parent, "Group", None) or ()
            if any(getattr(g, "Name", None) == source.Name for g in group):
                return parent
        return None

    @staticmethod
    def _can_leave_body(source: Any, body: Any) -> bool:
        """May `source` leave its Body, though Part Design refuses the drag?

        Part Design refuses every drag out of a Body. That is right for its
        solid features, which are the Body's history, and for a sketch
        attached to the Body's planes or faces, which would lose them - but
        it also holds back a VarSet or a free-standing sketch, which depend
        on nothing in the Body and are often better kept outside it. So:
        never a solid feature, nothing that still links to anything in the
        Body, and nothing the Body's features are built on - except values
        they read through expressions.
        """
        if not getattr(body, "TypeId", "").startswith("PartDesign::Body"):
            return False
        try:
            if source.isDerivedFrom("PartDesign::Feature"):
                return False
        except Exception:
            return False
        inside = {o.Name for o in getattr(body, "Group", None) or ()}
        origin = getattr(body, "Origin", None)
        if origin is not None:
            inside.add(origin.Name)
            inside |= {o.Name for o in
                       getattr(origin, "OriginFeatures", None) or ()}
        inside.add(body.Name)
        try:
            needs = getattr(source, "OutListRecursive", None)
            needs = needs if needs is not None else source.OutList
        except Exception:
            return False
        if any(getattr(o, "Name", None) in inside for o in needs):
            return False
        # Used from inside the Body: a sketch a Pad is built on cannot move
        # out from under it. Values read through expressions - a VarSet, a
        # spreadsheet - are fine to read from outside the Body.
        used = any(getattr(o, "Name", None) in inside - {body.Name}
                   for o in getattr(source, "InList", None) or ())
        if used:
            kind = getattr(source, "TypeId", "")
            return kind in ("App::VarSet", "Spreadsheet::Sheet")
        return True

    @QtCore.Slot("QVariantList", result=bool)
    def canDropOnRoot(self, sources: list[Any]) -> bool:  # noqa: N802
        """Can these all leave their containers for the document's top?"""
        doc = App.ActiveDocument
        if doc is None or not sources:
            return False
        for name in sources:
            source = doc.getObject(str(name))
            parent = self._container_of(source) if source else None
            if parent is None:
                return False            # missing, or already at the top
            pvo = getattr(parent, "ViewObject", None)
            try:
                can = getattr(pvo, "canDragObject", None)
                if callable(can) and not can(source) \
                        and not self._can_leave_body(source, parent):
                    return False
            except Exception:
                return False
        return True

    @QtCore.Slot("QVariantList", result=bool)
    def dropOnRoot(self, sources: list[Any]) -> bool:  # noqa: N802
        """Move objects out of their containers to the document's top."""
        if not self.canDropOnRoot(sources):
            return False
        doc = App.ActiveDocument
        moved = False
        try:
            doc.openTransaction("Move to top level")
            for name in sources:
                source = doc.getObject(str(name))
                parent = self._container_of(source)
                pvo = getattr(parent, "ViewObject", None)
                can = getattr(pvo, "canDragObject", None)
                drag = getattr(pvo, "dragObject", None)
                if callable(drag) and (not callable(can) or can(source)):
                    drag(source)
                    moved = True
                elif self._can_leave_body(source, parent):
                    # Out of a Body its view provider will not release it
                    # from - see _can_leave_body.
                    parent.removeObject(source)
                    moved = True
            doc.commitTransaction()
        except Exception:
            doc.abortTransaction()
            _err("could not move to the top level")
            moved = False
        # Deferred, as dropOn's: see there.
        self._recompute_timer.start()
        self.invalidate(icons=True)
        return moved

    def _body_reorder(self, sources: list[Any],
                      target_name: str) -> tuple[Any, reorder.Plan]:
        """The Body and plan when this drop reorders a Body, else None."""
        doc = App.ActiveDocument
        objects = [doc.getObject(str(n)) for n in sources]
        target = doc.getObject(target_name)
        if target is None or any(o is None for o in objects):
            return None, reorder.Plan()
        try:
            return reorder.plan_drop(objects, target)
        except Exception:
            _err("could not plan a reorder onto %s" % target_name)
            return None, reorder.Plan()

    def _detach(self, doc: Any, source: Any) -> None:
        """Ask the current parent's view provider to release the object."""
        node = self._snapshot.nodes.get(source.Name)
        if node is None or not node.parent:
            return
        parent = doc.getObject(node.parent)
        pvo = getattr(parent, "ViewObject", None)
        if pvo is None:
            return
        try:
            can = getattr(pvo, "canDragObject", None)
            if callable(can) and not can(source):
                return
            drag = getattr(pvo, "dragObject", None)
            if callable(drag):
                drag(source)
        except Exception:
            _err("could not detach %s from %s" % (source.Name, node.parent))

    # ------------------------------------------------------------------ #

    @QtCore.Slot()
    def refresh(self) -> None:
        self.rebuild()
