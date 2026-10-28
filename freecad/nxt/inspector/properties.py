"""The few properties that define an object, for the detail strip."""

from __future__ import annotations

import traceback
from typing import Any

import FreeCAD as App

from ..core import property_kinds
from ..core.transaction import transaction

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
#: In getPropertyStatus: a property added to the object, not built in.
DYNAMIC_STATUS = 21
#: Types a new variable may have: (type id, label).
VARIABLE_TYPES = (
    ("App::PropertyLength", "Length"),
    ("App::PropertyAngle", "Angle"),
    ("App::PropertyArea", "Area"),
    ("App::PropertyVolume", "Volume"),
    ("App::PropertyFloat", "Number"),
    ("App::PropertyInteger", "Integer"),
    ("App::PropertyBool", "Yes/no"),
    ("App::PropertyString", "Text"),
)
#: FreeCAD's group for a VarSet's variables.
VARIABLE_GROUP = "Base"


def _added(obj: Any) -> tuple[str, ...]:
    """The properties added to an object (a VarSet's variables)."""
    found = []
    for prop in getattr(obj, "PropertiesList", ()) or ():
        try:
            if DYNAMIC_STATUS in obj.getPropertyStatus(prop):
                found.append(prop)
        except Exception:
            continue
    return tuple(found)


def tip_of(obj: Any, prop: str) -> str:
    """The property's tooltip: its documentation string."""
    try:
        return str(obj.getDocumentationOfProperty(prop) or "")
    except Exception:
        return ""


def _type_label(type_id: str) -> str:
    labels = dict(VARIABLE_TYPES)
    return labels.get(type_id, type_id.replace("App::Property", ""))


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
    names = _added(obj) if varset else KEY_PROPERTIES.get(type_id, ())
    present = set(getattr(obj, "PropertiesList", ()) or ())
    for prop in names:
        if prop not in present or property_kinds.is_hidden(obj, prop):
            continue
        try:
            type_id = obj.getTypeIdOfProperty(prop)
            kind = _strip_kind(type_id)
            value = getattr(obj, prop)
        except Exception:
            continue
        if kind is None:
            continue
        entry: dict[str, Any] = {
            "name": prop, "kind": kind, "text": "", "checked": False,
            "options": [], "expression": _expression(obj, prop) or "",
            "readOnly": property_kinds.is_read_only(obj, prop),
            "tip": tip_of(obj, prop),
            # Variables: one per row, name and tooltip editable.
            "variable": varset,
            "typeLabel": _type_label(type_id),
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


def _why_not(exc: Exception) -> str:
    text = str(exc)
    if "already exists" in text:
        return "That name's already taken. Try another."
    if "Invalid property name" in text:
        return "Start with a letter; use letters, digits and underscores."
    return text


def _changed(obj: Any, what: str, change: Any) -> str:
    """Run `change` as one undo step; "" if it took, else why not."""
    doc = getattr(obj, "Document", None)
    if doc is None:
        return "The object is gone."
    try:
        with transaction(doc, what):
            change()
    except NameError as exc:
        return _why_not(exc)
    except Exception as exc:
        App.Console.PrintError(traceback.format_exc())
        return str(exc)
    doc.recompute()
    return ""


def edit_variable(obj: Any, prop: str, name: str, tip: str) -> str:
    """Rename a variable and set its tooltip; "" or why not.

    FreeCAD's rename updates expressions that use it, and undoes; a
    tooltip change is not undone (FreeCAD keeps no history for it).
    """
    name = name.strip()
    if not name:
        return "Enter a name."

    def change() -> None:
        if name != prop:
            obj.renameProperty(prop, name)
        if tip != tip_of(obj, name):
            obj.setDocumentationOfProperty(name, tip)
    return _changed(obj, "Edit variable %s" % prop, change)


def add_variable(obj: Any, type_id: str, name: str, tip: str) -> str:
    """Add a variable to a VarSet, in its variables' group; "" or why not."""
    name = name.strip()
    if not name:
        return "Enter a name."
    if type_id not in dict(VARIABLE_TYPES):
        return "Choose a type."
    group = next((obj.getGroupOfProperty(p) for p in _added(obj)),
                 VARIABLE_GROUP)
    return _changed(obj, "Add variable %s" % name,
                    lambda: obj.addProperty(type_id, name, group, tip))


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
