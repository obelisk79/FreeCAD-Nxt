"""The Property Inspector's contents, laid out from FreeCAD's groups.

Several objects show the properties they share; differing values are
"mixed". Pure Python over duck-typed objects, so it runs in the tests.

Without a template, every property is one line: its name in a label
column, its editor beside it (Inspector.qml). By kind:
  quantity, number, text   a field, the unit inside it
  bool                     a switch
  enum                     joined buttons for up to three short choices,
                           otherwise a drop-down
  link                     a chip per object or sub-element, each with a
                           remove button, and a + to pick more in the tree
                           or the 3D view
  vector                   X, Y and Z fields on one line
  placement                position, then rotation, X Y Z each
  color                    a swatch and its code, opening a colour picker
  anything else            its value, and FreeCAD's own editor
  shapes, meshes, materials  not shown (UNSHOWN_TYPES): no editor, and
                           nothing readable
Read-only values are plain text. Groups are cards; the quiet ones
(QUIET_GROUPS) start closed.
"""

from __future__ import annotations

import math
import re
import traceback
from typing import Any

import FreeCAD as App

from ..app.i18n import translate
from ..core import property_kinds, units
from ..core.transaction import transaction
from . import templates as inspector_templates

DocObject = Any

DATA, VIEW = "Data", "View"

#: Kinds that fit half a row. Everything else takes a whole one.
COMPACT = frozenset({"quantity", "number", "bool", "enum", "color"})

#: Groups collapsed unless something in them has an expression.
QUIET_GROUPS = frozenset({"Base", "Attachment", "Object Style",
                          "Display Options", "Selection"})

#: An enumeration this short is joined buttons, not a drop-down.
SEGMENTED_CHOICES = 3
SEGMENTED_LETTERS = 24

LENGTH_UNIT = "mm"
ANGLE_UNIT = "°"
AXES = ("x", "y", "z")
NUMBER_FORMAT = "%.6g"


def label_for(name: str) -> str:
    """'UseCustomVector' -> 'Use Custom Vector', as the native panel does."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)


def _expressions(obj: DocObject) -> dict[str, str]:
    return dict(getattr(obj, "ExpressionEngine", None) or ())


def _number(value: float) -> str:
    return NUMBER_FORMAT % value


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


def link_items(value: Any) -> list[tuple[Any, str]]:
    """(object, sub-element) pairs a link property holds, in any shape."""
    if value is None:
        return []
    if hasattr(value, "Label"):
        return [(value, "")]
    if not isinstance(value, (list, tuple)) or not value:
        return []
    if hasattr(value[0], "Label") and (
            len(value) == 2 and isinstance(value[1], (list, tuple, str))):
        subs = value[1]
        subs = [subs] if isinstance(subs, str) else list(subs)
        return [(value[0], sub) for sub in subs if sub] or [(value[0], "")]
    out: list[tuple[Any, str]] = []
    for item in value:
        out.extend(link_items(item))
    return out


def link_value(type_id: str, items: list[tuple[Any, str]]) -> Any:
    """What a link property of `type_id` takes for these pairs."""
    if type_id.startswith("App::PropertyLinkSubList"):
        grouped: dict[str, tuple[Any, list[str]]] = {}
        for obj, sub in items:
            entry = grouped.setdefault(obj.Name, (obj, []))
            if sub and sub not in entry[1]:
                entry[1].append(sub)
        return [(obj, tuple(subs) or ("",)) for obj, subs in grouped.values()]
    if type_id.startswith("App::PropertyLinkSub"):
        if not items:
            return None
        obj = items[-1][0]
        subs = [sub for o, sub in items if o is obj and sub]
        return (obj, subs)
    if type_id.startswith("App::PropertyLinkList"):
        out: list[Any] = []
        for obj, _sub in items:
            if all(o is not obj for o in out):
                out.append(obj)
        return out
    return items[-1][0] if items else None


def _chips(value: Any) -> list[dict[str, Any]]:
    from ..tools.editing import is_sketch
    return [{"key": "%d" % index,
             "label": "%s.%s" % (obj.Label, sub) if sub else obj.Label,
             "sub": sub, "sketch": is_sketch(obj)}
            for index, (obj, sub) in enumerate(link_items(value))]


def _hex(colour: Any) -> str:
    try:
        r, g, b = (max(0, min(255, round(c * 255))) for c in colour[:3])
    except Exception:
        return ""
    return "#%02X%02X%02X" % (r, g, b)


def _entry(container: Any, prop: str, expressions: dict[str, str]
           ) -> dict[str, Any] | None:
    """One property, shaped for QML, or None if it is not for showing."""
    modes = property_kinds.editor_modes(container, prop)
    if "Hidden" in modes:
        return None
    try:
        type_id = container.getTypeIdOfProperty(prop)
        if type_id in property_kinds.UNSHOWN_TYPES:
            return None
        value = getattr(container, prop)
    except Exception:
        return None
    kind = property_kinds.kind_of(type_id)
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
        "editor": "", "chips": [],
    }
    if kind == "quantity":
        text = getattr(value, "UserString", str(value))
        entry["text"], entry["unit"] = units.split_number_and_unit(text)
    elif kind in ("number", "text"):
        entry["text"] = str(value)
    elif kind == "bool":
        entry["checked"] = bool(value)
        entry["editor"] = "switch"
    elif kind == "enum":
        entry["text"] = str(value)
        # FreeCAD marks values kept only for old files with "?".
        entry["options"] = [
            o for o in container.getEnumerationsOfProperty(prop) or ()
            if not o.startswith("?") or o == entry["text"]]
        if (len(entry["options"]) <= SEGMENTED_CHOICES
                and sum(map(len, entry["options"])) <= SEGMENTED_LETTERS):
            entry["editor"] = "segmented"
    elif kind == "color":
        entry["text"] = _hex(value)
    elif kind == "link":
        entry["links"] = _labels(value)
        entry["chips"] = _chips(value)
    elif kind == "vector":
        unit = LENGTH_UNIT if type_id in property_kinds.LENGTH_VECTORS else ""
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
    """The inspector's groups for `objects`: [{name, open, items}]."""
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

    template = (inspector_templates.for_objects(objects)
                if tab == DATA else None)
    cards = (inspector_templates.apply(template, objects, groups)
             if template is not None else [])

    own = _type_name(objects[0]) if len(objects) == 1 else ""
    out = []
    for index, (name, items) in enumerate(groups.items()):
        opened = (bool(needle)
                  or any(item["expression"] for item in items)
                  or (not cards and (name == own
                                     or name not in QUIET_GROUPS)))
        out.append({"name": name, "open": opened, "items": items,
                    "first": name == own and not cards})
    out.sort(key=lambda group: not group["first"])
    if cards and out:
        out[0]["rest"] = True
        out[0]["restCount"] = len(out)
        for group in out:
            group["behind"] = True
    return cards + out


# -- editing --

def _assign(container: Any, obj: DocObject, prop: str, value: Any,
            unit: str) -> None:
    kind = property_kinds.kind_of(container.getTypeIdOfProperty(prop))
    if property_kinds.is_expression(value) and container is obj:
        expression = property_kinds.expression_of(value)
        # FreeCAD binds a name it cannot find, and fails at recompute.
        obj.evalExpression(expression)
        obj.setExpression(prop, expression)
        return
    if container is obj and prop in _expressions(obj):
        obj.setExpression(prop, None)
    if kind in ("number", "quantity"):
        try:
            if kind == "number":
                current = getattr(container, prop)
                setattr(container, prop,
                        type(current)(units.number_value(str(value))))
            else:
                setattr(container, prop, units.with_unit(str(value), unit))
        except Exception:
            # An expression typed without its "=": bound as one, if
            # FreeCAD can work it out; else why it can't is reported.
            if container is not obj or not _reads(obj, str(value)):
                raise
            obj.setExpression(prop, str(value).strip())
    elif kind == "bool":
        setattr(container, prop, bool(value))
    elif kind == "color":
        colour = _parse_colour(str(value))
        if colour is not None:
            setattr(container, prop, colour)
    else:
        setattr(container, prop, str(value))


def _reads(obj: DocObject, text: str) -> bool:
    """Whether `text` is an expression FreeCAD can work out on `obj`."""
    try:
        obj.evalExpression(text.strip())
    except Exception:
        return False
    return True


def problem(obj: DocObject | None, prop: str, value: Any,
            error: Exception) -> str:
    """Why `value` could not be set, in a line the user can act on."""
    text = str(value).strip()
    typed = property_kinds.expression_of(text) \
        if property_kinds.is_expression(text) else text
    reason = ""
    if obj is not None and typed:
        try:
            obj.evalExpression(typed)
        except Exception as exc:
            reason = _first_line(exc)
    shadowed = _unit_names(typed)
    if shadowed:
        reason += ". " + translate(
            "Nxt", "%s is also a unit, which FreeCAD reads first: rename "
                   "the variable") % ", ".join("'%s'" % n for n in shadowed)
    elif not reason:
        reason = _first_line(error)
        if not property_kinds.is_expression(text):
            reason += ". " + translate("Nxt", "Expressions start with =")
    return "%s: %s" % (prop, reason)


def _first_line(error: Exception) -> str:
    lines = str(error).strip().splitlines()
    return lines[0] if lines else type(error).__name__


def _unit_names(text: str) -> list[str]:
    """Property names after a "." that FreeCAD would read as units."""
    return [name for name in re.findall(r"\.\s*([A-Za-z_]\w*)", text)
            if _is_unit(name)]


def _is_unit(name: str) -> bool:
    try:
        App.Units.Quantity("1 %s" % name)
    except Exception:
        return False
    return True


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
    number = units.number_value(text)
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


def edit_links(objects: list[DocObject], prop: str,
               remove: str = "", add: list[tuple[Any, str]] | None = None
               ) -> bool:
    """Drop the chip keyed `remove`, or add picked pairs, as one undo step."""
    if not objects:
        return False
    doc = getattr(objects[0], "Document", None)
    if doc is None:
        return False
    try:
        with transaction(doc, "Edit %s" % prop):
            for obj in objects:
                type_id = obj.getTypeIdOfProperty(prop)
                items = link_items(getattr(obj, prop))
                if remove:
                    index = int(remove)
                    items = [i for n, i in enumerate(items) if n != index]
                for picked in add or ():
                    if picked[0] is obj:
                        continue
                    # A whole object stands for its sub-elements, and
                    # they for it.
                    items = [i for i in items
                             if not (i[0] is picked[0]
                                     and (not i[1] or not picked[1]))]
                    items.append(picked)
                setattr(obj, prop, link_value(type_id, items))
    except Exception:
        App.Console.PrintError("Nxt: could not change %s\n" % prop)
        App.Console.PrintError(traceback.format_exc())
        return False
    doc.recompute()
    return True


def apply(objects: list[DocObject], prop: str, value: Any,
          tab: str = DATA, unit: str = "", part: str = "",
          problems: list[str] | None = None) -> bool:
    """Set `prop` on every object as one undo step, then recompute."""
    return apply_many(objects, [(prop, value, unit)], tab, part, problems)


def apply_many(objects: list[DocObject],
               edits: list[tuple[str, Any, str]], tab: str = DATA,
               part: str = "", problems: list[str] | None = None) -> bool:
    """Make several (property, value, unit) edits as one undo step.

    What went wrong, if anything, goes to `problems` for the user.
    """
    if not objects or not edits:
        return False
    doc = getattr(objects[0], "Document", None)
    if doc is None:
        return False
    try:
        with transaction(doc, "Edit %s" % edits[-1][0]):
            for prop, value, unit in edits:
                for obj in objects:
                    container = _container(obj, tab)
                    try:
                        if part:
                            _assign_part(container, prop, part, str(value))
                        else:
                            _assign(container, obj, prop, value, unit)
                    except Exception as exc:
                        if problems is not None:
                            problems.append(problem(obj, prop, value, exc))
                        raise
    except Exception:
        App.Console.PrintError("Nxt: could not set %s\n"
                               % ", ".join("%s to %r" % (p, v)
                                           for p, v, _u in edits))
        App.Console.PrintError(traceback.format_exc())
        return False
    doc.recompute()
    return True
