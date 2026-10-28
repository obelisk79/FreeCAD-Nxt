"""The Property Inspector's QML, loaded offscreen against a stub bridge.

Uses the real Theme and real `inspector.describe` output for a stand-in
Helix, a stand-in addon screw and a two-object selection, and checks that
each lays out without QML errors and that edits reach the bridge. Needs
PySide6.

Run with: python3 tests/test_inspector_qml.py
"""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import fakes  # noqa: E402
import test_inspector_templates as pads  # noqa: E402
from PySide6 import QtCore, QtQuick, QtWidgets  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

App, Gui = fakes.install()

from freecad.nxt.inspector import layout as inspector  # noqa: E402
from freecad.nxt.ui.theme import Theme  # noqa: E402

QML = ROOT / "freecad" / "nxt" / "resources" / "qml"
BAD = ("binding loop", "is not defined", "cannot read property",
       "unable to assign", "typeerror", "referenceerror", "cannot assign",
       "is not a function", "required property")
problems: list[str] = []


def _handler(_mode: Any, _context: Any, message: str) -> None:
    if any(token in str(message).lower() for token in BAD):
        problems.append(str(message))
        print(message)


QtCore.qInstallMessageHandler(_handler)


class Bridge(QtCore.QObject):
    """The InspectorBridge's QML surface, recording what QML asks."""

    changed = QtCore.Signal()

    def __init__(self, groups: list[dict[str, Any]]) -> None:
        super().__init__()
        self._groups = groups
        self.calls: list[tuple[Any, ...]] = []

    @QtCore.Property(list, notify=changed)
    def groups(self) -> list[dict[str, Any]]:
        return self._groups

    @QtCore.Property(str, notify=changed)
    def owner(self) -> str:
        return "Doc#Helix"

    @QtCore.Property(str, notify=changed)
    def title(self) -> str:
        return "Helix"

    @QtCore.Property(str, notify=changed)
    def tab(self) -> str:
        return "Data"

    @QtCore.Slot(str)
    def setTab(self, tab: str) -> None:
        self.calls.append(("tab", tab))

    @QtCore.Slot(str)
    def setFilter(self, text: str) -> None:
        self.calls.append(("filter", text))

    @QtCore.Slot(str, bool)
    def setGroupOpen(self, name: str, opened: bool) -> None:
        self.calls.append(("group", name, opened))

    @QtCore.Slot(str, "QVariant", str)
    def setValue(self, prop: str, value: Any, unit: str) -> None:
        self.calls.append(("value", prop, value, unit))

    @QtCore.Slot(str, str, str)
    def setPart(self, prop: str, part: str, text: str) -> None:
        self.calls.append(("part", prop, part, text))

    @QtCore.Slot(str, str)
    def pickColour(self, prop: str, current: str) -> None:
        self.calls.append(("colour", prop))

    @QtCore.Slot(str)
    def editNative(self, prop: str) -> None:
        self.calls.append(("native", prop))

    @QtCore.Property(str, notify=changed)
    def picking(self) -> str:
        return ""

    @QtCore.Slot(str, str)
    def removeLink(self, prop: str, key: str) -> None:
        self.calls.append(("unlink", prop, key))

    @QtCore.Slot(str)
    def pickLinks(self, prop: str) -> None:
        self.calls.append(("pick", prop))

    @QtCore.Slot(str, str, str, result=str)
    def editVariable(self, prop: str, name: str, tip: str) -> str:
        self.calls.append(("rename", prop, name, tip))
        if name == "Taken":
            return "That name's already taken."
        # Rebuilt inside the call, the worst case: the field that asked
        # is gone before the call returns.
        varset = pads.varset()
        varset._props[prop] = varset._props[prop][:2] + (tip + " ",)
        self._groups = inspector.describe([varset])
        self.changed.emit()
        return ""

    @QtCore.Slot(str, str, str, result=str)
    def addVariable(self, type_id: str, name: str, tip: str) -> str:
        self.calls.append(("add", type_id, name, tip))
        return ""

    @QtCore.Slot(result="QVariantList")
    def variableTypes(self) -> list[dict[str, str]]:
        return [{"id": "App::PropertyLength", "label": "Length"},
                {"id": "App::PropertyBool", "label": "Yes/no"}]


app = QtWidgets.QApplication(sys.argv)
theme = Theme()


KEEP: list[Any] = []


def finish(view: QtQuick.QQuickView, bridge: Bridge) -> None:
    """Unload a case's view before the next one loads.

    A closed view still evaluates its bindings, and would read a bridge the
    next case has replaced.
    """
    view.setSource(QtCore.QUrl())
    view.close()
    KEEP.append((view, bridge))
    settle()


def settle(seconds: float = 0.15) -> None:
    end = QtCore.QTime.currentTime().addMSecs(int(seconds * 1000))
    while QtCore.QTime.currentTime() < end:
        app.processEvents()


def load(bridge: Bridge) -> tuple[QtQuick.QQuickView, Any]:
    view = QtQuick.QQuickView()
    view.engine().addImportPath(str(QML))
    view.rootContext().setContextProperty("inspector", bridge)
    view.rootContext().setContextProperty("theme", theme)
    view.setSource(QtCore.QUrl.fromLocalFile(
        str(QML / "Inspector.qml")))
    for error in view.errors():
        problems.append(error.toString())
    view.resize(340, 900)
    view.show()
    settle()
    return view, view.rootObject()


def items_of(root: Any, class_prefix: str) -> list[Any]:
    out, stack = [], [root]
    while stack:
        item = stack.pop()
        if item.metaObject().className().startswith(class_prefix):
            out.append(item)
        stack.extend(item.childItems())
    return out


def texts(root: Any) -> set[str]:
    return {i.property("text") for i in items_of(root, "QQuickText")}


def click(view: QtQuick.QQuickView, item: Any) -> None:
    centre = item.mapToScene(QtCore.QPointF(item.property("width") / 2,
                                            item.property("height") / 2))
    QTest.mouseClick(view, QtCore.Qt.MouseButton.LeftButton,
                     QtCore.Qt.KeyboardModifier.NoModifier, centre.toPoint())
    settle()


def check(name: str, condition: bool) -> None:
    print("  %-52s %s" % (name, "ok" if condition else "FAIL"))
    if not condition:
        problems.append(name)


# --- a native object with no template ----------------------------------- #
print("native: Part::Helix")
helix = fakes.helix()
bridge = Bridge(inspector.describe([helix]))
view, root = load(bridge)
shown = texts(root)
check("groups are FreeCAD's, own group first",
      "Helix" in shown and "Base" in shown)
check("labels split like the native panel", "Local Coord" in shown)
check("the unit sits apart from the number", "mm" in shown)

pitch = next(i for i in items_of(root, "QQuickTextInput")
             if i.property("text") == "5.00")
click(view, pitch)
check("entering a field selects the number",
      pitch.property("selectedText") == "5.00")
QTest.keyClick(view, QtCore.Qt.Key.Key_7)
QTest.keyClick(view, QtCore.Qt.Key.Key_Return)
settle()
check("Return applies, with the field's unit",
      ("value", "Pitch", "7", "mm") in bridge.calls)

base = next(i for i in items_of(root, "QQuickText")
            if i.property("text") == "Base")
click(view, base)
settle()
check("a collapsed group opens, and the bridge remembers it",
      ("group", "Base", True) in bridge.calls)
parts = [i for i in items_of(root, "QQuickTextInput")
         if i.property("text") in ("1", "2", "3", "0", "90")]
check("a placement shows its seven components", len(parts) == 7)
starts = {round(e.mapToScene(QtCore.QPointF(0, 0)).x())
          for e in items_of(root, "ValueEditor") if e.property("visible")}
check("every editor starts after the same label column", len(starts) == 1)
finish(view, bridge)

# --- an addon object with no template ------------------------------------ #
print("addon: Fasteners::Screw")
screw = fakes.Thing("Fasteners::Screw", {
    "Diameter": ("Parameters", "App::PropertyEnumeration", "M6"),
    "Thread": ("Parameters", "App::PropertyBool", True),
    "Offset": ("Parameters", "App::PropertyLength",
               fakes.Quantity("0.00 mm")),
    "BaseObject": ("Parameters", "App::PropertyLinkSub",
                   (types.SimpleNamespace(Label="Plate"), ["Face1"])),
    "ThreadData": ("Parameters", "App::PropertyPythonObject", "<cache>"),
})
bridge = Bridge(inspector.describe([screw]))
view, root = load(bridge)
shown = texts(root)
check("its own group is shown", "Parameters" in shown)
check("a link shows what it points at", "Plate" in shown)
check("an unknown kind shows as text", "<cache>" in shown)
edits = [i for i in items_of(root, "QQuickText")
         if i.property("text") == "Edit…" and i.property("visible")]
check("with Edit… for it", len(edits) == 1)
for edit in edits:
    click(view, edit)
check("Edit… hands the property to FreeCAD's editor",
      ("native", "ThreadData") in bridge.calls)
check("a link is a chip naming its sub-element", "Plate.Face1" in shown)
remove = next(i for i in items_of(root, "QQuickText")
              if i.property("text") == "×" and i.property("visible"))
click(view, remove)
check("its × removes it", ("unlink", "BaseObject", "0") in bridge.calls)
plus = next(i for i in items_of(root, "QQuickText")
            if i.property("text") == "+" and i.property("visible"))
click(view, plus)
check("+ starts picking for it", ("pick", "BaseObject") in bridge.calls)
check("a short choice is joined buttons, a yes/no a switch",
      any(i.property("visible") for i in items_of(root, "Segmented"))
      or any(i.property("visible") for i in items_of(root, "NxtSwitch")))
finish(view, bridge)

# --- two objects at once ------------------------------------------------- #
print("several: two helices")
other = fakes.helix(Pitch=("Helix", "App::PropertyLength",
                           fakes.Quantity("8.00 mm")))
bridge = Bridge(inspector.describe([fakes.helix(), other]))
view, root = load(bridge)
mixed = [i for i in items_of(root, "QQuickText")
         if i.property("text") == "— mixed" and i.property("visible")]
check("a differing value shows as mixed", len(mixed) == 1)
finish(view, bridge)

# --- a Pad, laid out by its template ------------------------------------- #
print("template: PartDesign::Pad")
bridge = Bridge(inspector.describe([pads.modern(SideType="Two sides")]))
view, root = load(bridge)
shown = texts(root)
check("the template's cards and the rest's heading",
      {"Extent", "Direction", "Everything else"} <= shown
      and "Direction" not in [g["name"] for g in bridge._groups])
check("two sides give two titled columns",
      {"First side", "Second side"} <= shown)
check("Type is a drop-down showing its readable label",
      any("Dimension" in (t or "") for t in shown))
check("no Symmetric switch beside Sides", "Symmetric" in shown
      and not any(i.property("text") == "Symmetric"
                  for i in items_of(root, "NxtSwitch")))
custom = next(i for i in items_of(root, "QQuickText")
              if i.property("text") == "Custom")
click(view, custom)
check("a two-state choice sets the yes/no",
      ("value", "UseCustomVector", True, "") in bridge.calls)
toggles = [i for i in items_of(root, "GlyphToggle")
           if i.property("visible")]
click(view, next(i for i in toggles if i.property("tip") == "Reversed"))
check("Reversed is a button after Direction",
      ("value", "Reversed", True, "") in bridge.calls)
two = next(i for i in items_of(root, "QQuickText")
           if i.property("text") == "One side")
click(view, two)
check("Sides is a segmented control",
      ("value", "SideType", "One side", "") in bridge.calls)
finish(view, bridge)

# --- a choice that rebuilds the form ------------------------------------- #
print("template: a drop-down choice that changes the fields")


class Rebuilding(Bridge):
    """Lays the form out again after every edit, as the real bridge does."""

    @QtCore.Slot(str, "QVariant", str)
    def setValue(self, prop: str, value: Any, unit: str) -> None:
        self.calls.append(("value", prop, value, unit))
        self._groups = inspector.describe([pads.modern(**{prop: value})])
        self.changed.emit()


bridge = Rebuilding(inspector.describe([pads.modern()]))
view, root = load(bridge)
kind = next(i for i in items_of(root, "DropBox")
            if "Dimension" in (i.property("text") or ""))
click(view, kind)
# The list opens on the window's content item, above the whole panel.
choice = next(i for i in items_of(view.contentItem(), "QQuickText")
              if i.property("text") == "Up to face" and i.property("visible"))
click(view, choice)
settle()
check("the choice reached the bridge",
      ("value", "Type", "UpToFace", "") in bridge.calls)
check("the list closed though its field was rebuilt",
      not [i for i in items_of(view.contentItem(), "ChoiceList")
           if i.property("visible")])
check("the panel still takes clicks",
      any(i.property("text") == "Offset"
          for i in items_of(root, "QQuickText")))
finish(view, bridge)

# --- a VarSet: its variables by name, edited in place -------------------- #
print("template: a VarSet's variables")
bridge = Bridge(inspector.describe([pads.varset()]))
view, root = load(bridge)
fields = [f for f in items_of(root, "VariableField")
          if not f.property("adding")]
values = [e for f in fields for e in items_of(f, "ValueEditor")
          if e.property("visible")]
lefts = {round(e.mapToScene(QtCore.QPointF(0, 0)).x()) for e in values}
check("three variables, each value the same width",
      len(values) == 3
      and {e.property("width") for e in values} == {theme.valueWidth})
check("the values line up", len(lefts) == 1)
long_label = next(t for f in fields for t in items_of(f, "QQuickText")
                  if (t.property("text") or "").startswith("Spindle"))
check("a long name is shortened, not the value", long_label.property(
    "truncated"))
check("its tooltip names it in full", next(
    f for f in fields if f.property("spec")["name"].startswith("Spindle")
).property("tipText") == ("SpindleClearanceHeightAboveTheSpoilboard\n"
                          "Gap under the gantry"))
first = next(f for f in fields if f.property("spec")["name"] == "BaseLength")
QtCore.QMetaObject.invokeMethod(first, "open")
settle()
check("edit opens the name and tooltip in place",
      first.property("expanded"))
QtCore.QMetaObject.invokeMethod(first, "save")
settle()
check("save renames through the bridge",
      ("rename", "BaseLength", "BaseLength", "Across the frame")
      in bridge.calls and not first.property("expanded"))
second = next(f for f in items_of(root, "VariableField")
              if not f.property("adding")
              and f.property("spec")["name"] == "RailCount")
QtCore.QMetaObject.invokeMethod(second, "open")
settle()
second.findChildren(QtCore.QObject)  # still alive before the clash
for text_field in items_of(second, "TextField"):
    if text_field.property("placeholder") == "FrameWidth":
        text_field.setProperty("text", "Taken")
QtCore.QMetaObject.invokeMethod(second, "save")
settle()
check("a refused name keeps the form open with why",
      second.property("expanded")
      and "taken" in second.property("error"))
adders = [f for f in items_of(root, "VariableField") if f.property("adding")]
check("one add-variable form", len(adders) == 1)
if adders:
    QtCore.QMetaObject.invokeMethod(adders[0], "open")
    settle()
    check("the add form opens with a type chosen",
          adders[0].property("expanded")
          and adders[0].property("typeId") == "App::PropertyLength")
    QtCore.QMetaObject.invokeMethod(adders[0], "close")
finish(view, bridge)

bridge = Bridge(inspector.describe([pads.varset("A"), pads.varset("B")]))
view, root = load(bridge)
fields = items_of(root, "VariableField")
check("two VarSets: values only, no edit or add",
      len(fields) == 3 and not any(f.property("editable") for f in fields))
finish(view, bridge)

print("PROBLEMS: %d" % len(problems))
for problem in problems:
    print("  *", problem)
print("INSPECTOR QML PASSED" if not problems else "INSPECTOR QML FAILED")
sys.exit(1 if problems else 0)
