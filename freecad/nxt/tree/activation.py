"""Double-click in the tree: activate a container or open an edit."""

from __future__ import annotations

import contextlib
from typing import Any

import FreeCAD as App

from ..core import fc, log, settings
from ..tools import editing

#: Types whose task opens through FreeCAD's double-click, not an edit.
DOUBLE_CLICKED = frozenset({"Image::ImagePlane"})


def opens_itself(obj: Any) -> bool:
    """Whether its view provider opens it on a double-click, not an edit.

    A Python one with doubleClicked but no setEdit (an Assembly
    Simulation, say): editing it would do nothing.
    """
    if getattr(obj, "TypeId", "") in DOUBLE_CLICKED:
        return True
    proxy = getattr(getattr(obj, "ViewObject", None), "Proxy", None)
    return callable(getattr(proxy, "doubleClicked", None)) \
        and not callable(getattr(proxy, "setEdit", None))


def active_key(obj: Any) -> str:
    """The key FreeCAD keeps this kind of active container under."""
    type_id = str(getattr(obj, "TypeId", ""))
    if type_id == "PartDesign::Body":
        return "pdbody"
    if type_id.startswith("Assembly::Assembly"):
        return "assembly"
    with contextlib.suppress(Exception):
        if obj.isDerivedFrom("App::Part"):
            return "part"
    return ""


class Activation:
    """Double-click handling for the tree; TreeBridge's slot calls this."""

    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge
        self._pending_active = ""
        self._pending_edit: tuple[str, str] | None = None
        self._activate_timer = bridge._deferral(self._activate_pending)
        self._edit_timer = bridge._deferral(self._enter_pending_edit)
        self._pending_inspect = ""
        self._pending_native = ""
        self._native_timer = bridge._deferral(self._native_pending)
        self._inspect_timer = bridge._deferral(self._inspect_pending)

    @property
    def _snapshot(self) -> Any:
        return self._bridge._snapshot

    def activate(self, name: str) -> None:
        """Double-click: activate or toggle a container, edit anything else."""
        doc = App.ActiveDocument
        if doc is None or editing.is_reference_pick(doc.getObject(name)):
            return
        node = self._snapshot.nodes.get(name)
        obj = doc.getObject(name)
        if node is not None and node.is_container and not node.is_lifted:
            key = active_key(obj)
            if key and name != self._current(key):
                # Deferred: activating can switch workbench or open a task.
                self._pending_active = name
                self._activate_timer.start()
                return
            if key or not opens_itself(obj):
                self._bridge.toggleExpanded(name)
                return
        if obj is None:
            return
        if opens_itself(obj):
            # Their view provider's own double-click opens their task;
            # editing them instead opens a bare transform.
            self._pending_native = name
            self._native_timer.start()
            return
        if getattr(obj, "TypeId", "") == "App::VarSet":
            # Its variables are its content: show them in the inspector.
            self._pending_inspect = name
            self._inspect_timer.start()
            return
        # Deferred: setEdit nests an event loop and can destroy the
        # delegate inside its own onDoubleClicked, which aborts QML.
        self._pending_edit = (doc.Name, name)
        self._edit_timer.start()

    def _native_pending(self) -> None:
        """Run FreeCAD's own double-click on the object."""
        name, self._pending_native = self._pending_native, ""
        doc = App.ActiveDocument
        obj = doc.getObject(name) if doc is not None and name else None
        view = getattr(obj, "ViewObject", None)
        if view is None:
            return
        try:
            view.doubleClicked()
        except Exception:
            log.error("could not open %s" % name)

    def _inspect_pending(self) -> None:
        """Open the Property Inspector on the double-clicked VarSet."""
        name, self._pending_inspect = self._pending_inspect, ""
        if not name:
            return
        self._bridge._push_selection([name], False)
        self._bridge.request_property_inspector()

    def _current(self, key: str) -> str:
        """The container active under `key`'s mark: outer or inner."""
        return (self._bridge._active_part if key in self._bridge.OUTER_KEYS
                else self._bridge._active)

    def toggle_active(self, name: str) -> None:
        """Make active, as double-click does; again to deactivate."""
        doc = App.ActiveDocument
        obj = doc.getObject(name) if doc is not None else None
        key = active_key(obj)
        if not key:
            return
        if self._current(key) != name:
            self._pending_active = name
            self._activate_timer.start()
            return
        try:
            view = fc.active_view()
            if view is not None:
                view.setActiveObject(key, None)
        except Exception:
            log.error("could not deactivate %s" % name)
        self._bridge._sync_active()

    def _activate_pending(self) -> None:
        """Make the double-clicked container the active one."""
        name, self._pending_active = self._pending_active, ""
        doc = App.ActiveDocument
        obj = doc.getObject(name) if doc is not None and name else None
        key = active_key(obj)
        if obj is None or not key:
            return
        with contextlib.suppress(Exception):
            obj.ViewObject.doubleClicked()
        try:
            view = fc.active_view()
            if self._bridge._read_active((key,)) != name \
                    and view is not None:
                view.setActiveObject(key, obj)
        except Exception:
            log.error("could not make %s active" % name)
        self._bridge._sync_active()

    def _enter_pending_edit(self) -> None:
        pending, self._pending_edit = self._pending_edit, None
        if pending is not None:
            self._enter_edit(*pending)

    def _enter_edit(self, doc_name: str, name: str) -> None:
        """Edit an object inside an undo step of its own (editing.py)."""
        editing.open_for_edit(
            doc_name, name,
            handles=not settings.get("TreeEditHidesHandles"))
