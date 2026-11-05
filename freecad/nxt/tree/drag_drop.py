"""Dragging rows: what may go where, and moving objects when dropped."""

from __future__ import annotations

from typing import Any

import FreeCAD as App

from ..app.i18n import translate
from ..core import log
from ..core.transaction import transaction
from . import reorder


class DragDrop:
    """Drag and drop for the tree; TreeBridge's slots call into this."""

    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge

    @property
    def _snapshot(self) -> Any:
        return self._bridge._snapshot

    @property
    def _tree(self) -> Any:
        return self._bridge._tree

    def _toast(self, doc: Any, message: str) -> None:
        self._bridge._toast(doc, message)

    def _named(self, doc: Any, names: Any) -> str:
        return self._bridge._named(doc, names)

    def drag_names(self, name: str) -> list[str]:
        """Names a drag begun on this row carries, in tree order.

        The visible selection if the row is part of it, else the row alone.
        """
        selected = self._bridge._selected_names()
        if name not in selected or len(selected) < 2:
            return [name]
        rows = sorted((self._tree.row_of(n), n) for n in set(selected))
        names = [n for row, n in rows if row >= 0]
        return names if name in names and len(names) > 1 else [name]

    def slide_container(self, names: list[Any]) -> str:
        """The Body or group a drag of `names` reorders within, or ""."""
        doc = App.ActiveDocument
        if doc is None or not names:
            return ""
        objects = [doc.getObject(str(n)) for n in names]
        if any(o is None for o in objects):
            return ""
        for find in (reorder.body_of, reorder.group_of):
            try:
                holders = {getattr(find(o), "Name", None) for o in objects}
            except Exception:  # nosec B112  # no such holder
                continue
            if len(holders) == 1 and None not in holders:
                return str(holders.pop())
        return ""

    def can_reorder_on(self, sources: list[Any], target_name: str) -> bool:
        """May `sources` go after the row, or first on their container?"""
        body, plan = self._body_reorder(sources, target_name)
        if body is None:
            body, plan = self._group_reorder(sources, target_name)
        if body is None:
            return self._to_top_beside(sources, target_name)
        return plan.ok

    def _to_top_beside(self, sources: list[Any], target_name: str) -> bool:
        """Is the row at the top level, and may `sources` join it there?

        The document's own order is not the user's to set, so this only
        moves them out of their containers.
        """
        doc = App.ActiveDocument
        target = doc.getObject(target_name) if doc is not None else None
        return (target is not None and self._container_of(target) is None
                and not self._can_drop_into(sources, target_name)
                and self.can_drop_on_root(sources))

    def can_drop_into(self, sources: list[Any], target_name: str) -> bool:
        """Would the row take `sources` inside, not being their container?"""
        if target_name in {self.slide_container(sources)}:
            return False
        if self._body_reorder(sources, target_name)[0] is not None:
            return False        # a Body's own members reorder, never nest
        return self._can_drop_into(sources, target_name)

    def reorder_on(self, sources: list[Any], target_name: str) -> bool:
        """Place `sources` after the row, or first on their container."""
        body, plan = self._body_reorder(sources, target_name)
        if body is not None:
            return self.drop_on(sources, target_name)
        container, group_plan = self._group_reorder(sources, target_name)
        if container is None and self._to_top_beside(sources, target_name):
            return self.drop_on_root(sources)
        if container is None or not group_plan.ok:
            return False
        try:
            reorder.apply_group(container, group_plan)
        except Exception:
            log.error("could not reorder %s" % container.Name)
            return False
        what = self._named(container.Document, group_plan.moving)
        self._toast(container.Document, translate(
            "Nxt", "Moved %s to the start of %s")
            % (what, container.Label) if target_name == container.Name
            else translate("Nxt", "Moved %s after %s")
            % (what, self._named(container.Document, [target_name])))
        self._bridge.invalidate(icons=True)
        return True

    def drop_into(self, sources: list[Any], target_name: str) -> bool:
        """Put `sources` inside the row's object."""
        if not self.can_drop_into(sources, target_name):
            return False
        return self._move_into(sources, target_name)

    def drop_hint(self, sources: list[Any], target_name: str) -> str:
        """Describe what dropping `sources` on this row does; "" if not."""
        doc = App.ActiveDocument
        if doc is None or not sources:
            return ""
        target = doc.getObject(target_name)
        label = getattr(target, "Label", target_name)
        body, plan = self._body_reorder(sources, target_name)
        if body is not None:
            if not plan.ok:
                return ""
            return (translate("Nxt", "To the start of %s") % label
                    if target_name == body.Name
                    else translate("Nxt", "After %s") % label)
        container, group_plan = self._group_reorder(sources, target_name)
        into = self._can_drop_into(sources, target_name)
        if container is not None and (target_name == container.Name
                                      or not into):
            if not group_plan.ok:
                return ""
            return (translate("Nxt", "To the start of %s") % label
                    if target_name == container.Name
                    else translate("Nxt", "After %s") % label)
        if into:
            return translate("Nxt", "Into %s") % label
        if self._to_top_beside(sources, target_name):
            return translate("Nxt", "To the top level")
        return ""

    def _group_reorder(self, sources: list[Any], target_name: str
                       ) -> tuple[Any, reorder.Plan]:
        doc = App.ActiveDocument
        if doc is None:
            return None, reorder.Plan()
        objects = [doc.getObject(str(n)) for n in sources]
        target = doc.getObject(target_name)
        if target is None or any(o is None for o in objects):
            return None, reorder.Plan()
        try:
            return reorder.plan_group_drop(objects, target)
        except Exception:
            log.error("could not plan a reorder onto %s" % target_name)
            return None, reorder.Plan()

    def _can_drop_into(self, sources: list[Any], target_name: str) -> bool:
        """Would the row's object take `sources` inside it?"""
        doc = App.ActiveDocument
        if doc is None or not sources:
            return False
        target = doc.getObject(target_name)
        tvo = getattr(target, "ViewObject", None)
        if tvo is None:
            return False
        try:
            # Asked of no object, it says whether the row takes any.
            probe = getattr(tvo, "canDropObject", None)
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

    def drop_on(self, sources: list[Any], target_name: str) -> bool:
        body, plan = self._body_reorder(sources, target_name)
        if body is not None:
            if not plan.ok:
                reorder.report(plan.problem)
                return False
            try:
                reorder.apply(body, plan)
            except Exception:
                log.error("could not reorder %s" % body.Name)
                return False
            what = self._named(body.Document, plan.moving)
            if target_name == body.Name:
                self._toast(body.Document, translate(
                    "Nxt", "Moved %s to the start of %s")
                    % (what, body.Label))
            else:
                self._toast(body.Document, translate(
                    "Nxt", "Moved %s after %s")
                    % (what, self._named(body.Document, [target_name])))
            self._bridge.invalidate(icons=True)
            return True
        container, group_plan = self._group_reorder(sources, target_name)
        if container is not None and (
                target_name == container.Name
                or not self._can_drop_into(sources, target_name)):
            if not group_plan.ok:
                return False
            try:
                reorder.apply_group(container, group_plan)
            except Exception:
                log.error("could not reorder %s" % container.Name)
                return False
            what = self._named(container.Document, group_plan.moving)
            self._toast(container.Document, translate(
                "Nxt", "Moved %s to the start of %s")
                % (what, container.Label) if target_name == container.Name
                else translate("Nxt", "Moved %s after %s")
                % (what, self._named(container.Document, [target_name])))
            self._bridge.invalidate(icons=True)
            return True
        if self._can_drop_into(sources, target_name):
            return self._move_into(sources, target_name)
        if self._to_top_beside(sources, target_name):
            return self.drop_on_root(sources)
        return False

    def _move_into(self, sources: list[Any], target_name: str) -> bool:
        doc = App.ActiveDocument
        if doc is None:
            return False
        target = doc.getObject(target_name)
        tvo = target.ViewObject
        moved = False
        try:
            with transaction(doc, "Move in tree"):
                for source_name in sources:
                    source = doc.getObject(str(source_name))
                    if source is None:
                        continue
                    self._detach(doc, source)
                    drop = getattr(tvo, "dropObject", None)
                    if callable(drop):
                        drop(source)
                        moved = True
            if moved:
                self._toast(doc, translate("Nxt", "Moved %s into %s")
                            % (self._named(doc, sources), target.Label))
        except Exception:
            log.error("drop onto %s failed" % target_name)
            moved = False
        # Deferred: recomputing here can destroy this row's QML delegate
        # inside its own handler.
        self._bridge._recompute_timer.start()
        self._bridge.invalidate(icons=True)
        return moved

    @staticmethod
    def _container_of(source: Any) -> Any:
        """The group-like object that really holds `source`, or None.

        Asks the document: a row's tree parent may not be its owner.
        """
        for parent in getattr(source, "InList", None) or ():
            group = getattr(parent, "Group", None) or ()
            if any(getattr(g, "Name", None) == source.Name for g in group):
                return parent
        return None

    @staticmethod
    def _can_leave_body(source: Any, body: Any) -> bool:
        """May `source` leave its Body, though Part Design refuses the drag?

        Only non-features that link to nothing in the Body and that no
        member uses, except VarSets and spreadsheets read by expression.
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
        used = any(getattr(o, "Name", None) in inside - {body.Name}
                   for o in getattr(source, "InList", None) or ())
        if used:
            kind = getattr(source, "TypeId", "")
            return kind in ("App::VarSet", "Spreadsheet::Sheet")
        return True

    def can_drop_on_root(self, sources: list[Any]) -> bool:
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

    def drop_on_root(self, sources: list[Any]) -> bool:
        """Move objects out of their containers to the document's top."""
        if not self.can_drop_on_root(sources):
            return False
        doc = App.ActiveDocument
        if doc is None:
            return False
        moved = False
        try:
            with transaction(doc, "Move to top level"):
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
                        parent.removeObject(source)
                        moved = True
            if moved:
                self._toast(doc, translate(
                    "Nxt", "Moved %s to the top level")
                    % self._named(doc, sources))
        except Exception:
            log.error("could not move to the top level")
            moved = False
        # Deferred for the same reason as in _move_into.
        self._bridge._recompute_timer.start()
        self._bridge.invalidate(icons=True)
        return moved

    def _body_reorder(self, sources: list[Any],
                      target_name: str) -> tuple[Any, reorder.Plan]:
        """The Body and plan when this drop reorders a Body, else None."""
        doc = App.ActiveDocument
        if doc is None:
            return None, reorder.Plan()
        objects = [doc.getObject(str(n)) for n in sources]
        target = doc.getObject(target_name)
        if target is None or any(o is None for o in objects):
            return None, reorder.Plan()
        try:
            return reorder.plan_drop(objects, target)
        except Exception:
            log.error("could not plan a reorder onto %s" % target_name)
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
                # A Body refuses every drag; some objects may leave anyway.
                if self._can_leave_body(source, parent):
                    parent.removeObject(source)
                return
            drag = getattr(pvo, "dragObject", None)
            if callable(drag):
                drag(source)
        except Exception:
            log.error("could not detach %s from %s"
                      % (source.Name, node.parent))
