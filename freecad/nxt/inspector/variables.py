"""A VarSet's variables: the properties added to it, and editing them.

FreeCAD can't change a property's type, so a variable's type is chosen
once, when it is added.
"""

from __future__ import annotations

import traceback
from collections.abc import Callable
from typing import Any

import FreeCAD as App

from ..core.transaction import transaction

#: In getPropertyStatus: a property added to the object, not built in.
DYNAMIC_STATUS = 21
#: Types a new variable may have: (type id, label).
TYPES = (
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
GROUP = "Base"


def added(obj: Any) -> tuple[str, ...]:
    """The properties added to an object (a VarSet's variables)."""
    found = []
    for prop in getattr(obj, "PropertiesList", ()) or ():
        try:
            if DYNAMIC_STATUS in obj.getPropertyStatus(prop):
                found.append(prop)
        except Exception:
            continue
    return tuple(found)


def type_label(type_id: str) -> str:
    return dict(TYPES).get(type_id, type_id.replace("App::Property", ""))


def tip_of(obj: Any, prop: str) -> str:
    try:
        return str(obj.getDocumentationOfProperty(prop) or "")
    except Exception:
        return ""


def _why_not(exc: Exception) -> str:
    text = str(exc)
    if "already exists" in text:
        return "That name's already taken. Try another."
    if "Invalid property name" in text:
        return "Start with a letter; use letters, digits and underscores."
    return text


def _changed(obj: Any, what: str, change: Callable[[], None]) -> str:
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


def edit(obj: Any, prop: str, name: str, tip: str) -> str:
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


def add(obj: Any, type_id: str, name: str, tip: str) -> str:
    """Add a variable, in the variables' group; "" or why not."""
    name = name.strip()
    if not name:
        return "Enter a name."
    if type_id not in dict(TYPES):
        return "Choose a type."
    group = next((obj.getGroupOfProperty(p) for p in added(obj)), GROUP)
    return _changed(obj, "Add variable %s" % name,
                    lambda: obj.addProperty(type_id, name, group, tip))
