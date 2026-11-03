"""The rollback bars: where each sits, dragging one, and moving the tip."""

from __future__ import annotations

from typing import Any

import FreeCAD as App

from ..app.i18n import translate
from ..core import log
from ..core.qt import QtCore

#: Where a Body's bar sets no tip: above its first feature.
NO_TIP = ""
#: Objects made but not yet placed against the bar, at most.
MAX_PENDING = 64


class Rollback:
    """Rollback bars for the tree; TreeBridge's slots call into this."""

    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge
        self.drag: dict[str, Any] | None = None
        # Body -> object whose row its bar rests under (row indices shift
        # on expand); honoured only while it still resolves to the tip.
        self._bar_anchor: dict[str, str] = {}
        # model -> (tip, steps it was set against)
        self._model_tips: dict[str, tuple[str, tuple[str, ...]]] = {}
        self._pending_restore: list[str] = []
        #: Objects just made: a Body's bar moves below each, as below a
        #: new feature, if it lands where the bar rests.
        self._created: list[str] = []
        self._pending_finish: tuple[str, bool] | None = None
        self._bars_timer = bridge._deferral(bridge.tipBarsChanged.emit)
        self._drain_timer = bridge._deferral(self._drain_tip_drag)
        self._finish_timer = bridge._deferral(self._finish_pending_drag)
        self._restore_timer = bridge._deferral(self._show_finished_models)

    @property
    def _snapshot(self) -> Any:
        return self._bridge._snapshot

    @property
    def _tree(self) -> Any:
        return self._bridge._tree

    def publish(self) -> None:
        """Announce new marker positions on the next event-loop turn.

        Deferred: QML aborts if a delegate is destroyed inside its own
        handler, and this is reached from a marker's `onReleased`.
        """
        self._bars_timer.start()

    def created(self, name: str) -> None:
        """An object was made: placed against its Body's bar at next look."""
        self._created = [*self._created[-MAX_PENDING:], name]

    def bars(self) -> list[dict[str, Any]]:
        """The rollback bars: every Body's, and each Part model's.

        `pos` is the row the bar sits below. A Body's bar goes anywhere
        among its children, above the first feature too (no tip); a
        Part model's, from its first step to its last.
        """
        index = self._tree.row_index_map()
        self._place_created(index)
        bars: list[dict[str, Any]] = []
        dimmed: list[str] = []
        for name, node in self._snapshot.nodes.items():
            if not node.stack:
                continue
            feature_rows = [index[f] for f in node.stack if f in index]
            if not feature_rows:
                continue
            child_rows = [index[c] for c in node.children if c in index]
            first_feature = min(feature_rows)
            last_child = max(child_rows) if child_rows else max(feature_rows)
            top = (first_feature if node.is_model
                   else self._top_row(name, node, index, first_feature))
            pos = self._resting_position(name, node, index)
            if pos is None and node.is_model and node.tip == name:
                pos = max(feature_rows)
            if pos is None:
                pos = index.get(node.tip) if node.tip else None
            if pos is None:
                pos = top
            if not node.is_model:
                dimmed += self._dim_past(node, index, pos)
            bars.append({
                "body": name,
                "label": node.label,
                "pos": pos,
                "minPos": top,
                "maxPos": max(last_child, first_feature),
                "depth": self._tree.depth_at(first_feature),
            })
        if dimmed:
            # Not inside the property read that asked for the bars.
            QtCore.QTimer.singleShot(0, lambda: self._tree.touch(dimmed))
        return bars

    def _top_row(self, name: str, node: Any, index: dict[str, int],
                 first_feature: int) -> int:
        """The highest a Body's bar goes.

        Under the Body, and below its Origin, which every feature uses.
        """
        top = index.get(name, first_feature - 1)
        for child in node.children:
            row = index.get(child)
            kid = self._snapshot.nodes.get(child)
            if row is None or kid is None or not kid.is_coordinate_system:
                break
            top = row
        return min(top, first_feature)

    def _dim_past(self, node: Any, index: dict[str, int],
                  pos: int) -> list[str]:
        """Timeline rows below the bar drawn as past the tip; the rest not.

        Features follow the tip already; this keeps sketches and other
        lifted rows between the tip and the bar from looking rolled back.
        """
        changed = []
        for child in node.children:
            kid = self._snapshot.nodes.get(child)
            row = index.get(child)
            if kid is None or row is None or kid.is_feature \
                    or not kid.is_lifted:
                continue
            past = row > pos
            if kid.after_tip != past:
                kid.after_tip = past
                changed.append(child)
        return changed

    def _place_created(self, index: dict[str, int]) -> None:
        """A Body's bar moves below an object just made where it rests.

        As FreeCAD moves the tip to a new feature: a new sketch, binder or
        datum placed at the bar takes the bar below it; the tip is kept.
        """
        waiting = []
        for name in self._created:
            node = self._snapshot.nodes.get(name)
            if node is None:
                waiting.append(name)
                continue
            body = self._snapshot.nodes.get(node.body or "")
            row = index.get(name)
            if body is None or body.is_model or node.is_feature \
                    or row is None:
                continue
            if self.tip_for_row(node.body, row) == (body.tip or NO_TIP):
                self._bar_anchor[node.body] = name
        self._created = waiting[-MAX_PENDING:]

    def _resting_position(self, name: str, node: Any,
                          index: dict[str, int]) -> int | None:
        """Where the bar was last put down, if it still sets this tip."""
        anchor = self._bar_anchor.get(name)
        resting = index.get(anchor) if anchor is not None else None
        if (resting is not None and self.tip_for_row(name, resting)
                == (node.tip or (NO_TIP if not node.is_model else None))):
            return resting
        return None

    def tip_for_row(self, body_name: str, row: int) -> str | None:
        """The feature a bar dropped below `row` sets.

        NO_TIP above a Body's first feature; None outside the Body.
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
            if name == body_name:
                return None if node.is_model else NO_TIP
            cursor -= 1
        return None

    def begin_drag(self, body_name: str) -> None:
        """Start an interactive tip move.

        One transaction spans the drag, so it is a single undo step.
        """
        if self.drag is not None:
            self.end_drag(self.drag["body"])
        node = self._snapshot.nodes.get(body_name)
        doc = App.ActiveDocument
        if doc is None or node is None or not node.stack:
            return
        try:
            doc.openTransaction("Move tip")
        except Exception:
            log.error("could not open a transaction for the tip drag")
            return
        tip = node.tip or (None if node.is_model else NO_TIP)
        self.drag = {
            "body": body_name,
            "original": tip,
            "current": tip,         # what the document is actually showing
            "wanted": tip,          # which feature the bar would set
            "anchor": None,         # the row the bar is resting under
            "live": True,
            "applying": False,
            "ending": False,
        }

    def preview_row(self, body_name: str, row: int) -> None:
        """Note where the marker now is; the apply is queued.

        An exception escaping a Qt event handler kills the process, so the
        apply runs from the event loop, not this mouse-move.
        """
        drag = self.drag
        if drag is None or drag["body"] != body_name:
            return
        # Before the early return: a move between sketches changes where
        # the bar rests without changing what it sets.
        drag["anchor"] = self._tree.name_at(row)
        name = self.tip_for_row(body_name, row)
        if name is None or name == drag["wanted"]:
            return

        drag["wanted"] = name
        if not drag["live"] or drag["applying"]:
            return  # the running apply picks this up when it drains
        self._drain_timer.start()

    def _drain_tip_drag(self) -> None:
        """Apply the marker's latest position until it stops moving.

        Recompute spins the event loop, so moves can arrive mid-apply; the
        guard turns them into another lap instead of a nested recompute.
        """
        drag = self.drag
        if drag is None or drag["applying"]:
            return

        drag["applying"] = True
        try:
            while (self.drag is drag and not drag["ending"] and
                   drag["wanted"] != drag["current"]):
                target = drag["wanted"]
                # Shown, not set: Tip is set once on release.
                if not self._preview_tip(drag["body"], target):
                    break
                drag["current"] = target
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

    def end_drag(self, body_name: str) -> None:
        self._finish_tip_drag(body_name, commit=True)

    def cancel_drag(self, body_name: str) -> None:
        self._finish_tip_drag(body_name, commit=False)

    def _finish_tip_drag(self, body_name: str, commit: bool) -> None:
        drag = self.drag
        if drag is None:
            return
        if drag["applying"]:
            # Released mid-apply (recompute spins the event loop): let the
            # apply unwind before closing the transaction.
            drag["ending"] = True
            self._defer_finish(body_name, commit)
            return

        self.drag = None
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
                # Visibility is view state; abort does not restore it.
                if drag["current"] != drag["original"]:
                    self._preview_tip(body_name, drag["original"])
        except Exception:
            log.error("could not finish the tip drag on %s" % body_name)
        self._bridge.invalidate(icons=True)
        self.publish()

    def _commit_tip_drag(self, doc: Any, drag: dict[str, Any],
                         body_name: str) -> None:
        wanted = drag["wanted"]
        if wanted == drag["original"]:
            if drag["current"] != wanted:
                self._preview_tip(body_name, wanted)
            if doc is not None:
                doc.abortTransaction()  # nothing moved; no undo entry
            return
        if not self._apply_tip(body_name, wanted):
            self._preview_tip(body_name, drag["original"])
            if doc is not None:
                doc.abortTransaction()
            return
        if doc is not None:
            doc.commitTransaction()
            self._toast_tip(doc, body_name, wanted)

    def _preview_tip(self, body_name: str, feature_name: str) -> bool:
        """Show the Body as it would be with this tip, without setting it."""
        node = self._snapshot.nodes.get(body_name)
        doc = App.ActiveDocument
        if node is None or doc is None:
            return False
        if node.is_model:
            return self._apply_tip(body_name, feature_name)
        try:
            for other in node.stack:
                vo = getattr(doc.getObject(other), "ViewObject", None)
                if vo is None:
                    continue
                wanted = other == feature_name
                if bool(getattr(vo, "Visibility", not wanted)) != wanted:
                    vo.Visibility = wanted
            self._tree.touch(self._snapshot.retip(body_name,
                                                  feature_name or None))
            return True
        except Exception:
            log.error("could not show %s at %s" % (body_name, feature_name))
            return False

    def restore_model_tips(self) -> None:
        """Carry each model's history position across a rebuild.

        Part models have no Tip; the position is kept only while the steps
        are unchanged.
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
        """Set Tip and stack visibility; the caller owns the transaction."""
        doc = App.ActiveDocument
        if doc is None:
            return False
        body = doc.getObject(body_name)
        feature = doc.getObject(feature_name) if feature_name else None
        body_node = self._snapshot.nodes.get(body_name)
        if body is None or body_node is None or (
                feature is None and (feature_name or body_node.is_model)):
            return False
        if body_node.is_model:
            try:
                self._show_model_state(body_name, feature_name)
                return True
            except Exception:
                log.error("could not roll %s back to %s"
                          % (body_name, feature_name))
                return False
        try:
            body.Tip = feature
            # Only write visibilities that differ; each write wakes
            # observers.
            for other in body_node.stack:
                obj = doc.getObject(other)
                vo = getattr(obj, "ViewObject", None)
                if vo is None:
                    continue
                wanted = (other == feature_name)
                if bool(getattr(vo, "Visibility", not wanted)) != wanted:
                    vo.Visibility = wanted
            self._recompute(doc, body)
            # Patch the snapshot; a drag suppresses rebuilds.
            self._tree.touch(self._snapshot.retip(body_name,
                                                  feature_name or None))
            return True
        except Exception:
            log.error("could not set the tip of %s to %s"
                      % (body_name, feature_name))
            return False

    @staticmethod
    def _recompute(doc: Any, body: Any) -> None:
        """Recompute the Body, not the document.

        A slow recompute raises the progress indicator, which spins the
        event loop and invites re-entrancy.
        """
        try:
            doc.recompute([body])
        except TypeError:
            doc.recompute()     # older signature, no object list

    def set_tip(self, body_name: str, feature_name: str) -> None:
        """Roll a Body's history to end at `feature_name`.

        A Body draws through its one visible feature, so the other stack
        members are hidden too.
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

        self._bar_anchor.pop(body_name, None)
        try:
            doc.openTransaction("Move tip")
            if self._apply_tip(body_name, feature_name):
                doc.commitTransaction()
                self._toast_tip(doc, body_name, feature_name)
            else:
                doc.abortTransaction()
        except Exception:
            doc.abortTransaction()
            log.error("could not move the tip of %s to %s"
                      % (body_name, feature_name))
        self._bridge.invalidate(icons=True)

    def _toast_tip(self, doc: Any, body_name: str,
                   feature_name: str | None) -> None:
        node = self._snapshot.nodes.get(body_name)
        if node is not None and node.is_model:
            return      # a Part model's bar is a view; there is no undo
        body = self._bridge._named(doc, [body_name])
        message = (translate("Nxt", "Tip of %s moved to %s") % (
            body, self._bridge._named(doc, [feature_name]))
            if feature_name else
            translate("Nxt", "%s rolled back to its start") % body)
        self._bridge._toast(doc, message, body_name)

    def show_through_tip(self, body_name: str, doc: Any) -> None:
        """Show a Body through its tip again after an undo.

        Undo restores Tip but not visibility, which is view state.
        """
        body = doc.getObject(body_name)
        if body is None:
            return
        tip = getattr(getattr(body, "Tip", None), "Name", None)
        for other in getattr(
                self._snapshot.nodes.get(body_name), "stack", ()):
            vo = getattr(doc.getObject(other), "ViewObject", None)
            if vo is not None and bool(vo.Visibility) != (other == tip):
                vo.Visibility = other == tip
