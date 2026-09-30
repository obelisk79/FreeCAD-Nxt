"""The context menu, opened offscreen as the panel opens it.

The menu is resolved from Nxt's own `default.toml` for a stand-in Pocket
that failed, presented with a stand-in for FreeCAD's command table, and
opened from a deliberately narrow stand-in panel. Checks that it opens in
a window of its own, wider than the panel; that Escape and a click
elsewhere close it without running anything; that its rows, its bar and
its More submenu run what they show; and that the keyboard walks it.
Needs PySide6 6.8 or later (Popup.Window).

Run with: python3 tests/test_context_menu_qml.py
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

from freecad.nxt.menus import definitions, present  # noqa: E402
from freecad.nxt.tree.theme import Theme  # noqa: E402

QML = ROOT / "freecad" / "nxt" / "resources" / "qml"
DEFAULT = ROOT / "freecad" / "nxt" / "resources" / "menus" / "default.toml"
BAD = ("binding loop", "is not defined", "cannot read property",
       "unable to assign", "typeerror", "referenceerror", "cannot assign",
       "is not a function", "required property", "cannot override")
problems: list[str] = []


def _handler(_mode: Any, _context: Any, message: str) -> None:
    if any(token in str(message).lower() for token in BAD):
        problems.append(str(message))
        print(message)


QtCore.qInstallMessageHandler(_handler)


def lookup(name: str) -> present.CommandInfo | None:
    """FreeCAD's command table, as far as this menu needs it."""
    if name.startswith("Draft_"):
        return None                         # Draft is not loaded
    return present.CommandInfo(label=name.split("_", 1)[1],
                               shortcut="Del" if name == "Std_Delete" else "",
                               active=name != "Std_Paste", icon=name)


POCKET = definitions.ObjectFacts(
    types=("PartDesign::Pocket", "PartDesign::Feature", "Part::Feature"),
    in_body=True,
    flags=frozenset({"failed", "has_shape", "shown_in_3d", "has_inputs"}))
MENU = present.present(
    definitions.resolve(definitions.load(DEFAULT), [POCKET]),
    present.Subject(title="Pocket", subtitle="Pocket"), lookup)

HOST = """
import QtQuick
import Nxt
Rectangle {
    id: host
    width: 120; height: 200
    property var ran: []
    Component { id: menuComponent; ContextMenu {} }
    function open(data) {
        var menu = menuComponent.createObject(host);
        menu.load(data);
        menu.chosen.connect(function (command) {
            host.ran = host.ran.concat([command]);
        });
        menu.popup(20, 20);
        return menu;
    }
}
"""

app = QtGui.QGuiApplication(sys.argv)
theme = Theme()


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
host_file = ROOT / "tests" / "_menu_host.qml"
host_file.write_text(HOST, encoding="utf-8")
view.setSource(QtCore.QUrl.fromLocalFile(str(host_file)))
host_file.unlink()
for error in view.errors():
    problems.append(error.toString())
view.setPosition(100, 100)
view.show()
settle()
root = view.rootObject()


def ran() -> list[str]:
    return [str(c) for c in root.property("ran").toVariant()] \
        if hasattr(root.property("ran"), "toVariant") \
        else [str(c) for c in root.property("ran")]


def open_menu() -> Any:
    menu = QtCore.QMetaObject.invokeMethod(
        root, "open", QtCore.Qt.ConnectionType.DirectConnection,
        QtCore.Q_RETURN_ARG("QVariant"), QtCore.Q_ARG("QVariant", MENU))
    settle()
    return menu


def popup_windows() -> list[QtGui.QWindow]:
    settle(0.05)
    return [w for w in app.topLevelWindows()
            if w is not view and w.isVisible()]


def items_of(item: Any, class_prefix: str) -> list[Any]:
    out, stack = [], [item]
    while stack:
        current = stack.pop()
        if current.metaObject().className().startswith(class_prefix):
            out.append(current)
        stack.extend(current.childItems())
    return out


def window_texts(window: QtGui.QWindow) -> list[str]:
    """Visible text in a window, top to bottom: reading order."""
    shown = [i for i in items_of(window.contentItem(), "QQuickText")
             if i.property("visible") and i.property("text")]

    def place(item: Any) -> tuple[float, float]:
        point = item.mapToScene(QtCore.QPointF(0, 0))
        return (round(point.y()), point.x())

    return [i.property("text") for i in sorted(shown, key=place)]


def text_in(window: QtGui.QWindow, text: str) -> Any:
    return next(i for i in items_of(window.contentItem(), "QQuickText")
                if i.property("text") == text and i.property("visible"))


def point_of(item: Any) -> QtCore.QPoint:
    return item.mapToScene(QtCore.QPointF(item.property("width") / 2,
                                          item.property("height") / 2)
                           ).toPoint()


def hover(window: QtGui.QWindow, text: str) -> None:
    point = point_of(text_in(window, text))
    # Two moves: hover is a change of position, and the first move only
    # tells the window where the pointer is.
    QTest.mouseMove(window, point - QtCore.QPoint(3, 0))
    settle(0.05)
    QTest.mouseMove(window, point)
    settle(0.6)


def click(window: QtGui.QWindow, text: str) -> None:
    point = point_of(text_in(window, text))
    QTest.mouseMove(window, point)
    settle(0.05)
    QTest.mouseClick(window, QtCore.Qt.MouseButton.LeftButton,
                     QtCore.Qt.KeyboardModifier.NoModifier, point)
    settle()


def key(window: QtGui.QWindow, name: str) -> None:
    QTest.keyClick(window, getattr(QtCore.Qt.Key, "Key_" + name))
    settle(0.08)


print("a failed Pocket")
menu = open_menu()
windows = popup_windows()
check("it opens in a window of its own", len(windows) == 1)
window = windows[0] if windows else view
check("wider than the panel it opened from",
      window.width() > view.width())
corner = window.position() - view.position()
check("placed where it was asked, relative to the panel",
      abs(corner.x() - 20) <= 8 and abs(corner.y() - 20) <= 8)
shown = window_texts(window)
check("the header names the object", "Pocket" in shown)
check("four bar buttons with short labels, no Hide",
      all(t in shown for t in ("Isolate", "Fit", "Appearance", "Inspect"))
      and "Hide" not in shown)
check("the lead action is bold",
      text_in(window, "Edit Pocket").property("font").bold())
check("the failure leads the state rows",
      shown.index("Why did it fail?") < shown.index("Model"))
check("sections are labelled, in order",
      [t for t in shown if t in ("Model", "Organize", "Relations",
                                 "Inspect")][-4:]
      == ["Model", "Organize", "Relations", "Inspect"])

print("closing")
key(window, "Escape")
check("Escape closes it", not popup_windows())
open_menu()
QTest.mouseClick(view, QtCore.Qt.MouseButton.LeftButton,
                 QtCore.Qt.KeyboardModifier.NoModifier, QtCore.QPoint(5, 190))
settle()
check("a click elsewhere closes it", not popup_windows())
check("and runs nothing", ran() == [])

print("mouse")
open_menu()
window = popup_windows()[0]
click(window, "Why did it fail?")
check("a row runs its command and closes the menu",
      ran() == ["nxt:reveal_failure"] and not popup_windows())
open_menu()
click(popup_windows()[0], "Fit")
check("a bar button runs its command and closes the menu",
      ran()[-1] == "Std_ViewFitSelection" and not popup_windows())

open_menu()
window = popup_windows()[0]
hover(window, "More")
windows = popup_windows()
check("hovering More opens it as a submenu", len(windows) == 2)
more = next((w for w in windows if w is not window), None)
shown = window_texts(more) if more is not None else []
check("grouped", "Clipboard" in shown and "Display" in shown)
check("Draft's commands are absent when Draft is not loaded",
      "Draft" not in shown)
check("FreeCAD's own menu is the last entry",
      bool(shown) and shown[-1] == "FreeCAD's menu…")
if more is not None:
    before = len(ran())
    click(more, "Paste")
    check("a command FreeCAD says cannot run does nothing",
          len(ran()) == before)
    click(more, "Copy")
    check("a More entry runs and closes both",
          ran()[-1] == "Std_Copy" and not popup_windows())

print("keyboard")
open_menu()
window = popup_windows()[0]
key(window, "Down")
key(window, "Down")
key(window, "Down")
key(window, "Return")
check("Down past the bar and the lead runs the state row",
      ran()[-1] == "nxt:reveal_failure")
open_menu()
window = popup_windows()[0]
key(window, "Down")
key(window, "Return")
check("Down stops on the bar; Enter runs its first button",
      ran()[-1] == "nxt:isolate")
open_menu()
window = popup_windows()[0]
key(window, "Down")
key(window, "Right")
key(window, "Return")
check("Right moves along the bar", ran()[-1] == "Std_ViewFitSelection")

print("expressions")
open_menu()
window = popup_windows()[0]
hover(window, "Expressions")
windows = popup_windows()
check("Expressions opens as a submenu", len(windows) == 2)
sub = next((w for w in windows if w is not window), None)
if sub is not None:
    check("with Nxt's four actions",
          window_texts(sub) == ["Copy selected", "Copy active document",
                                "Copy all documents", "Paste"])
    click(sub, "Paste")
    check("which run", ran()[-1] == "nxt:expressions_paste")

print("PROBLEMS: %d" % len(problems))
for problem in problems:
    print("  *", problem)
print("CONTEXT MENU QML PASSED" if not problems
      else "CONTEXT MENU QML FAILED")
sys.exit(1 if problems else 0)
