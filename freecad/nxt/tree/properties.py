"""The few properties that define an object, for the detail strip.

The strip shows a handful of values an object is made of - a Pad's length, a
fillet's radius - editable in place. Everything else is one click away in
the Property Inspector. Which properties are "the few" is a judgement per
type, so it is a table; a type that is not in it shows no values and only
the link to the inspector, rather than a guess.
"""

from __future__ import annotations

import traceback
from typing import Any

import FreeCAD as App

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

QUANTITY_TYPES = frozenset({
    "App::PropertyLength", "App::PropertyDistance", "App::PropertyAngle",
    "App::PropertyQuantity", "App::PropertyQuantityConstraint",
})
NUMBER_TYPES = frozenset({
    "App::PropertyFloat", "App::PropertyFloatConstraint",
    "App::PropertyInteger", "App::PropertyIntegerConstraint",
})
BOOL_TYPE = "App::PropertyBool"
ENUM_TYPE = "App::PropertyEnumeration"

#: Typed into a field, this prefix makes the value an expression.
EXPRESSION_PREFIX = "="


def _modes(obj: Any, prop: str) -> list[str]:
    try:
        return list(obj.getEditorMode(prop) or ())
    except Exception:
        return []


def _expression(obj: Any, prop: str) -> str | None:
    for path, expression in getattr(obj, "ExpressionEngine", None) or ():
        if path == prop:
            return expression
    return None


def _kind(type_id: str) -> str | None:
    if type_id in QUANTITY_TYPES:
        return "quantity"
    if type_id in NUMBER_TYPES:
        return "number"
    if type_id == BOOL_TYPE:
        return "bool"
    if type_id == ENUM_TYPE:
        return "enum"
    return None


def describe(obj: Any) -> list[dict[str, Any]]:
    """The object's key properties, shaped for QML.

    Each entry: name, kind (quantity/number/bool/enum), text (as the user
    would type it), checked (bool kinds), options (enum kinds), expression
    (the bound expression, or ""), readOnly.
    """
    out: list[dict[str, Any]] = []
    names = KEY_PROPERTIES.get(getattr(obj, "TypeId", ""), ())
    present = set(getattr(obj, "PropertiesList", ()) or ())
    for prop in names:
        if prop not in present or "Hidden" in _modes(obj, prop):
            continue
        try:
            kind = _kind(obj.getTypeIdOfProperty(prop))
            value = getattr(obj, prop)
        except Exception:
            continue
        if kind is None:
            continue
        entry: dict[str, Any] = {
            "name": prop, "kind": kind, "text": "", "checked": False,
            "options": [], "expression": _expression(obj, prop) or "",
            "readOnly": "ReadOnly" in _modes(obj, prop),
        }
        if kind == "quantity":
            entry["text"] = getattr(value, "UserString", str(value))
        elif kind == "number":
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
    return sum(1 for prop in names if "Hidden" not in _modes(obj, prop))


def apply(obj: Any, prop: str, value: str | bool) -> bool:
    """Set one key property from the strip, as one undo step.

    A text value starting with "=" binds an expression; any other text
    clears one that was bound, since typing a plain value over an
    expression means "not computed any more".
    """
    doc = getattr(obj, "Document", None)
    if doc is None:
        return False
    doc.openTransaction("Edit %s" % prop)
    try:
        if isinstance(value, str) and value.strip().startswith(
                EXPRESSION_PREFIX):
            obj.setExpression(prop, value.strip()[1:].strip())
        else:
            if _expression(obj, prop) is not None:
                obj.setExpression(prop, None)
            _assign(obj, prop, value)
        doc.commitTransaction()
    except Exception:
        doc.abortTransaction()
        App.Console.PrintError("Nxt: could not set %s.%s to %r\n"
                               % (obj.Name, prop, value))
        App.Console.PrintError(traceback.format_exc())
        return False
    doc.recompute()
    return True


def _assign(obj: Any, prop: str, value: str | bool) -> None:
    kind = _kind(obj.getTypeIdOfProperty(prop))
    if kind == "bool":
        setattr(obj, prop, bool(value))
    elif kind == "number":
        current = getattr(obj, prop)
        setattr(obj, prop, type(current)(float(value)))
    else:
        # Quantity properties parse a string with units themselves, in
        # the user's unit system: "10 mm", "0.5 in", "30 deg".
        setattr(obj, prop, str(value))
