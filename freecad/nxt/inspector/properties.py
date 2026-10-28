"""The few properties that define an object, for the detail strip."""

from __future__ import annotations

import traceback
from typing import Any

import FreeCAD as App

from ..core import property_kinds
from ..core.transaction import transaction
from . import variables

#: TypeId -> the properties that define it, in the order to show them.
KEY_PROPERTIES: dict[str, tuple[str, ...]] = {
    "PartDesign::Pad": ("Length", "Type", "Reversed"),
    "PartDesign::Pocket": ("Length", "Type", "Reversed"),
    "PartDesign::Revolution": ("Angle", "Type", "Reversed"),
    "PartDesign::Groove": ("Angle", "Type", "Reversed"),
    "PartDesign::Fillet": ("Radius",),
    "PartDesign::Chamfer": ("Size", "ChamferType"),
    "PartDesign::Thickness": ("Value", "Reversed"),
    "PartDesign::Draft": ("Angle", "Reversed"),
    "PartDesign::Hole": ("Diameter", "Depth", "DepthType"),
    "PartDesign::LinearPattern": ("Length", "Occurrences"),
    "PartDesign::PolarPattern": ("Angle", "Occurrences"),
    "Part::Box": ("Length", "Width", "Height"),
    "Part::Cylinder": ("Radius", "Height"),
    "Part::Cone": ("Radius1", "Radius2", "Height"),
    "Part::Sphere": ("Radius",),
    "Part::Torus": ("Radius1", "Radius2"),
    "Part::Extrusion": ("LengthFwd", "Solid"),
    "Part::Fillet": ("Base",),
}

#: The kinds the strip edits in place; any other is the inspector's.
STRIP_KINDS = frozenset({"quantity", "number", "bool", "enum", "text"})
#: A variable set: its key properties are the variables added to it.
VARSET = "App::VarSet"


def _expression(obj: Any, prop: str) -> str | None:
    for path, expression in getattr(obj, "ExpressionEngine", None) or ():
        if path == prop:
            return expression
    return None


def _strip_kind(type_id: str) -> str | None:
    kind = property_kinds.kind_of(type_id)
    return kind if kind in STRIP_KINDS else None


def describe(obj: Any) -> list[dict[str, Any]]:
    """The object's key properties, shaped for QML."""
    out: list[dict[str, Any]] = []
    type_id = getattr(obj, "TypeId", "")
    varset = type_id == VARSET
    names = (variables.added(obj) if varset
             else KEY_PROPERTIES.get(type_id, ()))
    present = set(getattr(obj, "PropertiesList", ()) or ())
    for prop in names:
        if prop not in present or property_kinds.is_hidden(obj, prop):
            continue
        try:
            kind = _strip_kind(obj.getTypeIdOfProperty(prop))
            value = getattr(obj, prop)
        except Exception:
            continue
        if kind is None:
            continue
        entry: dict[str, Any] = {
            "name": prop, "kind": kind, "text": "", "checked": False,
            "options": [], "expression": _expression(obj, prop) or "",
            "readOnly": property_kinds.is_read_only(obj, prop),
            # Variables: two columns, each name over its value.
            "stacked": varset,
        }
        if kind == "quantity":
            entry["text"] = getattr(value, "UserString", str(value))
        elif kind in ("number", "text"):
            entry["text"] = str(value)
        elif kind == "bool":
            entry["checked"] = bool(value)
        else:
            entry["text"] = str(value)
            entry["options"] = list(obj.getEnumerationsOfProperty(prop) or ())
        out.append(entry)
    return out


def visible_count(obj: Any) -> int:
    """How many properties the inspector would list for this object."""
    names = getattr(obj, "PropertiesList", None) or ()
    return sum(1 for prop in names
               if not property_kinds.is_hidden(obj, prop))


def apply(obj: Any, prop: str, value: str | bool) -> bool:
    """Set one key property as one undo step; "=..." binds an expression."""
    doc = getattr(obj, "Document", None)
    if doc is None:
        return False
    try:
        with transaction(doc, "Edit %s" % prop):
            if property_kinds.is_expression(value):
                obj.setExpression(prop, property_kinds.expression_of(value))
            else:
                if _expression(obj, prop) is not None:
                    obj.setExpression(prop, None)
                _assign(obj, prop, value)
    except Exception:
        App.Console.PrintError("Nxt: could not set %s.%s to %r\n"
                               % (obj.Name, prop, value))
        App.Console.PrintError(traceback.format_exc())
        return False
    doc.recompute()
    return True


def _assign(obj: Any, prop: str, value: str | bool) -> None:
    kind = _strip_kind(obj.getTypeIdOfProperty(prop))
    if kind == "bool":
        setattr(obj, prop, bool(value))
    elif kind == "number":
        current = getattr(obj, prop)
        setattr(obj, prop, type(current)(float(value)))
    else:
        # Quantities parse unit strings themselves ("10 mm").
        setattr(obj, prop, str(value))
