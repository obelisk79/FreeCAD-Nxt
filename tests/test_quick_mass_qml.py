"""Quick Mass's bar, shown offscreen with a stand-in for quick_mass.py.

Checks that it shows the material, unit system and mass, that each field
opens its options in a window of its own, that filtering narrows the
materials, and that picking writes back.
Needs PySide6 6.8 or later (Popup.Window).

Run with: python3 tests/test_quick_mass_qml.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import fakes  # noqa: E402
from PySide6 import QtCore, QtGui, QtQuick  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

App, Gui = fakes.install()

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


class Mass(QtCore.QObject):
    """Stand-in for quick_mass.QuickMass."""

    changed = QtCore.Signal()

    def __init__(self) -> None:
        super().__init__()
        self._materials = ["ABS-Generic", "Aluminum-Generic",
                           "Steel-Generic", "Wood-Generic", "Custom"]
        self._densities = ["1060 kg/m³", "2700 kg/m³", "7850 kg/m³",
                           "550.0 kg/m³", "1000 kg/m³"]
        self.custom_typed: list[str] = []
        self._units = ["Standard (mm, kg, s, °)",
                       "Imperial decimal (in, lb)", "MKS (m, kg, s, °)"]
        self._material = 2
        self._unit = 0

    @QtCore.Property(list, notify=changed)
    def materials(self) -> list[str]:
        return self._materials

    @QtCore.Property(list, notify=changed)
    def densities(self) -> list[str]:
        return self._densities

    @QtCore.Property(int, notify=changed)
    def material(self) -> int:
        return self._material

    @QtCore.Property(bool, notify=changed)
    def custom(self) -> bool:
        return self._material == len(self._materials) - 1

    @QtCore.Property(str, notify=changed)
    def customDensity(self) -> str:  # noqa: N802
        return "1000"

    @QtCore.Slot(str, result=bool)
    def setCustomDensity(self, text: str) -> bool:  # noqa: N802
        self.custom_typed.append(text)
        return True

    @QtCore.Property(list, notify=changed)
    def units(self) -> list[str]:
        return self._units

    @QtCore.Property(int, notify=changed)
    def unit(self) -> int:
        return self._unit

    @QtCore.Property(str, notify=changed)
    def mass(self) -> str:
        return "%.3f kg" % (1.0 + self._material + self._unit)

    @QtCore.Slot(result=QtCore.QPointF)
    def anchorOffset(self) -> QtCore.QPointF:  # noqa: N802
        return QtCore.QPointF(0, 0)

    @QtCore.Slot(int)
    def pickMaterial(self, index: int) -> None:  # noqa: N802
        self._material = index
        self.changed.emit()

    @QtCore.Slot(int)
    def pickUnit(self, index: int) -> None:  # noqa: N802
        self._unit = index
        self.changed.emit()


app = QtGui.QGuiApplication(sys.argv)
theme = Theme()
mass = Mass()


def settle(seconds: float = 0.15) -> None:
    end = QtCore.QTime.currentTime().addMSecs(int(seconds * 1000))
    while QtCore.QTime.currentTime() < end:
        app.processEvents()


def check(name: str, condition: bool) -> None:
    print("  %-56s %s" % (name, "ok" if condition else "FAIL"))
    if not condition:
        problems.append(name)


def items_of(item: Any) -> list[Any]:
    out, stack = [], [item]
    while stack:
        current = stack.pop()
        out.append(current)
        stack.extend(current.childItems())
    return out


def texts(window: QtGui.QWindow) -> list[Any]:
    return [i for i in items_of(window.contentItem())
            if i.metaObject().className().startswith("QQuickText")
            and i.property("visible")]


def text_item(window: QtGui.QWindow, text: str) -> Any:
    return next(i for i in texts(window) if i.property("text") == text)


def click(window: QtGui.QWindow, item: Any) -> None:
    point = item.mapToScene(QtCore.QPointF(item.property("width") / 2,
                                           item.property("height") / 2)
                            ).toPoint()
    QTest.mouseMove(window, point)
    settle(0.05)
    QTest.mouseClick(window, QtCore.Qt.MouseButton.LeftButton,
                     QtCore.Qt.KeyboardModifier.NoModifier, point)
    settle()


def popups() -> list[QtGui.QWindow]:
    settle(0.05)
    return [w for w in app.topLevelWindows()
            if w is not view and w.isVisible()]


view = QtQuick.QQuickView()
view.engine().addImportPath(str(QML))
view.rootContext().setContextProperty("theme", theme)
view.rootContext().setContextProperty("quickMass", mass)
view.setResizeMode(QtQuick.QQuickView.ResizeMode.SizeViewToRootObject)
view.setSource(QtCore.QUrl.fromLocalFile(str(QML / "QuickMass.qml")))
for error in view.errors():
    problems.append(error.toString())
view.show()
settle()

print("bar")
for label in ("Quick Mass", "Steel-Generic", "7850 kg/m³",
              "Standard (mm, kg, s, °)", "3.000 kg"):
    try:
        text_item(view, label)
        found = True
    except StopIteration:
        found = False
    check("shows %r" % label, found)

print("material")
click(view, text_item(view, "Steel-Generic"))
windows = popups()
check("the materials open in a window of their own", len(windows) == 1)
window = windows[0]
check("every material is offered", all(
    any(t.property("text") == m for t in texts(window))
    for m in mass.materials))
for key in ("A", "L", "U"):
    QTest.keyClick(window, getattr(QtCore.Qt.Key, "Key_" + key))
settle()
check("typing filters them", [t.property("text") for t in texts(window)
                              if t.property("text") in mass.materials]
      == ["Aluminum-Generic"])
QTest.keyClick(window, QtCore.Qt.Key.Key_Return)
settle()
check("Return picks the first left", mass.material == 1)
check("and closes the list", not popups())
check("the bar shows it", text_item(view, "Aluminum-Generic") is not None)

print("custom")
click(view, text_item(view, "Aluminum-Generic"))
window = popups()[0]
check("each material shows its density",
      text_item(window, "550.0 kg/m³") is not None)
click(window, text_item(window, "Custom"))
check("Custom is offered last and picked", mass.custom)
field = next((i for i in items_of(view.contentItem())
              if i.metaObject().className().startswith("QQuickTextInput")
              and i.property("visible")
              and i.property("text") == "1000"), None)
check("a density field appears", field is not None)
if field is not None:
    view.requestActivate()
    settle()
    field.forceActiveFocus()
    field.setProperty("text", "8000")
    QTest.keyClick(view, QtCore.Qt.Key.Key_Return)
    settle()
    check("Return sets the custom density", mass.custom_typed == ["8000"])
click(view, text_item(view, "Custom"))
window = popups()[0]
click(window, text_item(window, "Wood-Generic"))
check("another material can be picked after Custom",
      mass.material == 3 and not mass.custom)

print("units")
click(view, text_item(view, "Standard (mm, kg, s, °)"))
window = popups()[0]
click(window, text_item(window, "Imperial decimal (in, lb)"))
check("a click picks a unit system", mass.unit == 1)
check("and closes the list", not popups())
check("the mass follows", text_item(view, "3.000 kg") is not None)

view.setSource(QtCore.QUrl())
print("PROBLEMS: %d" % len(problems))
for problem in problems:
    print("  *", problem)
print("QUICK MASS QML PASSED" if not problems else "QUICK MASS QML FAILED")
sys.exit(1 if problems else 0)
