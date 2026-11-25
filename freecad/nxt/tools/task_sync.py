"""Edits to a feature whose task panel is open go through the panel.

The open panel owns the feature: OK writes its fields back, overwriting
a property set directly. Field names: TaskExtrudeParameters.ui.
"""

from __future__ import annotations

import contextlib
from typing import Any

import FreeCADGui as Gui

from ..core import units
from ..core.qt import QtCore, QtWidgets

#: How a field is set. COMBO: a list of the panel's own (an axis), shown
#: as its items and set by the item's text.
QUANTITY, CHECK, INDEX, MODE = "quantity", "check", "index", "mode"
COMBO = "combo"
#: A whole number in a spin box (a prism's sides, a pattern's count).
SPIN = "spin"
#: A face or plane the panel holds in a line edit (FeatureName and FaceName
#: properties) and writes back on OK: set by picking, never typed.
REFERENCE = "reference"
#: Bodies the panel lists (a Boolean's) and writes back on OK. Picked by
#: the panel itself, which hides and shows them as it goes.
BODIES = "bodies"
#: Features the panel lists (a pattern's), picked by the panel itself.
FEATURES = "features"
LISTS = (BODIES, FEATURES)
#: An enumeration's combo box whose panel acts on a choice made
#: (activated), not on the index changing.
CHOICE = "choice"
#: An enumeration as radio buttons, named in its values' order with "|".
RADIO = "radio"
#: A vector as three number fields, named x, y and z with "|".
VECTOR = "vector"
#: A yes/no the panel's direction list says: its custom item, else its
#: first (the sketch normal).
CUSTOM_DIRECTION = "custom-direction"
#: TaskExtrudeParameters' direction list: the sketch normal, "Select
#: reference...", "Custom direction", then the references picked.
NORMAL_ITEM, CUSTOM_ITEM = 0, 2
#: "name#2": the second field of that name (a pattern's second direction
#: repeats the first's form).
NTH = "#"
#: Each reference field's toggle, checked while the panel itself picks.
PICK_BUTTONS = {
    "lineFaceName": "buttonFace",
    "lineFaceName2": "buttonFace2",
    "lineStartReference": "buttonStartReference",
    "listWidgetBodies": "buttonBodyAdd",
    "listWidgetFeatures": "buttonAddFeature",
}
#: The ends and start every extrusion and revolution panel holds.
_REFERENCES: dict[str, tuple[str, str]] = {
    "UpToFace": ("lineFaceName", REFERENCE),
    "UpToFace2": ("lineFaceName2", REFERENCE),
    "StartReference": ("lineStartReference", REFERENCE),
}

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
    # The direction list says which of these OK writes back: the sketch
    # normal, a reference, or the custom vector in the three fields.
    "ReferenceAxis": ("directionCB", COMBO),
    "UseCustomVector": ("directionCB", CUSTOM_DIRECTION),
    "Direction": ("XDirectionEdit|YDirectionEdit|ZDirectionEdit", VECTOR),
    **_REFERENCES,
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
    **_REFERENCES,
}

#: TaskLoftParameters.ui. Its profile and sections it writes to the
#: feature as they change, so they are set directly.
_LOFT: dict[str, tuple[str, str]] = {
    "Ruled": ("checkBoxRuled", CHECK),
    "Closed": ("checkBoxClosed", CHECK),
}

#: TaskHelixParameters.ui. The panel writes the rest to the feature as
#: they change, and OK writes them back from it: those are set directly.
_HELIX: dict[str, tuple[str, str]] = {
    "ReferenceAxis": ("axis", COMBO),
}

#: TaskPrimitiveParameters.ui: one box for every primitive, each with its
#: own fields, prefixed by its kind. OK writes every field back.
_PRIMITIVES: dict[str, dict[str, tuple[str, str]]] = {
    kind: {prop: (field, how) for prop, field, how in props}
    for kind, props in {
        "Box": [("Length", "boxLength", QUANTITY),
                ("Width", "boxWidth", QUANTITY),
                ("Height", "boxHeight", QUANTITY)],
        "Cylinder": [("Radius", "cylinderRadius", QUANTITY),
                     ("Height", "cylinderHeight", QUANTITY),
                     ("Angle", "cylinderAngle", QUANTITY),
                     ("FirstAngle", "cylinderXSkew", QUANTITY),
                     ("SecondAngle", "cylinderYSkew", QUANTITY)],
        "Sphere": [("Radius", "sphereRadius", QUANTITY),
                   ("Angle1", "sphereAngle1", QUANTITY),
                   ("Angle2", "sphereAngle2", QUANTITY),
                   ("Angle3", "sphereAngle3", QUANTITY)],
        "Cone": [("Radius1", "coneRadius1", QUANTITY),
                 ("Radius2", "coneRadius2", QUANTITY),
                 ("Height", "coneHeight", QUANTITY),
                 ("Angle", "coneAngle", QUANTITY)],
        "Ellipsoid": [("Radius1", "ellipsoidRadius1", QUANTITY),
                      ("Radius2", "ellipsoidRadius2", QUANTITY),
                      ("Radius3", "ellipsoidRadius3", QUANTITY),
                      ("Angle1", "ellipsoidAngle1", QUANTITY),
                      ("Angle2", "ellipsoidAngle2", QUANTITY),
                      ("Angle3", "ellipsoidAngle3", QUANTITY)],
        "Torus": [("Radius1", "torusRadius1", QUANTITY),
                  ("Radius2", "torusRadius2", QUANTITY),
                  ("Angle1", "torusAngle1", QUANTITY),
                  ("Angle2", "torusAngle2", QUANTITY),
                  ("Angle3", "torusAngle3", QUANTITY)],
        "Prism": [("Polygon", "prismPolygon", SPIN),
                  ("Circumradius", "prismCircumradius", QUANTITY),
                  ("Height", "prismHeight", QUANTITY),
                  ("FirstAngle", "prismXSkew", QUANTITY),
                  ("SecondAngle", "prismYSkew", QUANTITY)],
        "Wedge": [(prop, "wedge" + prop, QUANTITY) for prop in (
            "Xmin", "Xmax", "Ymin", "Ymax", "Zmin", "Zmax",
            "X2min", "X2max", "Z2min", "Z2max")],
    }.items()
}

#: TaskBooleanParameters.ui. Its list is the bodies OK writes back.
_BOOLEAN: dict[str, tuple[str, str]] = {
    "Type": ("comboType", INDEX),
    "Group": ("listWidgetBodies", BODIES),
}

#: TaskTransformedParameters.ui, every pattern's: what it repeats.
_TRANSFORMED: dict[str, tuple[str, str]] = {
    "TransformMode": ("radioTransformToolShapes|radioTransformBody", RADIO),
    "Originals": ("listWidgetFeatures", FEATURES),
}


def _direction(suffix: str = "", nth: str = "",
               axis: str = "Direction", size: str = "Length"
               ) -> dict[str, tuple[str, str]]:
    """PatternParametersWidget.ui: one direction of a pattern.

    OK writes its direction, mode and sizes back; Reversed it reads from
    the feature.
    """
    return {axis + suffix: ("comboDirection" + nth, COMBO),
            "Mode" + suffix: ("comboMode" + nth, INDEX),
            size + suffix: ("spinExtent" + nth, QUANTITY),
            "Offset" + suffix: ("spinSpacing" + nth, QUANTITY),
            "Occurrences" + suffix: ("spinOccurrences" + nth, SPIN)}


#: PatternCircularParametersWidget.ui. OK writes every field back.
_CIRCULAR: dict[str, tuple[str, str]] = {
    "Axis": ("axisCombo", COMBO),
    "RadialDistance": ("radialDistance", QUANTITY),
    "TangentialDistance": ("tangentialDistance", QUANTITY),
    "NumberCircles": ("numberCircles", SPIN),
    "Symmetry": ("symmetry", SPIN),
    "StartAtShape": ("centerAroundFeature", CHECK),
    "BinormalAxis": ("tangentAxisCombo", COMBO),
    "FlipBinormalAxis": ("flipTangentDirection", CHECK),
}

#: PatternPathParametersWidget.ui. Its path is read from the feature.
_PATH: dict[str, tuple[str, str]] = {
    "SpacingMode": ("spacingMode", CHOICE),
    "Count": ("count", SPIN),
    "Spacing": ("spacing", QUANTITY),
    "StartOffset": ("startOffset", QUANTITY),
    "EndOffset": ("endOffset", QUANTITY),
    "CyclicOffset": ("cyclicOffset", QUANTITY),
    "ReversePath": ("reversePath", CHECK),
    "Align": ("align", CHECK),
    "TangentAxis": ("tangentAxis", COMBO),
    "FlipTangentAxis": ("flipTangentAxis", CHECK),
    "VerticalAxis": ("verticalAxis", COMBO),
    "FlipVerticalAxis": ("flipVerticalAxis", CHECK),
    "RelativeToFirst": ("relativeToFirst", CHECK),
    "OriginPointIndex": ("originPointIndex", SPIN),
}

#: PatternPointParametersWidget.ui. Its points are read from the feature.
_POINT: dict[str, tuple[str, str]] = {
    "RelativeToFirst": ("relativeToFirst", CHECK),
    "OriginPointIndex": ("originPointIndex", SPIN),
}

#: Per feature type, property -> (task field, how it is set).
FIELDS: dict[str, dict[str, tuple[str, str]]] = {
    "PartDesign::Pad": _EXTRUDE,
    "PartDesign::Pocket": _EXTRUDE,
    "PartDesign::Revolution": _REVOLVE,
    "PartDesign::Groove": _REVOLVE,
    "PartDesign::AdditiveLoft": _LOFT,
    "PartDesign::SubtractiveLoft": _LOFT,
    "PartDesign::AdditiveHelix": _HELIX,
    "PartDesign::SubtractiveHelix": _HELIX,
    "PartDesign::Boolean": _BOOLEAN,
    "PartDesign::Mirrored": {**_TRANSFORMED,
                             "MirrorPlane": ("comboPlane", COMBO)},
    "PartDesign::LinearPattern": {**_TRANSFORMED, **_direction(),
                                  **_direction("2", NTH + "2")},
    "PartDesign::PolarPattern": {**_TRANSFORMED,
                                 **_direction(axis="Axis", size="Angle")},
    "PartDesign::CircularPattern": {**_TRANSFORMED, **_CIRCULAR},
    "PartDesign::PathPattern": {**_TRANSFORMED, **_PATH},
    "PartDesign::PointPattern": {**_TRANSFORMED, **_POINT},
    **{"PartDesign::%s%s" % (way, kind): fields
       for kind, fields in _PRIMITIVES.items()
       for way in ("Additive", "Subtractive")},
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
    """The task's field `name`, or with "#n" the n-th of that name."""
    main = Gui.getMainWindow()
    if main is None:
        return None
    name, _, nth = name.partition(NTH)
    if not nth:
        return main.findChild(QtWidgets.QWidget, name)
    found = main.findChildren(QtWidgets.QWidget, name)
    return found[int(nth) - 1] if len(found) >= int(nth) else None


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
    # A component's path is kept as ".Direction.y".
    bound = {path.lstrip(".") for path, _expression
             in getattr(obj, "ExpressionEngine", None) or ()}
    if prop not in bound:
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
    if how == RADIO:
        return _choose_radio(obj, prop, name, str(value))
    if how == VECTOR:
        return _set_vector(obj, prop, name, [
            (axis, str(getattr(value, axis, number)))
            for axis, number in zip(AXES, _numbers(value), strict=False)])
    widget = _field(name)
    if widget is None or how in (REFERENCE, *LISTS):
        return False
    if how == CUSTOM_DIRECTION:
        on = bool(value) if not isinstance(value, str) \
            else value.lower() in ("1", "true", "yes")
        index = CUSTOM_ITEM if on else NORMAL_ITEM
        try:
            if index >= widget.count():
                return False
            widget.setCurrentIndex(index)
            widget.activated.emit(index)
        except RuntimeError:
            return False
        return True
    try:
        if how == COMBO:
            index = widget.findText(str(value))
            if index < 0:
                return False
            widget.setCurrentIndex(index)
            # The panel acts on a choice the user makes (activated), not
            # on the index changing: say it was chosen.
            widget.activated.emit(index)
        elif how == SPIN:
            number = units.internal_value(value)
            if number is None:
                return False
            widget.setValue(_spin_value(widget, round(number)))
        elif how == CHECK:
            widget.setChecked(bool(value) if not isinstance(value, str)
                              else value.lower() in ("1", "true", "yes"))
        elif how in (INDEX, MODE, CHOICE):
            options = list(obj.getEnumerationsOfProperty(prop) or ())
            index = (_mode_index(options, str(value)) if how == MODE
                     else options.index(str(value))
                     if str(value) in options else -1)
            if index < 0 or index >= widget.count():
                return False
            widget.setCurrentIndex(index)
            if how == CHOICE:
                widget.activated.emit(index)
        else:
            number = units.internal_value(value, unit)
            if number is None:
                return False
            _unbind(obj, prop, widget)
            widget.setProperty("rawValue", number)
    except (RuntimeError, AttributeError, ValueError):
        return False
    return True


#: A vector's components, in its fields' order.
AXES = ("x", "y", "z")


def _numbers(value: Any) -> list[float]:
    """A vector's x, y and z, from a Vector or its text "(x, y, z)"."""
    if hasattr(value, "x"):
        return [float(value.x), float(value.y), float(value.z)]
    numbers = []
    for part in str(value).strip("()[] ").split(","):
        number = units.number_value(part)
        if number is None:
            return []
        numbers.append(number)
    return numbers if len(numbers) == len(AXES) else []


def set_parts_in_task(objects: list[Any], prop: str,
                      parts: list[tuple[str, str]]) -> bool:
    """Components of a vector into the open panel's fields, as typed.

    `parts`: (axis, text); "=..." binds an expression to that component.
    False if the panel holds no such fields.
    """
    if len(objects) != 1:
        return False
    obj = objects[0]
    fields = FIELDS.get(str(getattr(obj, "TypeId", "")), {})
    if fields.get(prop, ("", ""))[1] != VECTOR or not _in_edit(obj):
        return False
    return _set_vector(obj, prop, fields[prop][0], parts)


def _set_vector(obj: Any, prop: str, names: str,
                parts: list[tuple[str, str]]) -> bool:
    widgets = dict(zip(AXES, (_field(n) for n in names.split("|")),
                       strict=True))
    if not parts or any(w is None for w in widgets.values()):
        return False
    try:
        for axis, text in parts:
            widget = widgets.get(axis.rpartition(".")[2])
            if widget is None:
                return False
            path = "%s.%s" % (prop, axis.rpartition(".")[2])
            if text.strip().startswith("="):
                if not _bind_expression(obj, path, widget, text):
                    return False
                continue
            number = units.number_value(text)
            if number is None:
                return False
            _unbind(obj, path, widget)
            widget.setValue(number)
    except (RuntimeError, AttributeError, ValueError):
        return False
    return True


def _bind_expression(obj: Any, path: str, widget: Any, text: str) -> bool:
    """Bind "=..." to `path` and to the field, which writes it on OK."""
    from . import expressions
    expression = expressions.strip_marker(text.strip())
    try:
        value = obj.evalExpression(expression)
        obj.setExpression(path, expression)
    except Exception:
        return False
    widget.setValue(float(getattr(value, "Value", value)))
    binding: Any = Gui.ExpressionBinding     # not in FreeCAD's stubs
    binding(widget).bind(obj, path)
    return True


def is_reference(objects: list[Any], prop: str) -> bool:
    """`prop` is a reference the open panel holds for one object."""
    if len(objects) != 1:
        return False
    fields = FIELDS.get(str(getattr(objects[0], "TypeId", "")), {})
    return fields.get(prop, ("", ""))[1] == REFERENCE


#: Gui::UIntSpinBox (a pattern's occurrences) keeps a count n as the
#: QSpinBox value n + INT_MIN, to reach unsigned values; its own
#: setValue, which does this, is not reachable from Python.
UINT_SPIN = "UIntSpinBox"
UINT_OFFSET = -2 ** 31


def _spin_value(widget: Any, count: int) -> int:
    """What QSpinBox.setValue takes for `count` in this spin box."""
    if widget.metaObject().className().endswith(UINT_SPIN):
        return count + UINT_OFFSET
    return count


def _choose_radio(obj: Any, prop: str, names: str, value: str) -> bool:
    """Click the radio button of `value`, as a user would."""
    options = list(obj.getEnumerationsOfProperty(prop) or ())
    buttons = names.split("|")
    if value not in options or options.index(value) >= len(buttons):
        return False
    button = _field(buttons[options.index(value)])
    if button is None:
        return False
    if not button.isChecked():
        button.click()
    return True


def _how(obj: Any, prop: str) -> str:
    fields = FIELDS.get(str(getattr(obj, "TypeId", "")), {})
    return fields.get(prop, ("", ""))[1]


def _pick_button(obj: Any, prop: str) -> Any:
    if _how(obj, prop) not in (REFERENCE, *LISTS) or not _in_edit(obj):
        return None
    name = FIELDS[str(obj.TypeId)][prop][0]
    return _field(PICK_BUTTONS[name])


def panel_picks(obj: Any, prop: str) -> bool:
    """The panel itself waits for a click on `prop`'s reference.

    It does so on choosing "Up to face" with no face yet: a click in the
    3D view is all it takes.
    """
    button = _pick_button(obj, prop)
    try:
        return button is not None and button.isChecked()
    except RuntimeError:
        return False


def start_panel_pick(obj: Any, prop: str) -> bool:
    """Let the panel pick for `prop` itself, if it is its way; True if so.

    A Boolean's panel picks its bodies, hiding what is in the way; a
    pattern's its features, taking only those that add or cut.
    """
    if _how(obj, prop) not in LISTS:
        return False
    button = _pick_button(obj, prop)
    with contextlib.suppress(RuntimeError):
        if button is not None:
            button.setChecked(True)
            return True
    return False


def list_to_task(obj: Any, prop: str) -> None:
    """The panel's list takes what `prop` now holds, for its OK.

    A body taken out is shown again, as the panel's own Remove does.
    """
    how = _how(obj, prop)
    if how not in LISTS or not _in_edit(obj):
        return
    widget = _field(FIELDS[str(obj.TypeId)][prop][0])
    if widget is None:
        return
    bodies = list(getattr(obj, prop, None) or ())
    kept = {body.Name for body in bodies}
    role = QtCore.Qt.ItemDataRole.UserRole
    with contextlib.suppress(RuntimeError):
        for row in range(widget.count()):
            name = str(widget.item(row).data(role))
            gone = obj.Document.getObject(name) if how == BODIES else None
            if name not in kept and gone is not None \
                    and gone.ViewObject is not None:
                gone.ViewObject.Visibility = True
        widget.clear()
        for body in bodies:
            item = QtWidgets.QListWidgetItem(str(body.Label), widget)
            item.setData(role, body.Name)


def stop_panel_pick(obj: Any, prop: str) -> None:
    button = _pick_button(obj, prop)
    with contextlib.suppress(RuntimeError):
        if button is not None:
            button.setChecked(False)


def mark_panel_picks(groups: list[Any], obj: Any) -> None:
    """Show as picking each reference the panel is picking for."""
    picking = {p for p in FIELDS.get(str(getattr(obj, "TypeId", "")), {})
               if panel_picks(obj, p)}
    if not picking:
        return

    def visit(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                visit(item)
        elif isinstance(node, dict):
            if node.get("name") in picking and "kind" in node:
                node["picking"] = True
            for value in node.values():
                if isinstance(value, (list, dict)):
                    visit(value)
    visit(groups)


def reference_to_task(obj: Any, prop: str) -> None:
    """Show the panel's field what `prop` now holds, so OK writes it back.

    The panel's own picking is turned off: the pick has been made.
    """
    if not is_reference([obj], prop) or not _in_edit(obj):
        return
    name = FIELDS[str(obj.TypeId)][prop][0]
    widget = _field(name)
    if widget is None:
        return
    value = getattr(obj, prop, None)
    target = value[0] if value else None
    subs = value[1] if value and len(value) > 1 else []
    sub = subs if isinstance(subs, str) else (list(subs) or [""])[0]
    try:
        widget.setProperty("FeatureName", target.Name if target else None)
        widget.setProperty("FaceName", sub)
        widget.setText(("%s:%s" % (target.Label, sub) if sub
                        else target.Label) if target else "")
        button = _field(PICK_BUTTONS[name])
        if button is not None and button.isChecked():
            button.setChecked(False)
    except RuntimeError:
        pass        # the panel closed meanwhile


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


def _pick_row(prop: str, picked: str, hint: str = PICK_HINT
              ) -> dict[str, Any]:
    chips = [{"key": "0", "label": picked, "sub": ""}] if picked else []
    return {"name": prop + PICKING, "label": "Reference", "kind": "link",
            "wide": True, "text": "", "unit": "", "checked": False,
            "options": [], "links": [picked] if picked else [],
            "parts": [], "expression": "", "readOnly": False,
            "mixed": False, "tip": "", "editor": "", "chips": chips,
            "picking": True, "pickHint": hint}


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
                    node.insert(index + 1, _pick_row(
                        name, picking[name],
                        item.get("pickHint") or PICK_HINT))
        elif isinstance(node, dict):
            name = node.get("name")
            if name in lists and "kind" in node:
                items, current = lists[name]
                # The panel's list stays usable while FreeCAD marks the
                # property read-only (a Pad's reference, while custom).
                node.update(kind="enum", editor="dropdown", options=items,
                            optionLabels=items, text=current, links=[],
                            chips=[], unit="", readOnly=False)
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
