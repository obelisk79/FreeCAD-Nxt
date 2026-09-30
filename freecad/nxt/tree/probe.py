"""Run this in FreeCAD's Python console before trusting the panel.

    from freecad.nxt.tree import probe; probe.run()

Everything the panel does rests on four assumptions that vary between
FreeCAD builds and object flavours:

  1. QtQuick is importable from this FreeCAD's Python.
  2. ViewProvider::claimChildren() is reachable from Python. If it is not,
     the hierarchy silently degrades to group containment only.
  3. The drag/drop protocol (canDragObject/dragObject/canDropObject/
     dropObject) is exposed on view providers.
  4. The document/selection observer APIs accept a plain Python object.

The report tells you which of those hold, and then dumps the partition the
panel would draw so you can compare it against the stock tree by eye.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from .. import qtquick
from ..qt import QtCompat
from . import health, scene


def _line(label: str, ok: bool, detail: str = "") -> bool:
    mark = "OK  " if ok else "FAIL"
    text = "  [%s] %s" % (mark, label)
    if detail:
        text += " - %s" % detail
    App.Console.PrintMessage(text + "\n")
    return ok


def sketch(name: str, doc: Any = None) -> Any:
    """Dump every source of status a single object exposes.

    Run this on the sketch that is misreporting:

        from freecad.nxt.tree import probe; probe.sketch("Sketch012")

    Nothing here is guessed. It lists what the object actually has, calls
    only the accessors that are unambiguously getters, and leaves the rest
    named but untouched - several of the names matching "redundant" are the
    ones that edit the sketch.
    """
    if doc is None:
        doc = App.ActiveDocument
    if doc is None:
        App.Console.PrintError("Nxt: no active document\n")
        return
    obj = doc.getObject(name)
    if obj is None:
        for candidate in doc.Objects:
            if getattr(candidate, "Label", None) == name:
                obj = candidate
                break
    if obj is None:
        App.Console.PrintError("Nxt: no object named or labelled %r\n" % name)
        return

    App.Console.PrintMessage("\n=== %s (%s) ===\n"
                             % (obj.Label, getattr(obj, "Name", "?")))
    for key, value in health.dump(obj, everything=True):
        App.Console.PrintMessage("  %-38s %s\n" % (key, value))

    view = getattr(obj, "ViewObject", None)
    if view is not None:
        # The stock tree composes its status overlays through the view
        # provider, so if the finding is reachable from Python at all it is
        # as likely to be here as on the object.
        App.Console.PrintMessage("\n  --- ViewObject ---\n")
        for key, value in health.dump(view, everything=True):
            App.Console.PrintMessage("  %-38s %s\n" % (key, value))

    severity, notes = health.inspect(obj, note_unavailable=True)
    App.Console.PrintMessage("\n  panel verdict: severity=%d notes=%r\n\n"
                             % (severity, notes))
    return obj


def timeline(body_name: str | None = None,
             doc: Any = None) -> list[Any]:
    """Does Group really record creation order, and does it hold sketches?

        from freecad.nxt.tree import probe; probe.timeline()

    The panel now draws a Body's children as a timeline, and the order it
    draws comes from Group. That is an assumption about this build, so it
    gets checked against a real model rather than asserted: this prints
    Group beside claimChildren, the BaseFeature chain and the tip, so a
    disagreement is visible instead of silently mis-ordering the tree.
    """
    doc = doc or App.ActiveDocument
    if doc is None:
        App.Console.PrintError("probe.timeline: no active document\n")
        return []

    bodies: list[Any] = []
    for obj in doc.Objects:
        if scene._derived(obj, scene.BODY_BASES):
            if body_name is None or obj.Name == body_name:
                bodies.append(obj)

    if not bodies:
        App.Console.PrintMessage("probe.timeline: no Body in this document\n")
        return []

    for body in bodies:
        App.Console.PrintMessage("\n=== %s (%s) ===\n"
                                 % (body.Label, body.Name))
        tip = getattr(body, "Tip", None)
        App.Console.PrintMessage("tip: %s\n"
                                 % (tip.Name if tip is not None else "(none)"))

        App.Console.PrintMessage("\nGroup order\n")
        group = list(getattr(body, "Group", None) or [])
        for index, obj in enumerate(group):
            App.Console.PrintMessage(
                "  %2d  %-22s %-34s%s\n"
                % (index, obj.Name, getattr(obj, "TypeId", ""),
                   "  <- profile" if scene.is_profile(obj) else ""))
        if not group:
            App.Console.PrintMessage("  (empty - Group is not where this "
                                     "build keeps Body members)\n")

        App.Console.PrintMessage("\nclaimChildren order\n")
        for index, obj in enumerate(scene.claim_children(body)):
            App.Console.PrintMessage("  %2d  %s\n" % (index, obj.Name))

        App.Console.PrintMessage("\nBaseFeature chain (what the tip can "
                                 "move along)\n")
        for index, obj in enumerate(scene.feature_stack(body)):
            App.Console.PrintMessage("  %2d  %s\n" % (index, obj.Name))

        App.Console.PrintMessage("\nprofiles in this Body, and who uses "
                                 "them\n")
        found = False
        for obj in group:
            if not scene.is_profile(obj):
                continue
            found = True
            users: list[str] = []
            for dep in getattr(obj, "InList", []) or []:
                if scene.linking_properties(dep, obj):
                    users.append(dep.Name)
            App.Console.PrintMessage(
                "  %-22s used by %s\n"
                % (obj.Name, ", ".join(sorted(set(users))) or "(nothing)"))
        if not found:
            App.Console.PrintMessage("  (none found in Group - if this Body "
                                     "has sketches, they live elsewhere and "
                                     "the timeline order needs another "
                                     "source)\n")

        App.Console.PrintMessage("\ndocument order, for comparison\n")
        names = [o.Name for o in doc.Objects if o.Name in
                 set(g.Name for g in group)]
        App.Console.PrintMessage("  %s\n" % ", ".join(names))
        agree = names == [g.Name for g in group]
        App.Console.PrintMessage(
            "  Group %s document order\n"
            % ("agrees with" if agree else "DISAGREES with"))

    App.Console.PrintMessage("\n=== end ===\n\n")
    return bodies


def active() -> dict[str, str]:
    """What this build offers for "which container is active".

        from freecad.nxt.tree import probe; probe.active()

    The panel marks the active Body so operations land somewhere visible,
    and it reads that through `ActiveView.getActiveObject(...)`. There is
    no observer for it - activating a Body is a Gui action that emits no
    document signal - so the panel polls, and it is worth knowing what the
    call actually returns here before trusting either half of that.
    """
    App.Console.PrintMessage("\n=== active object ===\n")

    try:
        view = Gui.ActiveDocument.ActiveView
    except Exception:
        App.Console.PrintError("  no active view\n")
        return {}

    App.Console.PrintMessage("  view: %s\n" % type(view).__name__)
    App.Console.PrintMessage("  getActiveObject: %s\n"
                             % hasattr(view, "getActiveObject"))

    found: dict[str, str] = {}
    for key in ("pdbody", "part", "Assembly", "AssemblyLink"):
        try:
            obj = view.getActiveObject(key)
        except Exception as exc:
            App.Console.PrintMessage("  %-14s raised %s\n"
                                     % (key, type(exc).__name__))
            continue
        # Some builds answer with (object, matrix, ...) rather than an
        # object; unwrap rather than assume either shape.
        if isinstance(obj, tuple):
            obj = obj[0] if obj else None
        name = getattr(obj, "Name", None)
        App.Console.PrintMessage("  %-14s %s\n" % (key, name or "(none)"))
        if name:
            found[key] = name

    App.Console.PrintMessage("\n  panel currently marks: %s\n"
                             % (_panel_active() or "(nothing)"))
    App.Console.PrintMessage("=== end ===\n\n")
    return found


def _panel_active() -> Any:
    try:
        from . import panel
        bridge = panel.bridge()
        return bridge.active_container() if bridge is not None else None
    except Exception:
        return None


def benchmark(rounds: int = 5,
              doc: Any = None) -> dict[str, float | None]:
    """How long the panel's work actually takes on *this* document.

    Run it on the model that feels slow:

        from freecad.nxt.tree import probe; probe.benchmark()

    A snapshot capture runs on every document signal, and a tip drag used
    to trigger one per feature crossed. The numbers below say whether that
    is a millisecond or a fifth of a second here, which is the difference
    between a design that is fine and one that needs rethinking - and it is
    not a thing to guess at from the outside.

    Read-only: nothing is moved and no transaction is opened.
    """
    doc = doc or App.ActiveDocument
    if doc is None:
        App.Console.PrintError("probe.benchmark: no active document\n")
        return {}

    def timed(label: str, call: Callable[[], object],
              count: int = rounds) -> float | None:
        best: Any = None
        total = 0.0
        for _round in range(count):
            started = time.perf_counter()
            call()
            elapsed = time.perf_counter() - started
            total += elapsed
            best = elapsed if best is None else min(best, elapsed)
        App.Console.PrintMessage("  %-34s best %7.1f ms   mean %7.1f ms\n"
                                 % (label, best * 1000,
                                    total / count * 1000))
        return best

    App.Console.PrintMessage("\n=== timings for %s ===\n" % doc.Label)
    App.Console.PrintMessage("  %d objects, %d rounds each\n\n"
                             % (len(doc.Objects), rounds))

    results: dict[str, float | None] = {}
    results["capture"] = timed("full snapshot capture",
                               lambda: scene.Snapshot(doc))

    snap = scene.Snapshot(doc)
    App.Console.PrintMessage("  %d nodes, %d profiles, %d roots\n"
                             % (len(snap.nodes), len(snap.profiles),
                                len(snap.roots)))

    bodies = [n for n, node in snap.nodes.items() if node.stack]
    if bodies:
        body = bodies[0]
        tips = snap.nodes[body].stack
        results["retip"] = timed(
            "in-place retip (one drag step)",
            lambda: snap.retip(body, tips[len(tips) // 2]), rounds * 20)
        App.Console.PrintMessage("  longest history: %s, %d features\n"
                                 % (body, len(tips)))
    else:
        App.Console.PrintMessage("  no Body with a feature stack to retip\n")

    profiles = [snap.nodes[n] for n in snap.profiles]
    if profiles:
        objs = [doc.getObject(n) for n in snap.profiles]
        objs = [o for o in objs if o is not None]
        results["health"] = timed(
            "solver read, all profiles",
            lambda: [health.inspect(o) for o in objs])

    results["flatten"] = timed(
        "flatten to rows",
        lambda: snap.flatten(snap.default_expansion()), rounds * 20)

    App.Console.PrintMessage("\n")
    capture = results.get("capture") or 0
    retip = results.get("retip") or 0
    if capture > 0.05:
        App.Console.PrintMessage(
            "  A capture over ~50ms is felt. Every document signal costs "
            "one.\n")
    if retip and capture:
        App.Console.PrintMessage(
            "  A drag step costs a retip, not a capture: %.0fx cheaper "
            "here.\n" % (capture / retip if retip else 0))
    App.Console.PrintMessage("=== end ===\n\n")
    return results


def overlay() -> tuple[list[str], list[str]]:
    """What this build offers for driving dock overlay from Python.

    Run it when the panel cannot restore its overlay state:

        from freecad.nxt.tree import probe; probe.overlay()

    Lists the overlay commands FreeCAD registers and searches the parameter
    tree for anything the overlay manager might be storing - which is the
    other route to setting this for a specific dock, if a command that acts
    on "the active dock" cannot be aimed.
    """
    App.Console.PrintMessage("\n=== overlay support ===\n")

    try:
        commands = sorted(c for c in Gui.listCommands()
                          if "overlay" in c.lower())
    except Exception:
        commands = []
    App.Console.PrintMessage("\ncommands\n")
    for name in commands or ["(none)"]:
        App.Console.PrintMessage("  %s\n" % name)

    App.Console.PrintMessage("\nGui attributes mentioning overlay\n")
    found = [n for n in dir(Gui) if "overlay" in n.lower()]
    for name in found or ["(none)"]:
        App.Console.PrintMessage("  %s\n" % name)

    App.Console.PrintMessage("\nparameters mentioning overlay\n")
    hits: list[str] = []

    def walk(group: Any, path: str, depth: int = 0) -> None:
        if depth > 4:
            return
        try:
            contents = group.GetContents() or []
        except Exception:
            contents = []
        for entry in contents:
            try:
                kind, key, value = entry
            except Exception:
                continue
            if "overlay" in str(key).lower() or "overlay" in path.lower():
                hits.append("%s/%s = %r (%s)" % (path, key, value, kind))
        try:
            subgroups = group.GetGroups() or []
        except Exception:
            subgroups = []
        for name in subgroups:
            if depth < 4:
                walk(group.GetGroup(name), "%s/%s" % (path, name), depth + 1)

    try:
        walk(App.ParamGet("User parameter:BaseApp"), "BaseApp")
    except Exception:
        App.Console.PrintError("  could not walk the parameter tree\n")
    for line in hits or ["(none)"]:
        App.Console.PrintMessage("  %s\n" % line)

    App.Console.PrintMessage("\n=== end ===\n\n")
    return commands, hits


def context_menu() -> dict[str, list[dict[str, Any]]]:
    """Read FreeCAD's own tree menu for the selection, without showing it.

    Select one object in FreeCAD's Model tree, then:

        from freecad.nxt.tree import probe; probe.context_menu()

    This is the check behind the Nxt menu's promise that nothing FreeCAD
    offers is lost: it opens the native tree's menu for the selected
    object, reads every entry, closes it before it is drawn, and reports:

      * commands - entries that name a FreeCAD command, which Nxt can run
        later with Gui.runCommand;
      * view provider actions - entries with no command; those carrying an
        edit mode replay as setEdit, the rest can only be triggered from
        a live menu;
      * which commands Nxt's definitions would not place, and so would go
        under More.
    """
    from ..qt import QtCore, QtGui, QtWidgets

    App.Console.PrintMessage("\n=== FreeCAD's tree menu ===\n")
    tree = _native_tree()
    if tree is None:
        App.Console.PrintError("  FreeCAD's Model tree was not found\n")
        return {}
    items = tree.selectedItems()
    if len(items) != 1:
        App.Console.PrintError("  select exactly one object in the Model "
                               "tree first\n")
        return {}
    tree.scrollToItem(items[0])
    point = tree.visualItemRect(items[0]).center()

    captured: list[dict[str, Any]] = []

    class Catch(QtCore.QObject):
        def eventFilter(self, obj: QtCore.QObject,  # noqa: N802
                        event: QtCore.QEvent) -> bool:
            if (event.type() == QtCore.QEvent.Type.Show
                    and isinstance(obj, QtWidgets.QMenu)
                    and obj.parentWidget() is None and not captured):
                # Wayland cannot fade a window; there it may flash.
                if QtGui.QGuiApplication.platformName() != "wayland":
                    obj.setWindowOpacity(0.0)
                captured.extend(_menu_entries(obj))
                QtCore.QTimer.singleShot(0, obj.close)
            return False

    catcher = Catch()
    app = QtWidgets.QApplication.instance()
    if app is None:
        return {}
    app.installEventFilter(catcher)
    try:
        event = QtGui.QContextMenuEvent(
            QtGui.QContextMenuEvent.Reason.Mouse, point,
            tree.viewport().mapToGlobal(point))
        QtWidgets.QApplication.sendEvent(tree.viewport(), event)
    finally:
        app.removeEventFilter(catcher)

    if not captured:
        App.Console.PrintError("  no menu was opened: is the Model tree "
                               "shown?\n")
        return {}

    flat = list(_flatten(captured))
    commands = [e for e in flat if e["command"]]
    groups = [e for e in flat if e["submenu"] and not e["command"]]
    # A submenu's own entries are listed with the submenu, not here.
    actions = [e for e in captured
               if not e["command"] and not e["submenu"]]
    App.Console.PrintMessage("\n  commands (%d)\n" % len(commands))
    for entry in commands:
        App.Console.PrintMessage("    %-34s %s%s\n" % (
            entry["command"], entry["text"],
            "" if entry["enabled"] else "  (disabled)"))
    App.Console.PrintMessage("\n  submenus with no command name (%d)\n"
                             % len(groups))
    for entry in groups:
        App.Console.PrintMessage("    %s: %s\n" % (
            entry["text"],
            ", ".join(e["text"] for e in entry["submenu"])))
    App.Console.PrintMessage("\n  view provider and tree actions (%d)\n"
                             % len(actions))
    for entry in actions:
        App.Console.PrintMessage("    %-34s data=%r%s\n" % (
            entry["text"], entry["data"],
            "  (default)" if entry["default"] else ""))

    try:
        from .. import menus
        menu = menus.for_selection(menus.current_selection())
        placed = set(menu.commands()) | menu.dropped
        missing = sorted({e["command"] for e in commands} - placed)
    except Exception as exc:
        missing = []
        App.Console.PrintError("  Nxt's definitions failed: %s\n" % exc)
    App.Console.PrintMessage("\n  not placed by Nxt's definitions, so "
                             "they go under More (%d)\n" % len(missing))
    for name in missing or ["(none)"]:
        App.Console.PrintMessage("    %s\n" % name)
    App.Console.PrintMessage("=== end ===\n\n")
    return {"commands": commands, "actions": actions,
            "missing": [{"command": m} for m in missing]}


def _native_tree() -> Any:
    from ..qt import QtWidgets

    trees = [w for w in Gui.getMainWindow().findChildren(
        QtWidgets.QTreeWidget)
        if w.metaObject().className() == "Gui::TreeWidget"]
    shown = [w for w in trees if w.isVisible()]
    return (shown or trees or [None])[0]


def _menu_entries(menu: Any) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    default = menu.defaultAction()
    for action in menu.actions():
        if action.isSeparator():
            continue
        sub = action.menu()
        data = action.data()
        # A command with a choice of actions (Std_Expressions,
        # Std_LinkMakeGroup) is a submenu; its name may be on the menu
        # rather than on the action that opens it.
        name = action.objectName() or (sub.objectName() if sub else "")
        entries.append({
            "text": action.text().replace("&", ""),
            "command": name if "_" in name else "",
            "data": data if isinstance(data, (int, str)) else None,
            "enabled": action.isEnabled(),
            "default": action is default,
            "submenu": _menu_entries(sub) if sub is not None else [],
        })
    return entries


def _flatten(entries: list[dict[str, Any]]) -> Any:
    for entry in entries:
        yield entry
        yield from _flatten(entry["submenu"])


#: Coin field types whose value is safe to read as text: plain values, no
#: nodes, paths or engines behind them.
_PLAIN_FIELDS = frozenset({
    "SFFloat", "SFDouble", "SFInt32", "SFUInt32", "SFShort", "SFUShort",
    "SFBool", "SFEnum", "SFBitMask", "SFVec2f", "SFVec3f", "SFVec3d",
    "SFVec4f", "SFRotation", "SFColor", "SFString", "SFName", "SFMatrix",
    "SFPlane", "SFTime",
})


def draggers(to_file: bool = True) -> dict[str, Any]:
    """What the 3D view's interactive arrows are made of, and what they expose.

        from freecad.nxt.tree import probe; probe.draggers()

    Run it while a feature's arrows are showing - a Pad open for editing.
    Reports:
      * every dragger or gizmo node in the view's scene: its type, its type
        ancestry, and every field with its current value - whether the
        drag step is a field Python can change;
      * the number fields in the open task panel, which a floating input
        in the 3D view would drive;
      * preferences whose names mention gizmos, draggers or steps.
    Printed to the Report view and, unless `to_file` is False, written to
    nxt-draggers.txt in FreeCAD's user data folder.
    """
    lines: list[str] = []
    say = lines.append
    found: dict[str, Any] = {"nodes": [], "fields": [], "params": []}

    try:
        from pivy import coin
    except Exception as exc:
        say("pivy is not importable: %s" % exc)
        coin = None

    view = getattr(Gui.ActiveDocument, "ActiveView", None) \
        if Gui.ActiveDocument is not None else None
    say("=== Nxt dragger probe ===")
    say("view: %s" % (type(view).__name__ if view is not None else None))
    edit = Gui.ActiveDocument.getInEdit() if Gui.ActiveDocument else None
    say("in edit: %s" % (getattr(getattr(edit, "Object", None), "Name", edit)))

    roots: list[tuple[str, Any]] = []
    if view is not None:
        try:
            roots.append(("view scene", view.getSceneGraph()))
        except Exception as exc:
            say("getSceneGraph failed: %s" % exc)
        try:
            viewer = view.getViewer()
            manager = viewer.getSoRenderManager()
            roots.append(("render manager", manager.getSceneGraph()))
        except Exception as exc:
            say("render manager scene not reachable: %s" % exc)

    def ancestry(node: Any) -> list[str]:
        chain: list[str] = []
        kind = node.getTypeId()
        while kind is not None and not kind.isBad():
            chain.append(str(kind.getName()))
            kind = kind.getParent()
        return chain

    def fields_of(node: Any) -> list[str]:
        out: list[str] = []
        try:
            field_list = coin.SoFieldList()
            node.getFields(field_list)
            for i in range(field_list.getLength()):
                field = field_list.get(i)
                name = str(node.getFieldName(field))
                kind = str(field.getTypeId().getName())
                # Only plain values are read. field.get() writes a field
                # out as text, and for a field holding a node - a node
                # kit's parts - that writes the node's whole subgraph,
                # which crashed FreeCAD (SIGSEGV in SoField::countWriteRefs).
                # Coin names field types without "So": "SFFloat".
                bare = kind[2:] if kind.startswith("So") else kind
                if bare in _PLAIN_FIELDS:
                    try:
                        value = str(field.get()).strip()[:120]
                    except Exception:
                        value = "?"
                elif bare.startswith("MF") and not any(
                        w in bare for w in ("Node", "Path", "Engine")):
                    try:
                        value = "%d values" % field.getNum()
                    except Exception:
                        value = "?"
                else:
                    value = "(not read)"
                out.append("%s (%s) = %s" % (name, kind, value))
        except Exception as exc:
            out.append("fields not readable: %s" % exc)
        return out

    seen: set[int] = set()
    words = ("dragger", "gizmo", "manip", "arrow")
    if coin is not None:
        for label, root in roots:
            if root is None:
                continue
            search = coin.SoSearchAction()
            search.setType(coin.SoNode.getClassTypeId(), True)
            search.setInterest(coin.SoSearchAction.ALL)
            search.setSearchingAll(True)
            search.apply(root)
            paths = search.getPaths()
            say("\n%s: %d nodes" % (label, paths.getLength()))
            for i in range(paths.getLength()):
                node = paths[i].getTail()
                chain = ancestry(node)
                if not any(w in " ".join(chain).lower() for w in words):
                    continue
                key = hash(str(node.this)) if hasattr(node, "this") \
                    else id(node)
                if key in seen:
                    continue
                seen.add(key)
                say("\n  %s" % " < ".join(chain))
                fields = fields_of(node)
                for line in fields:
                    say("      %s" % line)
                found["nodes"].append({"types": chain, "fields": fields})

    say("\nTask panel number fields")
    try:
        from ..qt import QtWidgets
        main = Gui.getMainWindow()
        for widget in main.findChildren(QtWidgets.QWidget):
            kind = widget.metaObject().className()
            if "QuantitySpinBox" in kind or "SpinBox" in kind:
                if not widget.isVisible():
                    continue
                entry = "%s %r = %s" % (kind, widget.objectName(),
                                        widget.property("text")
                                        or widget.property("value"))
                say("  " + entry)
                found["fields"].append(entry)
    except Exception as exc:
        say("  not readable: %s" % exc)

    say("\nPreferences mentioning gizmos, draggers or steps")

    def walk(group: Any, path: str, depth: int = 0) -> None:
        try:
            contents = group.GetContents() or []
        except Exception:
            contents = []
        for item in contents:
            try:
                kind, key, value = item
            except (TypeError, ValueError):
                continue
            text = ("%s/%s" % (path, key)).lower()
            if any(w in text for w in ("gizmo", "dragger", "increment",
                                       "step", "snap")):
                entry = "%s/%s = %r (%s)" % (path, key, value, kind)
                say("  " + entry)
                found["params"].append(entry)
        try:
            subgroups = group.GetGroups() or []
        except Exception:
            subgroups = []
        for name in subgroups:
            if depth < 5:
                walk(group.GetGroup(name), "%s/%s" % (path, name), depth + 1)

    try:
        walk(App.ParamGet("User parameter:BaseApp"), "BaseApp")
    except Exception as exc:
        say("  could not walk the parameter tree: %s" % exc)
    say("\n=== end ===")

    text = "\n".join(lines)
    App.Console.PrintMessage(text + "\n")
    if to_file:
        path = App.getUserAppDataDir() + "nxt-draggers.txt"
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
        App.Console.PrintMessage("Nxt: written to %s\n" % path)
    return found


def pick() -> list[dict[str, Any]]:
    """What the panel makes of the current 3D selection.

        from freecad.nxt.tree import probe; probe.pick()

    Select a face in the 3D view first. For each selected element, prints
    the object FreeCAD selected, the element's history from the shape's
    element map, and the row the panel reveals for it (see picking.py).
    """
    from . import picking
    out: list[dict[str, Any]] = []
    for sel in Gui.Selection.getSelectionEx("", 0):
        doc = sel.Document
        for sub in sel.SubElementNames or [""]:
            leaf = sel.Object.getSubObject(sub, retType=1) if sub else None
            leaf = leaf or sel.Object
            element = picking.element_of(sub)
            mapped = picking.mapped_of(sub)
            history: dict[str, Any] = {}
            for name in (element, mapped, ";" + mapped):
                try:
                    history[name] = leaf.Shape.getElementHistory(name)
                except Exception as exc:
                    history[name] = "error: %s" % exc
            made_by = picking.origin(leaf, sub)
            row = picking.target(doc, sel.Object.Name, sub)
            entry = {"top": sel.Object.Name, "sub": sub, "leaf": leaf.Name,
                     "element": element, "mapped": mapped,
                     "history": history,
                     "made_by": getattr(made_by, "Name", None),
                     "ids": {o.Name: o.ID for o in doc.Objects},
                     "row": row}
            out.append(entry)
            App.Console.PrintMessage("%s\n" % entry)
    return out


class _VisibilityWatch:
    """Prints every visibility change FreeCAD reports, and from where."""

    def slotChangedObject(self, obj: Any, prop: str) -> None:  # noqa: N802
        if prop == "Visibility":
            owner = getattr(obj, "Object", obj)
            side = "Gui" if owner is not obj else "App"
            view = getattr(owner, "ViewObject", None)
            App.Console.PrintMessage(
                "visibility [%s] %s -> %s (view says %s)\n"
                % (side, owner.Name, getattr(obj, "Visibility", "?"),
                   getattr(view, "Visibility", "?")))


_watch: _VisibilityWatch | None = None


def watch_visibility(on: bool = True) -> None:
    """Report visibility changes as FreeCAD announces them.

        probe.watch_visibility()        # then hide something any way
        probe.watch_visibility(False)   # stop

    For the eye getting out of step: shows whether a change made outside
    the panel (Space in the 3D view, the console) reaches the observers
    the panel listens on, which side it arrives on, and what the view
    object reports at that moment.
    """
    global _watch
    if _watch is not None:
        for remove in (App.removeDocumentObserver,
                       Gui.removeDocumentObserver):
            try:
                remove(_watch)
            except Exception:
                pass
        _watch = None
    if on:
        _watch = _VisibilityWatch()
        App.addDocumentObserver(_watch)
        Gui.addDocumentObserver(_watch)
        App.Console.PrintMessage("Nxt: watching visibility changes\n")


def run(doc: Any = None, widen: bool = False) -> scene.Snapshot | None:
    App.Console.PrintMessage("\n=== Nxt panel probe ===\n")

    App.Console.PrintMessage("\nQt\n")
    _line("binding", True, "Qt %s" % QtCompat.version())
    quick = qtquick.available()
    _line("QtQuick / QtQuickWidgets importable", quick,
          "" if quick else "the panel cannot start without these")

    if doc is None:
        doc = App.ActiveDocument
    if doc is None:
        App.Console.PrintMessage("\nNo active document - open one and re-run "
                                 "for the structural checks.\n")
        return None

    App.Console.PrintMessage("\nView provider API (%d objects)\n"
                             % len(doc.Objects))

    api = {"claimChildren": 0, "proxyClaimChildren": 0, "groupOnly": 0,
           "none": 0}
    dnd = {"canDragObject": 0, "dragObject": 0,
           "canDropObject": 0, "dropObject": 0}

    for obj in doc.Objects:
        vo = getattr(obj, "ViewObject", None)
        if vo is not None and callable(getattr(vo, "claimChildren", None)):
            api["claimChildren"] += 1
        elif vo is not None and callable(
                getattr(getattr(vo, "Proxy", None), "claimChildren", None)):
            api["proxyClaimChildren"] += 1
        elif getattr(obj, "Group", None) is not None:
            api["groupOnly"] += 1
        else:
            api["none"] += 1
        for method in dnd:
            if vo is not None and callable(getattr(vo, method, None)):
                dnd[method] += 1

    _line("claimChildren on the view object", api["claimChildren"] > 0,
          "%d objects" % api["claimChildren"])
    _line("claimChildren via Proxy", True,
          "%d objects" % api["proxyClaimChildren"])
    _line("group-containment fallback", True, "%d objects" % api["groupOnly"])
    _line("no child source at all", True, "%d objects" % api["none"])

    for method, count in sorted(dnd.items()):
        _line("%s exposed" % method, count > 0, "%d objects" % count)

    App.Console.PrintMessage("\nObservers\n")
    probe_obj = type("_Probe", (object,), {})()
    try:
        App.addDocumentObserver(probe_obj)
        App.removeDocumentObserver(probe_obj)
        _line("App document observer", True)
    except Exception as exc:
        _line("App document observer", False, str(exc))
    try:
        Gui.addDocumentObserver(probe_obj)
        Gui.removeDocumentObserver(probe_obj)
        _line("Gui document observer", True)
    except Exception as exc:
        _line("Gui document observer", False, str(exc))
    try:
        Gui.Selection.addObserver(probe_obj)
        Gui.Selection.removeObserver(probe_obj)
        _line("selection observer", True)
    except Exception as exc:
        _line("selection observer", False, str(exc))

    # ------------------------------------------------------------------ #

    snap = scene.Snapshot(doc, widen=widen)
    App.Console.PrintMessage("\nPartition for '%s'\n" % doc.Label)
    App.Console.PrintMessage("  tree roots : %d\n" % len(snap.roots))
    App.Console.PrintMessage("  profiles   : %d (%d with findings, "
                             "%d under-constrained)\n"
                             % (len(snap.profiles),
                                len(snap.problem_profiles()),
                                len(snap.unconstrained_profiles())))
    if snap.orphan_claims:
        App.Console.PrintMessage("  multi-claimed objects: %s\n"
                                 % ", ".join(n for n, _ in snap.orphan_claims))

    App.Console.PrintMessage("\nTree\n")
    for name, depth in snap.flatten(set(snap.nodes)):
        node = snap.nodes[name]
        refs = ""
        if node.refs:
            refs = "   <> " + ", ".join(ref[1] for ref in node.refs)
        App.Console.PrintMessage("  %s%s%s\n"
                                 % ("  " * depth, node.label, refs))

    # Which solver accessors this build actually offers. The panel degrades
    # to whatever is here, so a clean gutter on a document that
    # has them means this list came back empty, not that the sketches are
    # clean.
    sketches = [doc.getObject(n) for n in snap.profiles]
    sketches = [s for s in sketches if s is not None]
    if sketches:
        App.Console.PrintMessage("\nSketcher diagnostics\n")
        App.Console.PrintMessage("  (properties on SketchObject, read - "
                                 "never solved)\n")
        for accessor, present in sorted(health.available(sketches[0]).items()):
            _line(accessor, present)
        _line("FullyConstrained property",
              health.fully_constrained(sketches[0]) is not None)
        _line("any solver accessor answers", snap.solver_findings,
              "" if snap.solver_findings else
              "gutter marks reflect document State only")

    bodies = [(n, node) for n, node in snap.nodes.items() if node.stack]
    if bodies:
        App.Console.PrintMessage("\nFeature stacks\n")
        for name, node in bodies:
            App.Console.PrintMessage("  %s (tip: %s)\n"
                                     % (node.label, node.tip or "none"))
            for feature in node.stack:
                mark = "  " if not snap.nodes[feature].after_tip else "~ "
                App.Console.PrintMessage("    %s%s\n"
                                         % (mark, snap.nodes[feature].label))
        App.Console.PrintMessage("    (~ marks features past the tip)\n")

    App.Console.PrintMessage("\nProfiles\n")
    if not snap.profiles:
        App.Console.PrintMessage("  (none)\n")
    for name in snap.profiles:
        node = snap.nodes[name]
        where = (" in %s" % node.container_label
                 if node.container_label else "")
        # The property names are the interesting part when a count surprises
        # you: they say *why* something counts as a consumer.
        used = (", ".join("%s (%s)" % (lbl, "+".join(props))
                          for _n, lbl, props in node.consumers) or
                "UNUSED")
        flag = {health.ERROR: "[ERROR]  ",
                health.WARNING: "[warn]   "}.get(node.severity, "")
        App.Console.PrintMessage("  %s%s%s  x%d  ->  %s\n"
                                 % (flag, node.label, where,
                                    len(node.consumers), used))
        if node.constrained is True:
            App.Console.PrintMessage("      fully constrained\n")
        elif node.dof is not None:
            App.Console.PrintMessage("      %d DoF\n" % node.dof)
        for note in node.notes:
            App.Console.PrintMessage("      %s\n" % note)

    App.Console.PrintMessage("\n=== end probe ===\n\n")
    return snap
