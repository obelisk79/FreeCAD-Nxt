"""The context menu, from the tree's side: building it and running items.

The bridge's slots are thin; the work is here, so the bridge does not grow
a method per menu item. Nxt's own actions (`nxt:...`) mostly reuse what the
panel already does from its rows - isolate, set the tip, open the detail
strip - applied to the selection the menu was opened on.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import FreeCAD as App

from .. import fc, menus
from ..i18n import translate
from ..menus import facts, present, runner

if TYPE_CHECKING:
    from .bridge import TreeBridge


def build(bridge: TreeBridge, names: list[str]) -> dict[str, Any]:
    """The menu for these objects, as QML draws it."""
    doc = App.ActiveDocument
    if doc is None or not names:
        return {}
    nodes = bridge._snapshot.nodes
    objects = [o for o in (doc.getObject(n) for n in names) if o is not None]
    if not objects:
        return {}
    selection = [facts.of(o, nodes.get(o.Name), nodes) for o in objects]
    resolved = menus.for_selection(selection)
    subject = present.Subject(
        title=(objects[0].Label if len(objects) == 1
               else translate(present.CONTEXT, "%1 objects").replace(
                   "%1", str(len(objects)))),
        subtitle=_kind(objects),
        count=len(objects),
        any_shown=any("shown_in_3d" in f.flags for f in selection))
    return present.present(resolved, subject, runner.lookup)


def _kind(objects: list[Any]) -> str:
    """"Pad", or the common kind of several objects, or nothing."""
    kinds = {str(o.TypeId).split("::")[-1] for o in objects}
    return kinds.pop() if len(kinds) == 1 else ""


def run(bridge: TreeBridge, command: str, names: list[str]) -> None:
    """Run one menu item on the objects the menu was opened for."""
    doc = App.ActiveDocument
    if doc is None:
        return
    objects = [o for o in (doc.getObject(n) for n in names) if o is not None]
    if command == "nxt:native_menu":
        runner.open_native_menu()
    elif command.startswith("edit:"):
        if len(objects) == 1:
            runner.run_edit(objects[0], command)
    elif command.startswith("nxt:"):
        action = _ACTIONS.get(command[4:])
        if action is None:
            App.Console.PrintError("Nxt menu: no action %s\n" % command)
        else:
            try:
                action(bridge, objects)
            except Exception as exc:
                App.Console.PrintError("Nxt menu: %s failed: %s\n"
                                       % (command, exc))
    else:
        runner.run_command(command)
    bridge.invalidate(icons=True)


# ---------------------------------------------------------------------------
# Nxt's actions. Each takes the bridge and the objects the menu was for.
# ---------------------------------------------------------------------------

Action = Callable[["TreeBridge", list[Any]], None]


def _isolate(bridge: TreeBridge, objects: list[Any]) -> None:
    """Enter or leave the isolate mode (isolate.py) for these objects."""
    from .. import services
    isolation = services.isolation()
    if isolation is None:
        return
    doc = App.ActiveDocument
    isolation.toggle([o.Name for o in objects],
                     doc.Name if doc is not None else None)


def _inspector(bridge: TreeBridge, objects: list[Any]) -> None:
    bridge.request_property_inspector()


def _rename(bridge: TreeBridge, objects: list[Any]) -> None:
    if len(objects) == 1:
        row = bridge._tree.row_of(objects[0].Name)
        if row >= 0:
            bridge.renameRowRequested.emit(row)


def _recompute(bridge: TreeBridge, objects: list[Any]) -> None:
    doc = App.ActiveDocument
    if doc is None:
        return
    for obj in objects:
        obj.touch()
    try:
        doc.recompute(objects)
    except TypeError:
        doc.recompute()


def _reveal_failure(bridge: TreeBridge, objects: list[Any]) -> None:
    """Open the object's detail strip, where its failure is spelled out."""
    name = objects[0].Name
    bridge.revealObjectRow(name)
    bridge._tree.toggle_detail(name, True)


def _reveal_first_problem(bridge: TreeBridge, objects: list[Any]) -> None:
    body = bridge._snapshot.nodes.get(objects[0].Name)
    failed = [n for n in (body.stack if body is not None else [])
              if bridge._snapshot.nodes[n].in_error]
    if failed:
        bridge.revealObjectRow(failed[0])
        bridge._tree.toggle_detail(failed[0], True)
    else:
        bridge.revealFirstProblem()


def _select(bridge: TreeBridge, names: list[str]) -> None:
    seen = [n for i, n in enumerate(names) if n not in names[:i]]
    if seen:
        bridge._push_selection(seen, False)


def _select_consumers(bridge: TreeBridge, objects: list[Any]) -> None:
    nodes = bridge._snapshot.nodes
    _select(bridge, [c[0] for o in objects
                     for c in getattr(nodes.get(o.Name), "consumers", [])])


def _select_support(bridge: TreeBridge, objects: list[Any]) -> None:
    nodes = bridge._snapshot.nodes
    names: list[str] = []
    for obj in objects:
        node = nodes.get(obj.Name)
        if node is not None:
            names += [r[0] for r in node.refs] + list(node.inputs)
    _select(bridge, names)


def _set_tip(bridge: TreeBridge, objects: list[Any]) -> None:
    node = bridge._snapshot.nodes.get(objects[0].Name)
    if node is not None and node.body:
        bridge.setTip(node.body, node.name)


def _make_active(bridge: TreeBridge, objects: list[Any]) -> None:
    view = fc.active_view()
    if view is None:
        return
    current = view.getActiveObject("pdbody")
    if isinstance(current, tuple):
        current = current[0] if current else None
    body = objects[0]
    view.setActiveObject("pdbody", None if current is body else body)


def _select_same_type(bridge: TreeBridge, objects: list[Any]) -> None:
    """Every member of the object's Body of the object's own type.

    "Every Pocket", "every sketch": by TypeId, so a Pad does not bring the
    Pockets with it. In the Body's order, the object itself included.
    """
    obj = objects[0]
    body = None
    try:
        parent = obj.getParentGeoFeatureGroup()
        if parent is not None and parent.TypeId == "PartDesign::Body":
            body = parent
    except Exception:
        pass
    if body is None:
        return
    kind = obj.TypeId
    _select(bridge, [member.Name for member in body.Group
                     if getattr(member, "TypeId", None) == kind])


def _select_group_contents(bridge: TreeBridge, objects: list[Any]) -> None:
    names: list[str] = []

    def walk(group: Any) -> None:
        for child in getattr(group, "Group", []) or []:
            names.append(child.Name)
            walk(child)

    for obj in objects:
        walk(obj)
    _select(bridge, names)


def _synchronize(bridge: TreeBridge, objects: list[Any]) -> None:
    _recompute(bridge, objects)


def _select_bound(bridge: TreeBridge, objects: list[Any]) -> None:
    names: list[str] = []
    for obj in objects:
        support = getattr(obj, "Support", None) or []
        for entry in support:
            target = entry[0] if isinstance(entry, tuple) else entry
            if getattr(target, "Name", None):
                names.append(target.Name)
    _select(bridge, names)


def _edit_attachment(bridge: TreeBridge, objects: list[Any]) -> None:
    try:
        from AttachmentEditor import Commands
        Commands.editAttachment(objects[0])
    except Exception:
        runner.run_command("Part_EditAttachment")


def _expand_all(bridge: TreeBridge, objects: list[Any]) -> None:
    bridge._tree.expand_all()


def _collapse_all(bridge: TreeBridge, objects: list[Any]) -> None:
    bridge._tree.collapse_all()


# ---------------------------------------------------------------------------
# Expressions. FreeCAD's own Std_Expressions cannot be run from here (see
# menus/runner.py, UNSAFE), so these do the same, in the same clipboard
# format, so a copy made here pastes with FreeCAD's command and the other
# way round. Only the ExpressionEngine property is handled: it is where
# expressions on object properties live; a spreadsheet's cells are left to
# FreeCAD's own command.
# ---------------------------------------------------------------------------

#: One copied expression, as FreeCAD writes it:
#: `##@@ <path> <doc>#<object>.<property> (<label>)`, then `##@@<comment>`,
#: then the expression, then a blank line.
_EXPRESSION = re.compile(
    r"^##@@ ([^ ]+) (\w+)#(\w+)\.(\w+) [^\n]+\n##@@([^\n]*)\n",
    re.MULTILINE)


def _copy_expressions(objects: list[Any]) -> None:
    lines: list[str] = []
    for obj in objects:
        for path, expression in getattr(obj, "ExpressionEngine", []) or []:
            lines.append("##@@ %s %s#%s.ExpressionEngine (%s)\n##@@\n%s\n"
                         % (path, obj.Document.Name, obj.Name, obj.Label,
                            expression))
    from ..qt import QtWidgets
    clipboard = QtWidgets.QApplication.clipboard()
    if clipboard is not None:
        clipboard.setText("\n".join(lines))
    App.Console.PrintMessage("Nxt: copied %d expression(s)\n" % len(lines))


def _copy_selected(bridge: TreeBridge, objects: list[Any]) -> None:
    _copy_expressions(objects)


def _copy_document(bridge: TreeBridge, objects: list[Any]) -> None:
    doc = App.ActiveDocument
    _copy_expressions(list(doc.Objects) if doc is not None else [])


def _copy_all(bridge: TreeBridge, objects: list[Any]) -> None:
    documents: list[Any] = list(App.listDocuments().values())
    _copy_expressions([o for doc in documents for o in doc.Objects])


def _paste_expressions(bridge: TreeBridge, objects: list[Any]) -> None:
    from ..qt import QtWidgets
    clipboard = QtWidgets.QApplication.clipboard()
    text = clipboard.text() if clipboard is not None else ""
    found = list(_EXPRESSION.finditer(text))
    if not found:
        App.Console.PrintWarning("Nxt: no expressions on the clipboard\n")
        return
    by_doc: dict[str, list[tuple[Any, str, str]]] = {}
    for index, match in enumerate(found):
        end = found[index + 1].start() if index + 1 < len(found) else None
        path, doc_name, obj_name, prop = match.group(1, 2, 3, 4)
        expression = text[match.end():end].strip()
        doc: Any = App.listDocuments().get(doc_name)
        obj = doc.getObject(obj_name) if doc is not None else None
        if obj is None or prop != "ExpressionEngine":
            App.Console.PrintWarning("Nxt: skipped %s#%s.%s\n"
                                     % (doc_name, obj_name, prop))
            continue
        by_doc.setdefault(doc_name, []).append((obj, path, expression))
    for doc_name, entries in by_doc.items():
        doc = App.getDocument(doc_name)
        doc.openTransaction("Paste expressions")
        try:
            for obj, path, expression in entries:
                obj.setExpression(path, expression)
            doc.commitTransaction()
        except Exception:
            doc.abortTransaction()
            raise
        doc.recompute()


_ACTIONS: dict[str, Action] = {
    "isolate": _isolate,
    "inspector": _inspector,
    "rename": _rename,
    "recompute_object": _recompute,
    "reveal_failure": _reveal_failure,
    "show_solver_issues": _reveal_failure,
    "reveal_first_problem": _reveal_first_problem,
    "select_consumers": _select_consumers,
    "select_support": _select_support,
    "set_tip": _set_tip,
    "roll_forward": _set_tip,
    "make_active": _make_active,
    "select_group_contents": _select_group_contents,
    "select_same_type": _select_same_type,
    "expand_all": _expand_all,
    "collapse_all": _collapse_all,
    "synchronize_binder": _synchronize,
    "select_bound": _select_bound,
    "edit_attachment": _edit_attachment,
    "expressions_copy_selected": _copy_selected,
    "expressions_copy_document": _copy_document,
    "expressions_copy_all": _copy_all,
    "expressions_paste": _paste_expressions,
}
