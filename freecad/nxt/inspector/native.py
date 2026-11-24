"""What FreeCAD's own property editor shows, where Nxt keeps no record."""

from __future__ import annotations

from typing import Any

from ..core.qt import QtCore, QtWidgets

#: FreeCAD's property editor views, by the tab they show.
VIEWS = {True: "propertyEditorData", False: "propertyEditorView"}
#: Its class name.
EDITOR_CLASS = "Gui::PropertyEditor::PropertyEditor"
#: The row of a placement's axis, and of its components.
AXIS_ROW = "Axis"
COMPONENTS = ("x", "y", "z")
#: The column holding values.
VALUE_COLUMN = 1


def _view(data: bool) -> Any:
    if QtWidgets.QApplication.instance() is None:
        return None
    for widget in QtWidgets.QApplication.allWidgets():
        if (widget.objectName() == VIEWS[data]
                and widget.metaObject().className() == EDITOR_CLASS):
            return widget
    return None


def _child(model: Any, parent: Any, label: str) -> Any:
    for row in range(model.rowCount(parent)):
        index = model.index(row, 0, parent)
        if model.data(index) == label:
            return index
    return None


def axis(label: str, data: bool = True
         ) -> tuple[float, float, float] | None:
    """The axis the native editor shows for placement `label`, if shown.

    It keeps the axis as typed, where FreeCAD stores it normalised.
    """
    view = _view(data)
    if view is None:
        return None
    model = view.model()
    root = QtCore.QModelIndex()
    for group in range(model.rowCount(root)):
        placement = _child(model, model.index(group, 0, root), label)
        if placement is None:
            continue
        row = _child(model, placement, AXIS_ROW)
        if row is None:
            return None
        locale = QtCore.QLocale()
        values: list[float] = []
        for name in COMPONENTS:
            index = _child(model, row, name)
            if index is None:
                return None
            value, ok = locale.toDouble(str(model.data(
                model.index(index.row(), VALUE_COLUMN, row))))
            if not ok:
                return None
            values.append(value)
        return values[0], values[1], values[2]
    return None
