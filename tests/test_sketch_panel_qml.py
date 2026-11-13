"""The experimental sketch task panel: its bridge and both QML views.

The real bridge reads a stand-in sketch; the cards and the pill are
shown offscreen. Checks what each state shows, that a click reaches the
sketch in one undo step, and that nothing is read while the setting is
off.

Run with: python3 tests/test_sketch_panel_qml.py
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
from PySide6 import QtCore, QtGui, QtQuick, QtWidgets  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from sketch_fakes import Sketch  # noqa: E402

store: dict[str, Any] = {}
App, Gui = fakes.install(ParamGet=fakes.params(store))

from freecad.nxt.core import settings  # noqa: E402
from freecad.nxt.tools import sketch_panel  # noqa: E402
from freecad.nxt.ui.theme import Theme  # noqa: E402

QML = ROOT / "freecad" / "nxt" / "resources" / "qml"
BAD = ("binding loop", "is not defined", "cannot read property",
       "unable to assign", "typeerror", "referenceerror", "cannot assign",
       "is not a function", "required property", "cannot override")
problems: list[str] = []


def _handler(_mode: Any, _context: Any, message: str) -> None:
    if any(token in str(message).lower() for token in BAD):
        problems.append(str(message))
        print(message)


QtCore.qInstallMessageHandler(_handler)

app = QtWidgets.QApplication(sys.argv)
sketch = Sketch()
selected: list[str] = []
commands: list[str] = []
Gui.ActiveDocument = types.SimpleNamespace(
    getInEdit=lambda: sketch.ViewObject)


def _add(_doc: str, _obj: str, name: str) -> None:
    selected.append(name)


Gui.Selection = types.SimpleNamespace(
    getSelectionEx=lambda: [types.SimpleNamespace(
        ObjectName="Sketch", SubElementNames=selected)],
    clearSelection=selected.clear, addSelection=_add)
Gui.runCommand = commands.append


def settle(seconds: float = 0.15) -> None:
    end = QtCore.QTime.currentTime().addMSecs(int(seconds * 1000))
    while QtCore.QTime.currentTime() < end:
        app.processEvents()


def check(name: str, condition: bool) -> None:
    print("  %-58s %s" % (name, "ok" if condition else "FAIL"))
    if not condition:
        problems.append(name)


def items_of(item: Any) -> list[Any]:
    out, stack = [], [item]
    while stack:
        current = stack.pop()
        out.append(current)
        stack.extend(current.childItems())
    return out


def shown(item: Any) -> bool:
    while item is not None:
        if not item.property("visible"):
            return False
        item = item.parentItem()
    return True


def texts(view: QtQuick.QQuickView) -> list[str]:
    return [str(i.property("text")) for i in items_of(view.contentItem())
            if i.inherits("QQuickText") and shown(i)
            and i.property("text")]


def text_item(view: QtQuick.QQuickView, text: str) -> Any:
    return next(i for i in items_of(view.contentItem())
                if i.property("text") == text and shown(i))


def click(view: QtQuick.QQuickView, item: Any) -> None:
    point = item.mapToScene(QtCore.QPointF(item.property("width") / 2,
                                           item.property("height") / 2)
                            ).toPoint()
    QTest.mouseClick(view, QtCore.Qt.MouseButton.LeftButton,
                     QtCore.Qt.KeyboardModifier.NoModifier, point)
    settle()


def pick(*names: str) -> None:
    selected[:] = names
    bridge.touch()
    settle()


def load(source: str) -> QtQuick.QQuickView:
    view = QtQuick.QQuickView()
    view.engine().addImportPath(str(QML))
    view.rootContext().setContextProperty("theme", theme)
    view.rootContext().setContextProperty("sketch", bridge)
    view.setResizeMode(QtQuick.QQuickView.ResizeMode.SizeViewToRootObject)
    view.setSource(QtCore.QUrl.fromLocalFile(str(QML / source)))
    for error in view.errors():
        problems.append(error.toString())
    view.show()
    settle()
    return view


theme = Theme()
bridge = sketch_panel.SketchBridge()

print("off by default")
check("the setting starts off", settings.DEFAULTS["SketchPanel"] is False)
bridge.refresh()
check("nothing is read while it is off", not bridge.active)

settings.put("SketchPanel", True)
bridge.refresh()
check("the edited sketch is read once it is on", bridge.active)

cards = load("SketchPanel.qml")
pill = load("SketchPill.qml")

print("quiet")
check("the cards show only the two lists' rows",
      sorted(texts(cards)) == ["4", "4", "Browse constraints",
                               "Browse elements"])
check("the pill links the degrees of freedom", "3 DoF" in texts(pill))
click(pill, text_item(pill, "3 DoF"))
check("the link selects what is free",
      commands == ["Sketcher_SelectElementsWithDoFs"])
quiet_height = cards.rootObject().property("implicitHeight")


def accepted_press(view: QtQuick.QQuickView, item: Any) -> bool:
    """Whether a press on `item` stays in the view, not the 3D view."""
    point = item.mapToScene(QtCore.QPointF(2, 2))
    press = QtGui.QMouseEvent(
        QtCore.QEvent.Type.MouseButtonPress, point, point,
        QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.MouseButton.LeftButton,
        QtCore.Qt.KeyboardModifier.NoModifier)
    press.setAccepted(False)
    QtCore.QCoreApplication.sendEvent(view, press)
    accepted = press.isAccepted()
    release = QtGui.QMouseEvent(
        QtCore.QEvent.Type.MouseButtonRelease, point, point,
        QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.MouseButton.NoButton,
        QtCore.Qt.KeyboardModifier.NoModifier)
    QtCore.QCoreApplication.sendEvent(view, release)
    settle(0.5)
    return accepted


check("a press on the link stays in the pill",
      accepted_press(pill, text_item(pill, "3 DoF")))
check("so does one on its plain parts",
      accepted_press(pill, pill.rootObject()))
commands.clear()

print("an element")
pick("Edge1")
check("its card names it", "Line 1" in texts(cards))
check("and its constraints as chips",
      {"Constraints on it", "1  Horizontal", "3  Coincident"}
      <= set(texts(cards)))
click(cards, text_item(cards, "3  Coincident"))
settle(0.6)         # a single tap waits out the double-click interval
check("a chip selects its constraint", selected == ["Constraint3"])
check("whose card shows its geometry as chips",
      {"Coincident 3", "Geometry", "Line 1", "Line 2"} <= set(texts(cards)))
click(cards, text_item(cards, "Line 2"))
settle(0.6)
check("a geometry chip selects it", selected == ["Edge2"])
pick("Edge1")
check("the cards grow to hold it",
      cards.rootObject().property("implicitHeight") > quiet_height)
bridge.setConstruction(0, True)
settle()
check("Construction is set in one undo step",
      0 in sketch.construction and sketch.Document.steps
      == ["Toggle construction geometry", "commit"])
check("and the sketch is solved, so it redraws", sketch.solved == 1)

print("a constraint")
pick("Constraint2")
check("its card shows what it is, and its value",
      {"Distance 2", "32.00 mm", "Driving", "Active"} <= set(texts(cards)))
pick("Constraint1")
check("Driving is offered for a dimension only",
      "Driving" not in texts(cards) and "Active" in texts(cards))
bridge.rename(0, " Level ")
settle()
check("a name is kept, trimmed", sketch.Constraints[0].Name == "Level")

print("a problem")
pick()
sketch.ConflictingConstraints = [2, 4]
bridge.touch()
settle()
check("the cards list the conflicting constraints",
      {"Over-constrained", "2", "4"} <= set(texts(cards)))
check("the pill names the problem and links them",
      {"Over-constrained", "2, 4"} <= set(texts(pill)))
click(pill, text_item(pill, "2, 4"))
check("the link selects them",
      commands[-1] == "Sketcher_SelectConflictingConstraints")
bridge.setDriving(1, False)
settle()
check("a dimension can be made a reference",
      sketch.Constraints[1].Driving is False)
bridge.remove(3)
sketch.ConflictingConstraints = []
settle()
check("a constraint can be deleted", len(sketch.Constraints) == 3)
check("and the cards go quiet again",
      "Over-constrained" not in texts(cards))

print("settings")
pill.rootObject().setProperty("open", True)
settle()
check("the pill opens the settings above itself",
      {"Grid", "Snap", "Auto constraints", "Normal", "Construction",
       "External"} <= set(texts(pill)))
bridge.turn("grid", False)
bridge.turn("snapToGrid", True)
bridge.setSnapAngle("15°")
bridge.drawAbove(1)
settle()
check("a view setting reaches the sketch's view",
      sketch.ViewObject.ShowGrid is False)
check("a parameter setting reaches FreeCAD's parameters",
      store.get("SnapToGrid") is True and store.get("SnapAngle") == 15.0)
check("the render order swaps two places",
      [store.get(name) for name in sketch_panel.ORDER] == [2, 1, 3])
check("and the pill shows the new order",
      bridge.switches["order"] == [2, 1, 3])

print("lists")
bridge.browse("constraints", True)
check("a list can be asked for", bridge.shows("constraints")
      and not bridge.shows("elements"))

print("leaving")
Gui.ActiveDocument = types.SimpleNamespace(getInEdit=lambda: None)
bridge.touch()
settle()
check("the bridge goes idle with the edit", not bridge.active)

for view in (cards, pill):
    view.setSource(QtCore.QUrl())
print("PROBLEMS: %d" % len(problems))
for problem in problems:
    print("  *", problem)
print("SKETCH PANEL QML PASSED" if not problems
      else "SKETCH PANEL QML FAILED")
sys.exit(1 if problems else 0)
