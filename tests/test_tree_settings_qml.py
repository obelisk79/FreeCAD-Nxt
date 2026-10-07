"""The tree's quick settings, opened offscreen from a stand-in panel.

Checks that the popup opens in a window of its own, shows what the store
holds, writes back what is picked - by mouse and by keyboard - and that
the switch follows the store rather than the last click.
Needs PySide6 6.8 or later (Popup.Window).

Run with: python3 tests/test_tree_settings_qml.py
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

import test_inspector  # noqa: E402,F401  (installs the FreeCAD stub)
from PySide6 import QtCore, QtGui, QtQuick  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

App = sys.modules["FreeCAD"]
App.ParamGet = lambda _group: types.SimpleNamespace(
    GetBool=lambda _k, d: d, GetInt=lambda _k, d: d,
    GetFloat=lambda _k, d: d, GetString=lambda _k, d: d)

from freecad.nxt.tree.theme import Theme  # noqa: E402

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


class Prefs(QtCore.QObject):
    """Stand-in for tree/prefs.Preferences: a store that records writes."""

    changed = QtCore.Signal()

    def __init__(self) -> None:
        super().__init__()
        self.store: dict[str, Any] = {
            "PartLayout": "expression", "RowDensity": "normal",
            "ReferenceChips": "problems", "EditOnDoubleClick": True,
            "TreeLines": False}
        self.writes: list[tuple[str, Any]] = []
        self.opened = 0

    @QtCore.Property("QVariantMap", notify=changed)
    def values(self) -> dict[str, Any]:
        return dict(self.store)

    @QtCore.Slot(str, "QVariant")
    def set(self, key: str, value: Any) -> None:
        self.writes.append((key, value))
        self.store[key] = value
        self.changed.emit()

    @QtCore.Slot()
    def openPage(self) -> None:  # noqa: N802
        self.opened += 1


HOST = """
import QtQuick
import Nxt
Rectangle {
    id: host
    width: 120; height: 200
    Component { id: popupComponent; TreeSettings {} }
    function open() {
        var popup = popupComponent.createObject(host);
        popup.x = 10; popup.y = 10;
        popup.open();
        return popup;
    }
}
"""

app = QtGui.QGuiApplication(sys.argv)
theme = Theme()
prefs = Prefs()


def settle(seconds: float = 0.15) -> None:
    end = QtCore.QTime.currentTime().addMSecs(int(seconds * 1000))
    while QtCore.QTime.currentTime() < end:
        app.processEvents()


def check(name: str, condition: bool) -> None:
    print("  %-56s %s" % (name, "ok" if condition else "FAIL"))
    if not condition:
        problems.append(name)


view = QtQuick.QQuickView()
view.engine().addImportPath(str(QML))
view.rootContext().setContextProperty("theme", theme)
view.rootContext().setContextProperty("prefs", prefs)
host_file = ROOT / "tests" / "_settings_host.qml"
host_file.write_text(HOST, encoding="utf-8")
view.setSource(QtCore.QUrl.fromLocalFile(str(host_file)))
host_file.unlink()
for error in view.errors():
    problems.append(error.toString())
view.show()
settle()
root = view.rootObject()


def open_popup() -> None:
    QtCore.QMetaObject.invokeMethod(
        root, "open", QtCore.Qt.ConnectionType.DirectConnection,
        QtCore.Q_RETURN_ARG("QVariant"))
    settle()


def popup_windows() -> list[QtGui.QWindow]:
    settle(0.05)
    return [w for w in app.topLevelWindows()
            if w is not view and w.isVisible()]


def items_of(item: Any) -> list[Any]:
    out, stack = [], [item]
    while stack:
        current = stack.pop()
        out.append(current)
        stack.extend(current.childItems())
    return out


def text_item(window: QtGui.QWindow, text: str) -> Any:
    return next(i for i in items_of(window.contentItem())
                if i.metaObject().className().startswith("QQuickText")
                and i.property("text") == text and i.property("visible"))


def click(window: QtGui.QWindow, item: Any) -> None:
    point = item.mapToScene(QtCore.QPointF(item.property("width") / 2,
                                           item.property("height") / 2)
                            ).toPoint()
    QTest.mouseMove(window, point)
    settle(0.05)
    QTest.mouseClick(window, QtCore.Qt.MouseButton.LeftButton,
                     QtCore.Qt.KeyboardModifier.NoModifier, point)
    settle()


def switch_of(window: QtGui.QWindow,
              label: str = "Double-click a face to edit its feature"
              ) -> Any:
    """The switch with this label (a Switch, whatever its QML type)."""
    return next(i for i in items_of(window.contentItem())
                if i.property("text") == label
                and i.property("checked") is not None)


print("opening")
open_popup()
windows = popup_windows()
check("it opens in a window of its own", len(windows) == 1)
window = windows[0]
check("wider than the panel", window.width() > view.width())
for label in ("Tree settings", "Expression rows", "Compact", "Problems",
              "Double-click a face to edit its feature",
              "More preferences…"):
    try:
        text_item(window, label)
        found = True
    except StopIteration:
        found = False
    check("shows %r" % label, found)
check("the switch shows the stored value",
      switch_of(window).property("checked") is True)

print("mouse")
click(window, text_item(window, "Nested"))
check("a segment writes its value", prefs.writes[-1] == ("PartLayout",
                                                         "nested"))
click(window, text_item(window, "Roomy"))
check("each control writes its own key",
      prefs.writes[-1] == ("RowDensity", "roomy"))
click(window, switch_of(window))
check("the switch writes false", prefs.writes[-1]
      == ("EditOnDoubleClick", False))
check("and shows it", switch_of(window).property("checked") is False)
prefs.store["EditOnDoubleClick"] = True
prefs.changed.emit()
settle()
check("it follows the store, not the last click",
      switch_of(window).property("checked") is True)

repair = "Auto repair 'Wire not closed' errors"
check("auto repair has a switch", switch_of(window, repair) is not None)
click(window, switch_of(window, repair))
check("which writes its setting",
      prefs.writes[-1] == ("RepairProfiles", True))

lines = "Show tree lines"
check("another switch shows its own stored value",
      switch_of(window, lines).property("checked") is False)
click(window, switch_of(window, lines))
check("and writes its own key",
      prefs.writes[-1] == ("TreeLines", True))
for moved in ("Mark under-constrained sketches", "Show tooltips on rows",
              "Show objects picked in the 3D view"):
    check("%r is on the Preferences page only" % moved,
          not any(i.property("text") == moved
                  for i in items_of(window.contentItem())))

print("keyboard")
click(window, text_item(window, "Roomy"))    # focus the density row
QTest.keyClick(window, QtCore.Qt.Key.Key_Left)
settle(0.05)
check("Left moves the focused segment",
      prefs.writes[-1] == ("RowDensity", "normal"))

print("link and closing")
click(window, text_item(window, "More preferences…"))
check("the link asks for the page and closes",
      prefs.opened == 1 and not popup_windows())
open_popup()
QTest.keyClick(popup_windows()[0], QtCore.Qt.Key.Key_Escape)
settle()
check("Escape closes it", not popup_windows())

print("theme")
check("theme exposes the chip mode", theme.property("chipMode") == "problems")
check("and the under-constrained switch",
      theme.property("showUnderConstrained") is True)

print("PROBLEMS: %d" % len(problems))
for problem in problems:
    print("  *", problem)
print("TREE SETTINGS QML PASSED" if not problems
      else "TREE SETTINGS QML FAILED")
sys.exit(1 if problems else 0)
