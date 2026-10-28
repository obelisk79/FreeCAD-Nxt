"""NxtToolTip, opened offscreen: shows after the delay, obeys the setting.

Run with: python3 tests/test_tooltip_qml.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import fakes  # noqa: E402
import shiboken6  # noqa: E402
from PySide6 import QtCore, QtGui, QtQuick  # noqa: E402

STORE: dict[str, object] = {}
App, Gui = fakes.install(ParamGet=fakes.params(STORE))

from freecad.nxt.ui.theme import Theme  # noqa: E402

QML = ROOT / "freecad" / "nxt" / "resources" / "qml"
HOST = """
import QtQuick
import Nxt.Controls
import Nxt.Tree
import Nxt.Inspector
Rectangle {
    width: 120; height: 40
    property alias shown: tip.shown
    NxtToolTip { id: tip; delay: 100; text: "Pad" }
}
"""
problems: list[str] = []
app = QtGui.QGuiApplication(sys.argv)
theme = Theme()


def settle(ms: int) -> None:
    end = QtCore.QTime.currentTime().addMSecs(ms)
    while QtCore.QTime.currentTime() < end:
        app.processEvents()


def windows() -> int:
    return len([w for w in app.topLevelWindows()
                if w is not view and w.isVisible()])


def check(name: str, ok: bool) -> None:
    print("  %-48s %s" % (name, "ok" if ok else "FAIL"))
    if not ok:
        problems.append(name)


class Expressions(QtCore.QObject):
    """The offset a view with no `host` gives (the Property Inspector).

    Recorded, so the tooltip is seen asking for it.
    """

    def __init__(self) -> None:
        super().__init__()
        self.asked = 0

    @QtCore.Slot(QtCore.QObject, result=QtCore.QPointF)
    def anchorOffset(self, _item: QtCore.QObject) -> QtCore.QPointF:
        self.asked += 1
        return QtCore.QPointF(30, 40)


expressions = Expressions()
view = QtQuick.QQuickView()
view.engine().addImportPath(str(QML))
view.rootContext().setContextProperty("theme", theme)
view.rootContext().setContextProperty("expressions", expressions)
host = ROOT / "tests" / "_tooltip_host.qml"
host.write_text(HOST, encoding="utf-8")
view.setSource(QtCore.QUrl.fromLocalFile(str(host)))
host.unlink()
problems += [e.toString() for e in view.errors()]
view.show()
root = view.rootObject()
settle(50)

root.setProperty("shown", True)
settle(40)
check("nothing before the delay", windows() == 0)
settle(200)
check("a window of its own after it", windows() == 1)
check("with no host, the offset comes from its own view",
      expressions.asked == 1)
root.setProperty("shown", False)
settle(50)
check("gone when the pointer leaves", windows() == 0)

STORE["RowToolTips"] = False
theme.refresh()
root.setProperty("shown", True)
settle(250)
check("never, with the preference off", windows() == 0)

# The view before the theme: the other way round, the bindings re-read a
# theme that is already gone and say so on the way out.
root = None
view.close()
shiboken6.delete(view)
app.processEvents()

print("TOOLTIP QML PASSED" if not problems else "TOOLTIP QML FAILED")
for p in problems:
    print("  *", p)
sys.exit(1 if problems else 0)
