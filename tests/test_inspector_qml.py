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

import test_inspector as fakes  # noqa: E402  (installs the FreeCAD stub)
from PySide6 import QtCore, QtQuick, QtWidgets  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

App = sys.modules["FreeCAD"]
App.ParamGet = lambda _group: types.SimpleNamespace(
    GetBool=lambda _k, d: d, GetInt=lambda _k, d: d,
    GetFloat=lambda _k, d: d, GetString=lambda _k, d: d)

from freecad.nxt.tree import inspector  # noqa: E402
from freecad.nxt.tree.theme import Theme  # noqa: E402

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
editors = items_of(root, "ValueEditor")
widths = sorted({round(e.property("width")) for e in editors})
check("compact editors pair up, wide ones take a row", len(widths) == 2
      and abs(widths[1] - 2 * widths[0]) < 20)
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
check("with Edit… for it and the link", len(edits) == 2)
for edit in edits:
    click(view, edit)
check("Edit… hands the property to FreeCAD's editor",
      {("native", "ThreadData"), ("native", "BaseObject")}
      <= set(bridge.calls))
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

print("PROBLEMS: %d" % len(problems))
for problem in problems:
    print("  *", problem)
print("INSPECTOR QML PASSED" if not problems else "INSPECTOR QML FAILED")
sys.exit(1 if problems else 0)
