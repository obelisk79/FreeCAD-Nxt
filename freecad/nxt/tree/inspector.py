"""The Property Inspector's contents, laid out from what objects say.

No per-type layouts. FreeCAD already files every property in a named group
and gives it a kind, and addons use the same kinds, so the inspector is built
from those alone:

* groups are FreeCAD's own, in FreeCAD's order;
* each property gets the editor for its kind, not for its object's type;
* compact editors (numbers, quantities, toggles, choices, colours) take
  half a row and pair up; wide ones (text, links, vectors, placements)
  take a full row;
* a kind with no editor shows its value as text, with "Edit..." to hand
  that property to FreeCAD's own editor.

Several objects at once show the properties they share, by name and kind;
a value that differs between them is "mixed", and an edit applies to all.

Pure Python over duck-typed FreeCAD objects, so it runs in the tests.
"""

from __future__ import annotations

import math
import re
import traceback
from typing import Any

import FreeCAD as App

DocObject = Any

DATA, VIEW = "Data", "View"

QUANTITY_TYPES = frozenset({
    "App::PropertyLength", "App::PropertyDistance", "App::PropertyAngle",
    "App::PropertyQuantity", "App::PropertyQuantityConstraint",
    "App::PropertyArea", "App::PropertyVolume", "App::PropertySpeed",
    "App::PropertyAcceleration", "App::PropertyForce",
    "App::PropertyPressure", "App::PropertyPercent",
})
NUMBER_TYPES = frozenset({
    "App::PropertyFloat", "App::PropertyFloatConstraint",
    "App::PropertyPrecision", "App::PropertyInteger",
    "App::PropertyIntegerConstraint",
})
TEXT_TYPES = frozenset({
    "App::PropertyString", "App::PropertyFont", "App::PropertyFile",
    "App::PropertyFileIncluded", "App::PropertyPath", "App::PropertyUUID",
})
VECTOR_TYPES = frozenset({
    "App::PropertyVector", "App::PropertyVectorDistance",
    "App::PropertyPosition", "App::PropertyDirection",
})
LENGTH_VECTORS = frozenset({
    "App::PropertyVectorDistance", "App::PropertyPosition",
})
LINK_PREFIX = "App::PropertyLink"
KINDS: dict[str, str] = {
    "App::PropertyBool": "bool",
    "App::PropertyEnumeration": "enum",
    "App::PropertyColor": "color",
    "App::PropertyPlacement": "placement",
}

#: Kinds that fit half a row. Everything else takes a whole one.
COMPACT = frozenset({"quantity", "number", "bool", "enum", "color"})

#: Groups that open collapsed unless something in them is bound to an
#: expression: present on nearly everything, rarely what you came for.
QUIET_GROUPS = frozenset({"Base", "Attachment", "Object Style",
                          "Display Options", "Selection"})

EXPRESSION_PREFIX = "="
LENGTH_UNIT = "mm"
ANGLE_UNIT = "°"
AXES = ("x", "y", "z")
NUMBER_FORMAT = "%.6g"


def label_for(name: str) -> str:
    """'UseCustomVector' -> 'Use Custom Vector', as the native panel does."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)


def kind_of(type_id: str) -> str:
    if type_id in QUANTITY_TYPES:
        return "quantity"
    if type_id in NUMBER_TYPES:
        return "number"
    if type_id in TEXT_TYPES:
        return "text"
    if type_id in VECTOR_TYPES:
        return "vector"
    if type_id.startswith(LINK_PREFIX):
        return "link"
    return KINDS.get(type_id, "other")


def _modes(container: Any, prop: str) -> list[str]:
    try:
        return list(container.getEditorMode(prop) or ())
    except Exception:
        return []


def _expressions(obj: DocObject) -> dict[str, str]:
    return dict(getattr(obj, "ExpressionEngine", None) or ())


def _number(value: float) -> str:
    return NUMBER_FORMAT % value


def _split_quantity(text: str) -> tuple[str, str]:
    """'5.00 mm' -> ('5.00', 'mm'). A bare number has no unit."""
    match = re.match(r"^\s*([-+]?[\d.,]+(?:[eE][-+]?\d+)?)\s*(.*)$", text)
    if not match:
        return text, ""
    return match.group(1), match.group(2).strip()


def _labels(value: Any) -> list[str]:
    """Labels of whatever a link property holds, in any of its shapes."""
    out: list[str] = []
    items = value if isinstance(value, (list, tuple)) else [value]
    for item in items:
        if hasattr(item, "Label"):
            out.append(item.Label)
        elif isinstance(item, (list, tuple)) and item:
            out.extend(_labels(item[0]))
    return out


def _hex(colour: Any) -> str:
    try:
        r, g, b = (max(0, min(255, round(c * 255))) for c in colour[:3])
    except Exception:
        return ""
    return "#%02X%02X%02X" % (r, g, b)


def _entry(container: Any, prop: str, expressions: dict[str, str]
           ) -> dict[str, Any] | None:
    """One property, shaped for QML, or None if it is not for showing."""
    modes = _modes(container, prop)
    if "Hidden" in modes:
        return None
    try:
        type_id = container.getTypeIdOfProperty(prop)
        value = getattr(container, prop)
    except Exception:
        return None
    kind = kind_of(type_id)
    try:
        tip = container.getDocumentationOfProperty(prop) or ""
    except Exception:
        tip = ""
    entry: dict[str, Any] = {
        "name": prop, "label": label_for(prop), "kind": kind,
        "wide": kind not in COMPACT, "text": "", "unit": "",
        "checked": False, "options": [], "links": [], "parts": [],
        "expression": expressions.get(prop, ""),
        "readOnly": "ReadOnly" in modes, "mixed": False, "tip": tip,
    }
    if kind == "quantity":
        text = getattr(value, "UserString", str(value))
        entry["text"], entry["unit"] = _split_quantity(text)
    elif kind in ("number", "text"):
        entry["text"] = str(value)
    elif kind == "bool":
        entry["checked"] = bool(value)
    elif kind == "enum":
        entry["text"] = str(value)
        entry["options"] = list(
            container.getEnumerationsOfProperty(prop) or ())
    elif kind == "color":
        entry["text"] = _hex(value)
    elif kind == "link":
        entry["links"] = _labels(value)
    elif kind == "vector":
        unit = LENGTH_UNIT if type_id in LENGTH_VECTORS else ""
        entry["parts"] = [
            {"path": axis, "label": axis.upper(),
             "text": _number(getattr(value, axis)), "unit": unit}
            for axis in AXES]
    elif kind == "placement":
        base, rotation = value.Base, value.Rotation
        axis = rotation.Axis
        entry["parts"] = (
            [{"path": "Base." + a, "label": a.upper(),
              "text": _number(getattr(base, a)), "unit": LENGTH_UNIT}
             for a in AXES]
            + [{"path": "Axis." + a, "label": a.upper(),
                "text": _number(getattr(axis, a)), "unit": ""}
               for a in AXES]
            + [{"path": "Angle", "label": "Angle",
                "text": _number(math.degrees(rotation.Angle)),
                "unit": ANGLE_UNIT}])
    else:
        entry["text"] = str(value)
    return entry


def _container(obj: DocObject, tab: str) -> Any:
    return getattr(obj, "ViewObject", None) if tab == VIEW else obj


def _merge(first: dict[str, Any], other: dict[str, Any]) -> None:
    """Fold another object's value for the same property into `first`."""
    same = all(first[key] == other[key]
               for key in ("text", "checked", "links", "parts"))
    if not same:
        first["mixed"] = True
    first["readOnly"] = first["readOnly"] or other["readOnly"]
    if first["expression"] != other["expression"]:
        first["expression"] = ""


def _type_name(obj: DocObject) -> str:
    return str(getattr(obj, "TypeId", "")).split("::")[-1]


def describe(objects: list[DocObject], tab: str = DATA,
             text_filter: str = "") -> list[dict[str, Any]]:
    """The inspector's groups for `objects`: [{name, open, items}].

    With several objects, only properties all of them have, of the same
    kind, are shown. A filter keeps matching properties and opens every
    group that still has any.
    """
    if not objects:
        return []
    containers = [_container(obj, tab) for obj in objects]
    if any(c is None for c in containers):
        return []
    needle = text_filter.strip().lower()
    groups: dict[str, list[dict[str, Any]]] = {}
    first, rest = containers[0], containers[1:]
    expressions = [_expressions(obj) if tab == DATA else {}
                   for obj in objects]
    for prop in list(getattr(first, "PropertiesList", ()) or ()):
        entry = _entry(first, prop, expressions[0])
        if entry is None:
            continue
        if needle and needle not in entry["label"].lower() \
                and needle not in prop.lower():
            continue
        shared = True
        for container, exprs in zip(rest, expressions[1:]):
            other = (_entry(container, prop, exprs)
                     if prop in (container.PropertiesList or ()) else None)
            if other is None or other["kind"] != entry["kind"]:
                shared = False
                break
            _merge(entry, other)
        if not shared:
            continue
        try:
            group = first.getGroupOfProperty(prop) or ""
        except Exception:
            group = ""
        groups.setdefault(group or "Other", []).append(entry)

    own = _type_name(objects[0]) if len(objects) == 1 else ""
    out = []
    for index, (name, items) in enumerate(groups.items()):
        opened = (bool(needle) or name == own
                  or any(item["expression"] for item in items)
                  or name not in QUIET_GROUPS)
        out.append({"name": name, "open": opened, "items": items,
                    "first": name == own})
    # The object's own group leads, whatever order FreeCAD keeps it in.
    out.sort(key=lambda group: not group["first"])
    return out


# ---------------------------------------------------------------- editing

def _with_unit(text: str, unit: str) -> str:
    """A bare number typed into a quantity keeps the field's unit."""
    stripped = text.strip()
    if unit and re.fullmatch(r"[-+]?[\d.,]+(?:[eE][-+]?\d+)?", stripped):
        return "%s %s" % (stripped, unit)
    return stripped


def _parse(text: str) -> float:
    """A number, or a quantity in the user's units, as a plain float."""
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return float(App.Units.Quantity(text).Value)


def _assign(container: Any, obj: DocObject, prop: str, value: Any,
            unit: str) -> None:
    kind = kind_of(container.getTypeIdOfProperty(prop))
    if isinstance(value, str) and value.strip().startswith(
            EXPRESSION_PREFIX) and container is obj:
        obj.setExpression(prop, value.strip()[1:].strip())
        return
    if container is obj and prop in _expressions(obj):
        obj.setExpression(prop, None)
    if kind == "bool":
        setattr(container, prop, bool(value))
    elif kind == "number":
        current = getattr(container, prop)
        setattr(container, prop, type(current)(_parse(str(value))))
    elif kind == "quantity":
        setattr(container, prop, _with_unit(str(value), unit))
    elif kind == "color":
        colour = _parse_colour(str(value))
        if colour is not None:
            setattr(container, prop, colour)
    else:
        setattr(container, prop, str(value))


def _parse_colour(text: str) -> tuple[float, float, float] | None:
    """Colours cross from QML as '#RRGGBB'."""
    match = re.fullmatch(r"#?([0-9a-fA-F]{6})", text.strip())
    if not match:
        return None
    digits = match.group(1)
    red, green, blue = (int(digits[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return red, green, blue


def _assign_part(container: Any, prop: str, path: str, text: str) -> None:
    """Set one component of a vector or placement."""
    value = getattr(container, prop)
    number = _parse(text)
    if path in AXES:
        setattr(value, path, number)
    elif path.startswith("Base."):
        setattr(value.Base, path[len("Base."):], number)
    elif path.startswith("Axis."):
        axis = value.Rotation.Axis
        setattr(axis, path[len("Axis."):], number)
        value.Rotation = App.Rotation(axis, math.degrees(
            value.Rotation.Angle))
    elif path == "Angle":
        value.Rotation = App.Rotation(value.Rotation.Axis, number)
    setattr(container, prop, value)


def apply(objects: list[DocObject], prop: str, value: Any,
          tab: str = DATA, unit: str = "", part: str = "") -> bool:
    """Set `prop` on every object as one undo step, then recompute."""
    if not objects:
        return False
    doc = getattr(objects[0], "Document", None)
    if doc is None:
        return False
    doc.openTransaction("Edit %s" % prop)
    try:
        for obj in objects:
            container = _container(obj, tab)
            if part:
                _assign_part(container, prop, part, str(value))
            else:
                _assign(container, obj, prop, value, unit)
        doc.commitTransaction()
    except Exception:
        doc.abortTransaction()
        App.Console.PrintError("Nxt: could not set %s to %r\n"
                               % (prop, value))
        App.Console.PrintError(traceback.format_exc())
        return False
    doc.recompute()
    return True
