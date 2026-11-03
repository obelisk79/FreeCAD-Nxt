"""Edits to a feature whose task panel is open go through the panel.

The open panel owns the feature: OK writes its fields back, overwriting
a property set directly. Field names: TaskExtrudeParameters.ui.
"""

from __future__ import annotations

import contextlib
from typing import Any

import FreeCADGui as Gui

from ..core import units
from ..core.qt import QtWidgets

#: How a field is set. COMBO: a list of the panel's own (an axis), shown
#: as its items and set by the item's text.
QUANTITY, CHECK, INDEX, MODE = "quantity", "check", "index", "mode"
COMBO = "combo"

_EXTRUDE: dict[str, tuple[str, str]] = {
    "SideType": ("sidesMode", INDEX),
    "Type": ("changeMode", MODE),
    "Type2": ("changeMode2", MODE),
    "Length": ("lengthEdit", QUANTITY),
    "Length2": ("lengthEdit2", QUANTITY),
    "Offset": ("offsetEdit", QUANTITY),
    "Offset2": ("offsetEdit2", QUANTITY),
    "TaperAngle": ("taperEdit", QUANTITY),
    "TaperAngle2": ("taperEdit2", QUANTITY),
    "StartType": ("startMode", INDEX),
    "StartOffset": ("startOffsetEdit", QUANTITY),
    "Reversed": ("checkBoxReversed", CHECK),
    "AlongSketchNormal": ("checkBoxAlongDirection", CHECK),
}

#: TaskRevolutionParameters.ui, Revolution's and Groove's.
_REVOLVE: dict[str, tuple[str, str]] = {
    "SideType": ("sidesMode", INDEX),
    "Type": ("changeMode", MODE),
    "Type2": ("changeMode2", MODE),
    "Angle": ("revolveAngle", QUANTITY),
    "Angle2": ("revolveAngle2", QUANTITY),
    "StartType": ("startMode", INDEX),
    "StartOffset": ("startOffsetEdit", QUANTITY),
    "Reversed": ("checkBoxReversed", CHECK),
    "ReferenceAxis": ("axis", COMBO),
}

#: TaskLoftParameters.ui. Its profile and sections it writes to the
#: feature as they change, so they are set directly.
_LOFT: dict[str, tuple[str, str]] = {
    "Ruled": ("checkBoxRuled", CHECK),
    "Closed": ("checkBoxClosed", CHECK),
}

#: Per feature type, property -> (task field, how it is set).
FIELDS: dict[str, dict[str, tuple[str, str]]] = {
    "PartDesign::Pad": _EXTRUDE,
    "PartDesign::Pocket": _EXTRUDE,
    "PartDesign::Revolution": _REVOLVE,
    "PartDesign::Groove": _REVOLVE,
    "PartDesign::AdditiveLoft": _LOFT,
    "PartDesign::SubtractiveLoft": _LOFT,
}
#: Those whose start has a drag handle (float_input.py).
OFFSET_STARTS = ("PartDesign::Pad", "PartDesign::Pocket")

#: Kept in the enumeration for compatibility; absent from the combo box.
DEPRECATED_MODE = "TwoLengths"


#: Set on a dialog box task_layout.py has swapped for the template's cards.
SWAPPED = "nxtSwapped"


def showing(widget: Any) -> bool:
    """A task field is in use: on screen, or in a box swapped for cards."""
    if widget.isVisible():
        return True
    box = widget.parentWidget()
    while box is not None:
        if box.property(SWAPPED):
            holder = box.parentWidget()
            return (widget.isVisibleTo(box) and holder is not None
                    and holder.isVisible())
        box = box.parentWidget()
    return False


def _in_edit(obj: Any) -> bool:
    """`obj` is being edited, with a task panel open."""
    try:
        gui_doc = Gui.getDocument(obj.Document.Name)
        view: Any = gui_doc.getInEdit() if gui_doc is not None else None
        return (getattr(view, "Object", None) is obj
                and bool(Gui.Control.activeDialog()))
    except Exception:
        return False


def _field(name: str) -> Any:
    main = Gui.getMainWindow()
    return main.findChild(QtWidgets.QWidget, name) if main else None


def _mode_index(options: list[str], value: str) -> int:
    """Type's combo index: the enumeration's, less what it hides.

    TwoLengths is kept for compatibility; a "?" marks a hidden value.
    """
    shown = [o for o in options
             if o != DEPRECATED_MODE and not o.startswith("?")]
    return shown.index(value) if value in shown else -1


def _unbind(obj: Any, prop: str, widget: Any) -> None:
    """A plain value replaces the field's expression.

    The field keeps its own copy of the expression and writes it back
    on OK, whatever value it then shows: the property's is cleared and
    the field bound again, to nothing. Inside the edit's undo step, so
    Cancel brings the expression back.
    """
    if prop not in dict(getattr(obj, "ExpressionEngine", None) or ()):
        return
    obj.setExpression(prop, None)
    binding: Any = Gui.ExpressionBinding     # not in FreeCAD's stubs
    binding(widget).bind(obj, prop)


def set_in_task(objects: list[Any], prop: str, value: Any,
                unit: str = "") -> bool:
    """Make the edit in the open task panel's field; False if it has none.

    Expressions are never typed in; the panel would take them literally.
    """
    if len(objects) != 1:
        return False
    obj = objects[0]
    fields = FIELDS.get(str(getattr(obj, "TypeId", "")), {})
    if prop not in fields or not _in_edit(obj):
        return False
    if isinstance(value, str) and value.strip().startswith("="):
        return False
    name, how = fields[prop]
    widget = _field(name)
    if widget is None:
        return False
    try:
        if how == COMBO:
            index = widget.findText(str(value))
            if index < 0:
                return False
            widget.setCurrentIndex(index)
            # The panel acts on a choice the user makes (activated), not
            # on the index changing: say it was chosen.
            widget.activated.emit(index)
        elif how == CHECK:
            widget.setChecked(bool(value) if not isinstance(value, str)
                              else value.lower() in ("1", "true", "yes"))
        elif how in (INDEX, MODE):
            options = list(obj.getEnumerationsOfProperty(prop) or ())
            index = (_mode_index(options, str(value)) if how == MODE
                     else options.index(str(value))
                     if str(value) in options else -1)
            if index < 0 or index >= widget.count():
                return False
            widget.setCurrentIndex(index)
        else:
            number = units.internal_value(value, unit)
            if number is None:
                return False
            _unbind(obj, prop, widget)
            widget.setProperty("rawValue", number)
    except (RuntimeError, AttributeError, ValueError):
        return False
    return True


#: An offset start shows the offset handle; at zero, the same solid.
START_PROFILE, START_OFFSET = "Profile plane", "Offset"


def start_with_offset(obj: Any) -> bool:
    """Switch an edited Pad or Pocket to an offset start. True if changed.

    Set via the panel field so Cancel reverts it with the edit.
    """
    if not wants_offset_start(obj):
        return False
    return set_in_task([obj], "StartType", START_OFFSET)


def wants_offset_start(obj: Any) -> bool:
    """`obj` is an extrusion still starting at its profile plane."""
    return (str(getattr(obj, "TypeId", "")) in OFFSET_STARTS
            and str(getattr(obj, "StartType", "")) == START_PROFILE)


def combos(obj: Any) -> dict[str, tuple[list[str], str]]:
    """The panel's own lists for `obj`: property -> (items, current)."""
    if not _in_edit(obj):
        return {}
    out = {}
    for prop, (name, how) in FIELDS.get(
            str(getattr(obj, "TypeId", "")), {}).items():
        widget = _field(name) if how == COMBO else None
        if widget is None:
            continue
        with contextlib.suppress(RuntimeError):
            items = [widget.itemText(i) for i in range(widget.count())]
            out[prop] = (items, widget.currentText())
    return out


#: The row added under a list while its "Select reference..." picks.
PICKING = ":pick"
PICK_HINT = "Pick an edge, a circle, a flat face or an axis"


def select_item(items: list[str]) -> str:
    """The list's "Select reference..." item (the one with an ellipsis).

    A picked reference is added after it, so it is not always last.
    """
    for item in reversed(items):
        if item.endswith(("…", "...")):
            return item
    return ""


def _pick_row(prop: str, picked: str) -> dict[str, Any]:
    chips = [{"key": "0", "label": picked, "sub": ""}] if picked else []
    return {"name": prop + PICKING, "label": "Reference", "kind": "link",
            "wide": True, "text": "", "unit": "", "checked": False,
            "options": [], "links": [picked] if picked else [],
            "parts": [], "expression": "", "readOnly": False,
            "mixed": False, "tip": "", "editor": "", "chips": chips,
            "picking": True, "pickHint": PICK_HINT}


def as_combo(groups: list[Any], lists: dict[str, tuple[list[str], str]],
             picking: dict[str, str] | None = None) -> None:
    """Show each listed property as a drop-down of the panel's items.

    While one picks its reference (`picking`: property -> what it has
    picked so far), a row under it holds the pick and says what to pick.
    """
    picking = picking or {}

    def visit(node: Any) -> None:
        if isinstance(node, list):
            for index in range(len(node) - 1, -1, -1):
                item = node[index]
                visit(item)
                name = item.get("name") if isinstance(item, dict) else None
                if name in lists and name in picking:
                    node.insert(index + 1, _pick_row(name, picking[name]))
        elif isinstance(node, dict):
            name = node.get("name")
            if name in lists and "kind" in node:
                items, current = lists[name]
                node.update(kind="enum", editor="dropdown", options=items,
                            optionLabels=items, text=current, links=[],
                            chips=[], unit="")
            for value in node.values():
                if isinstance(value, (list, dict)):
                    visit(value)
    visit(groups)


def not_an_axis() -> str:
    """What is picked that cannot give an axis, if anything.

    The panel takes a straight edge, a circle (its centre line), a flat
    face (its normal) or a datum or origin line or plane.
    """
    try:
        picked = list(Gui.Selection.getSelectionEx("", 0))
    except Exception:
        return ""
    for entry in picked:
        obj = entry.Object
        type_id = str(getattr(obj, "TypeId", ""))
        if any(word in type_id for word in ("Line", "Plane", "Axis")):
            continue
        for sub in list(entry.SubElementNames) or [""]:
            element = sub.split(".")[-1]
            if _gives_axis(obj, sub, element):
                continue
            return "%s %s" % (obj.Label, element) if element else obj.Label
    return ""


def _gives_axis(obj: Any, sub: str, element: str) -> bool:
    if not element.startswith(("Edge", "Face")):
        return False
    try:
        import Part
        shape: Any = Part.getShape(obj, sub, needSubElement=True)
        if element.startswith("Edge"):
            return isinstance(shape.Curve, (Part.Line, Part.Circle))
        return isinstance(shape.Surface, Part.Plane)
    except Exception:
        return True     # not known to be wrong: the panel decides
