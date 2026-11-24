"""Switch a feature between its additive and subtractive kinds.

FreeCAD keeps them as two types (Pad and Pocket): a change of kind is a
new feature of the other type, with the same settings and in the same
place, which takes over every link to the old one. A subtractive kind
also cuts or keeps what is common (Operation), set in place.

While the feature's task is open the switch joins the edit: the panel
is closed without OK or Cancel, its undo step left open, and opened on
the new feature, so OK keeps the switch and Cancel takes it back.
"""

from __future__ import annotations

import re
import traceback
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from ..core.qt import QtCore
from ..core.transaction import transaction
from ..inspector import templates

ADDITIVE = templates.OPERATIONS[0]
#: Never copied: what FreeCAD derives, the kind's own, and its place.
UNCOPIED = frozenset({
    "Label", "Label2", "Operation", "Shape", "AddSubShape", "BaseFeature",
    "_Body", "ExpressionEngine", "Visibility", "Placement",
    "SuppressedShape", "_ElementMapVersion",
})
LINK_PREFIX = "App::PropertyLink"
#: A container's members: the body places the new feature itself.
MEMBERS = "Group"
ENUMERATION = "App::PropertyEnumeration"


def kind_for(obj: Any, operation: str) -> str:
    """The TypeId `obj` needs for `operation`, or "" if it has none."""
    template = templates.for_objects([obj])
    pair = template.variants if template is not None else None
    if pair is None or operation not in templates.OPERATIONS:
        return ""
    return pair[0] if operation == ADDITIVE else pair[1]


def choose(obj: Any, operation: str) -> None:
    """Give `obj` this operation, on the next event-loop turn.

    Switching kinds closes the task panel, and the view that asked with
    it: never while that view's handler runs.
    """
    doc_name, name = obj.Document.Name, obj.Name
    QtCore.QTimer.singleShot(0, lambda: _choose(doc_name, name, operation))


def _choose(doc_name: str, name: str, operation: str) -> None:
    try:
        doc = App.getDocument(doc_name)
        obj = doc.getObject(name)
        wanted = kind_for(obj, operation) if obj is not None else ""
        if not wanted:
            return
        if wanted == obj.TypeId:
            _set_operation(obj, operation)
            return
        gui_doc = Gui.getDocument(doc_name)
        editing = getattr(gui_doc.getInEdit(), "Object", None) is obj
        if editing:
            _switch_in_edit(gui_doc, obj, wanted, operation)
        else:
            with transaction(doc, "Switch to %s" % _base_name(wanted)):
                new = replace(obj, wanted, operation)
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(new)
    except Exception:
        App.Console.PrintError("Nxt: could not switch the feature\n")
        App.Console.PrintError(traceback.format_exc())


def _switch_in_edit(gui_doc: Any, obj: Any, wanted: str,
                    operation: str) -> None:
    doc = obj.Document
    if not doc.HasPendingTransaction:
        doc.openTransaction("Switch to %s" % _base_name(wanted))
    # Closes the panel without OK's commit or Cancel's abort.
    gui_doc.resetEdit()
    new = replace(obj, wanted, operation)
    gui_doc.setEdit(new, 0)


def _set_operation(obj: Any, operation: str) -> None:
    if str(obj.Operation) == operation:
        return
    obj.Operation = operation
    obj.recompute()


def _base_name(type_id: str) -> str:
    return type_id.split("::")[-1]


def replace(old: Any, type_id: str, operation: str) -> Any:
    """A feature of `type_id` in `old`'s place, which is removed."""
    doc = old.Document
    body = _body_of(old)
    new = doc.addObject(type_id, _base_name(type_id))
    if body is not None:
        body.insertObject(new, old, True)
    _copy(old, new)
    if operation != ADDITIVE:
        _set_operation(new, operation)
    if not _default_label(old):
        new.Label = old.Label
    _relink(old, new)
    if body is not None:
        body.removeObject(old)
    if old.ViewObject is not None and new.ViewObject is not None:
        new.ViewObject.Visibility = old.ViewObject.Visibility
    doc.removeObject(old.Name)
    doc.recompute()
    return new


def _body_of(obj: Any) -> Any:
    body = getattr(obj, "_Body", None)
    if body is not None:
        return body
    for user in obj.InList:
        if user.TypeId == "PartDesign::Body":
            return user
    return None


def _default_label(obj: Any) -> bool:
    """`obj` keeps the label FreeCAD gave it: "Pad", "Pad001"."""
    return re.fullmatch(re.escape(_base_name(obj.TypeId)) + r"\d*",
                        obj.Label) is not None


def _copy(old: Any, new: Any) -> None:
    """Every setting both kinds have, `old`'s values into `new`.

    Enumerations first: they decide which others are read-only (a
    helix's mode).
    """
    shared = [p for p in old.PropertiesList
              if p in new.PropertiesList and p not in UNCOPIED]
    shared.sort(key=lambda p: old.getTypeIdOfProperty(p) != ENUMERATION)
    for prop in shared:
        if "ReadOnly" in (new.getEditorMode(prop) or ()):
            continue
        try:
            value = getattr(old, prop)
            if old.getTypeIdOfProperty(prop) == ENUMERATION and str(value) \
                    not in (new.getEnumerationsOfProperty(prop) or ()):
                continue    # Pocket has no UpToLast, Pad no ThroughAll
            setattr(new, prop, value)
        except Exception:
            App.Console.PrintLog("Nxt: %s not copied to %s\n"
                                 % (prop, new.Name))
    for prop, expression in getattr(old, "ExpressionEngine", None) or ():
        if prop.split(".")[0] in new.PropertiesList:
            try:
                new.setExpression(prop, expression)
            except Exception:
                App.Console.PrintLog("Nxt: expression for %s not copied\n"
                                     % prop)


def _swapped(value: Any, old: Any, new: Any) -> Any:
    if value is old:
        return new
    if isinstance(value, (list, tuple)):
        return type(value)(_swapped(v, old, new) for v in value)
    return value


def _relink(old: Any, new: Any) -> None:
    """Links to `old` lead to `new`, and expressions naming it too."""
    named = re.compile(r"(?<![\w<])%s(?=\.)" % re.escape(old.Name))
    for user in list(old.InList):
        if user is new:
            continue
        for prop in user.PropertiesList:
            if prop == MEMBERS or not user.getTypeIdOfProperty(
                    prop).startswith(LINK_PREFIX):
                continue
            try:
                value = getattr(user, prop)
                swapped = _swapped(value, old, new)
                if swapped != value:
                    setattr(user, prop, swapped)
            except Exception:
                App.Console.PrintLog("Nxt: %s.%s not relinked\n"
                                     % (user.Name, prop))
        for prop, expression in getattr(user, "ExpressionEngine", None) \
                or ():
            changed = named.sub(new.Name, expression)
            if changed != expression:
                user.setExpression(prop, changed)
