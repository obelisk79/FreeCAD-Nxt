"""What the menu's conditions are tested against, read from FreeCAD.

Most facts come from the tree's snapshot, which has already worked them
out for drawing (failures, the tip, solver findings, what reads what); the
rest are asked of the object. Every read is guarded: a fact that cannot be
read is simply absent, which at worst leaves an item out of the menu.
"""

from __future__ import annotations

from typing import Any

from ..tree import health
from .definitions import ObjectFacts


def type_chain(type_id: str) -> tuple[str, ...]:
    """`type_id` followed by every type it derives from."""
    chain = [type_id] if type_id else []
    try:
        from FreeCAD import Base
        kind = Base.TypeId.fromName(type_id)
        while True:
            kind = kind.getParent()
            if kind.isBad():
                break
            chain.append(str(kind.Name))
    except Exception:
        pass
    return tuple(chain)


def of(obj: Any, node: Any = None, nodes: dict[str, Any] | None = None
       ) -> ObjectFacts:
    """The facts for one object.

    `node` is the object's entry in the tree's snapshot and `nodes` the
    snapshot's table, for the owning Body; without them only what the
    object itself reports is known.
    """
    flags: set[str] = set()
    type_id = str(getattr(obj, "TypeId", ""))

    if node is not None:
        if node.in_error:
            flags.add("failed")
        if node.after_tip:
            flags.add("past_tip")
        body = (nodes or {}).get(node.body or "")
        if body is not None and getattr(body, "tip", None) == node.name:
            flags.add("is_tip")
        if (type_id.startswith("Sketcher::")
                and node.severity >= health.WARNING):
            flags.add("solver_issues")
        if node.consumers:
            flags.add("has_dependents")
        if node.refs or node.inputs:
            flags.add("has_inputs")
        if node.touched:
            flags.add("out_of_date")
    # Anything a Body holds - sketches and datums too, not only the solid
    # feature stack the snapshot tracks.
    in_body = bool(node is not None and (node.body or node.is_feature)) \
        or _guard(lambda: obj.getParentGeoFeatureGroup().TypeId
                  == "PartDesign::Body")

    if _guard(lambda: len(obj.ExpressionEngine) > 0):
        flags.add("has_expression")
    if _guard(lambda: _placement_editable(obj)):
        flags.add("editable_placement")
    if _guard(lambda: hasattr(obj, "Suppressed")):
        flags.add("suppressible")
    if _guard(lambda: hasattr(obj, "Shape")):
        flags.add("has_shape")
    if _guard(lambda: bool(obj.ViewObject.Visibility)):
        flags.add("shown_in_3d")
    if _guard(lambda: _editing(obj)):
        flags.add("editing")
    if _guard(lambda: obj.hasExtension("Part::AttachExtension")):
        flags.add("attachable")

    return ObjectFacts(types=type_chain(type_id),
                       proxy_module=_proxy_module(obj),
                       in_body=in_body, flags=frozenset(flags))


def _guard(test: Any) -> bool:
    try:
        return bool(test())
    except Exception:
        return False


def _placement_editable(obj: Any) -> bool:
    if "Placement" not in obj.PropertiesList:
        return False
    status = obj.getPropertyStatus("Placement")
    return not {"ReadOnly", "Immutable", "Hidden"} & set(status)


def _editing(obj: Any) -> bool:
    import FreeCADGui as Gui
    doc = Gui.getDocument(obj.Document.Name)
    editing: Any = doc.getInEdit() if doc is not None else None
    return editing is not None and editing.Object is obj


def _proxy_module(obj: Any) -> str:
    proxy = getattr(obj, "Proxy", None)
    if proxy is None:
        return ""
    return str(getattr(type(proxy), "__module__", ""))
