"""Nxt fillets and chamfers from older files, made patternable.

Before, they were PartDesign::FeaturePython, which Mirrored and the
patterns refuse; now PartDesign::FeatureAddSubPython. A document object
cannot change its type, so each old one is replaced on opening: a new
feature takes its place in the body, its settings, label, look and
expressions, and every link and expression that pointed at it. One undo
step per document.
"""

from __future__ import annotations

import re
import traceback
from typing import Any

import FreeCAD as App

from . import blend_fillet as bf

#: Settings carried over, where the feature has them.
SETTINGS = ("Edges", "Radius", "Size", "UseAllEdges", "TangentEdges",
            "Refine", "Corners")

_waiting: dict[str, list[str]] = {}


def later(obj: Any) -> None:
    """Upgrade `obj` once its document has finished opening."""
    try:
        from ..core.qt import QtCore
    except Exception:  # noqa: BLE001 - no GUI: left as it is
        return
    doc = obj.Document.Name
    names = _waiting.setdefault(doc, [])
    names.append(obj.Name)
    if len(names) == 1:
        QtCore.QTimer.singleShot(0, lambda: upgrade_document(doc))


def upgrade_document(doc_name: str) -> list[Any]:
    names = _waiting.pop(doc_name, [])
    try:
        doc = App.getDocument(doc_name)
    except Exception:  # noqa: BLE001 - closed meanwhile
        return []
    olds = [doc.getObject(n) for n in names]
    olds = [o for o in olds if o is not None
            and o.TypeId == bf.OLD_FEATURE_TYPE]
    if not olds:
        return []
    made = []
    doc.openTransaction("Upgrade Nxt fillets")
    try:
        for old in olds:
            made.append(upgrade(old))
        doc.commitTransaction()
    except Exception:
        doc.abortTransaction()
        App.Console.PrintError("Nxt: could not upgrade the fillets of %s\n"
                               % doc.Label)
        App.Console.PrintError(traceback.format_exc())
        return []
    doc.recompute()
    App.Console.PrintMessage(
        "Nxt: %d fillet(s)/chamfer(s) in %s upgraded so Mirrored and the "
        "patterns can use them\n" % (len(made), doc.Label))
    return made


def upgrade(old: Any) -> Any:
    """A FeatureAddSubPython in `old`'s place; `old` is removed."""
    doc = old.Document
    body = bf._body_of(old)
    flat = isinstance(getattr(old, "Proxy", None), bf.BlendChamfer)
    label = old.Label
    old.Label = label + " (old)"
    new = doc.addObject(bf.FEATURE_TYPE,
                        bf.CHAMFER_NAME if flat else bf.FEATURE_NAME)
    (bf.BlendChamfer if flat else bf.BlendFillet)(new)
    bf._attach_view_provider(new, flat)
    if body is not None:
        body.insertObject(new, old, True)
    new.BaseFeature = old.BaseFeature
    for name in SETTINGS:
        if hasattr(old, name) and hasattr(new, name):
            setattr(new, name, getattr(old, name))
    for path, expression in old.ExpressionEngine:
        new.setExpression(path, expression)
    from . import feature_colors
    feature_colors.copy_visuals(old, new)
    if getattr(old, "ViewObject", None) is not None \
            and new.ViewObject is not None:
        new.ViewObject.Visibility = old.ViewObject.Visibility
    for user in old.InList:
        if user is not body and user is not new:
            relink(user, old, new)
    rename_in_expressions(doc, old.Name, new.Name)
    if body is not None:
        if body.Tip is old:
            body.Tip = new
        body.removeObject(old)
    doc.removeObject(old.Name)
    new.Label = label
    return new


def _swap(value: Any, old: Any, new: Any) -> Any:
    """`value` with `old` replaced by `new`, in any link property shape."""
    if value is old:
        return new
    if isinstance(value, tuple):
        return tuple(_swap(v, old, new) for v in value)
    if isinstance(value, list):
        return [_swap(v, old, new) for v in value]
    return value


def relink(user: Any, old: Any, new: Any) -> None:
    """Point every link property of `user` at `new` instead of `old`."""
    for name in user.PropertiesList:
        try:
            if not user.getTypeIdOfProperty(name).startswith(
                    "App::PropertyLink"):
                continue
            value = getattr(user, name)
            swapped = _swap(value, old, new)
            if swapped != value:
                setattr(user, name, swapped)
        except Exception:  # noqa: BLE001 - read-only or odd: left alone
            continue


def rename_in_expressions(doc: Any, old: str, new: str) -> None:
    """Expressions naming the old feature name the new one."""
    named = re.compile(r"(?<![\w.])%s(?=\.)" % re.escape(old))
    for obj in doc.Objects:
        for path, expression in list(getattr(obj, "ExpressionEngine", ())):
            changed = named.sub(new, expression)
            if changed != expression:
                obj.setExpression(path, changed)
