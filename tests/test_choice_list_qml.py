"""ChoiceList, opened offscreen from a field near a scrolling panel's foot.

The list is a window of its own, so it may reach past the panel, keeps
to the room its view gives it, and takes the wheel itself. Needs PySide6
6.8 or later (Popup.Window).

Run with: python3 tests/test_choice_list_qml.py
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
import shiboken6  # noqa: E402
from PySide6 import QtCore, QtGui, QtQuick  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

App, Gui = fakes.install()

from freecad.nxt.ui.theme import Theme  # noqa: E402

QML = ROOT / "freecad" / "nxt" / "resources" / "qml"
OPTIONS = 40
VIEW_HEIGHT = 160
HOST = """
import QtQuick
import Nxt.Controls
Rectangle {
    width: 240; height: %d
    property alias panelY: panel.contentY
    property var list: null
    property string picked: ""
    Component { id: choices; ChoiceList {} }
    function openList(count) {
        var options = [];
        for (var i = 0; i < count; ++i)
            options.push("Option " + i);
        list = choices.createObject(contentItem(), {
            options: options, current: "Option 0",
            below: field.mapToItem(contentItem(), 0, field.height),
            anchorHeight: field.height, minWidth: field.width});
        list.chosen.connect(function (value) { picked = value; });
    }
    function contentItem() { return Window.contentItem; }
    Flickable {
        id: panel
        anchors.fill: parent
        contentHeight: 1000
        Rectangle { id: field; x: 10; y: 130; width: 120; height: 20 }
    }
}
""" % VIEW_HEIGHT
problems: list[str] = []
app = QtGui.QGuiApplication(sys.argv)
theme = Theme()


class Expressions(QtCore.QObject):
    """The placement a view with no `host` gives (the Property Inspector)."""

    def __init__(self) -> None:
        super().__init__()
        self.room = QtCore.QRectF()

    @QtCore.Slot(QtCore.QObject, result=QtCore.QPointF)
    def anchorOffset(self, _item: QtCore.QObject) -> QtCore.QPointF:  # noqa: N802
        return QtCore.QPointF(0, 0)

    @QtCore.Slot(QtCore.QObject, result=QtCore.QRectF)
    def popupRoom(self, _item: QtCore.QObject) -> QtCore.QRectF:  # noqa: N802
        return self.room


def settle(ms: int = 100) -> None:
    end = QtCore.QTime.currentTime().addMSecs(ms)
    while QtCore.QTime.currentTime() < end:
        app.processEvents()


def popups() -> list[Any]:
    return [w for w in app.topLevelWindows()
            if w is not view and w.isVisible()]


def check(name: str, ok: bool) -> None:
    print("  %-52s %s" % (name, "ok" if ok else "FAIL"))
    if not ok:
        problems.append(name)


def wheel_down(window: Any) -> None:
    centre = QtCore.QPointF(window.width() / 2, window.height() / 2)
    event = QtGui.QWheelEvent(
        centre, QtCore.QPointF(window.mapToGlobal(centre.toPoint())),
        QtCore.QPoint(0, 0), QtCore.QPoint(0, -120),
        QtCore.Qt.MouseButton.NoButton, QtCore.Qt.KeyboardModifier.NoModifier,
        QtCore.Qt.ScrollPhase.NoScrollPhase, False)
    QtGui.QGuiApplication.sendEvent(window, event)
    settle()


def items_in(window: Any) -> list[Any]:
    out, stack = [], [window.contentItem()]
    while stack:
        item = stack.pop()
        out.append(item)
        stack.extend(item.childItems())
    return out


def option(window: Any, text: str) -> Any:
    return next((i for i in items_in(window)
                 if i.property("text") == text and i.property("visible")),
                None)


expressions = Expressions()
view = QtQuick.QQuickView()
view.engine().addImportPath(str(QML))
view.rootContext().setContextProperty("theme", theme)
view.rootContext().setContextProperty("expressions", expressions)
host = ROOT / "tests" / "_choice_list_host.qml"
host.write_text(HOST, encoding="utf-8")
view.setSource(QtCore.QUrl.fromLocalFile(str(host)))
host.unlink()
problems += [e.toString() for e in view.errors()]
view.show()
root = view.rootObject()
settle()

print("ChoiceList: a long list near the panel's foot")
root.openList(OPTIONS)
settle()
shown = popups()
check("opens in a window of its own", len(shown) == 1)
window = shown[0] if shown else None
check("reaches past the panel it was opened from",
      window is not None and window.height() > VIEW_HEIGHT)
rows = next((i for i in items_in(window)
             if i.metaObject().className().startswith("QQuickListView")),
            None) if window is not None else None
if window is not None:
    wheel_down(window)
check("the wheel scrolls the list",
      rows is not None and rows.property("contentY") > 0)
check("and not the panel behind it", root.property("panelY") == 0)
pick = option(window, "Option 6") if window is not None else None
if pick is not None:
    centre = pick.mapToScene(QtCore.QPointF(pick.property("width") / 2,
                                            pick.property("height") / 2))
    QTest.mouseClick(window, QtCore.Qt.MouseButton.LeftButton,
                     QtCore.Qt.KeyboardModifier.NoModifier, centre.toPoint())
    settle()
check("a click chooses", root.property("picked") == "Option 6")
check("and closes the list", not popups())

print("ChoiceList: kept to the room its view gives")
expressions.room = QtCore.QRectF(0, 0, 240, VIEW_HEIGHT)
root.openList(OPTIONS)
settle()
shown = popups()
check("no taller than the room",
      len(shown) == 1 and shown[0].height() <= VIEW_HEIGHT)
QTest.keyClick(shown[0] if shown else view, QtCore.Qt.Key.Key_Escape)
settle()
check("Escape closes it", not popups())

root = None
view.close()
shiboken6.delete(view)
app.processEvents()

print("CHOICE LIST QML PASSED" if not problems else "CHOICE LIST QML FAILED")
for p in problems:
    print("  *", p)
sys.exit(1 if problems else 0)
