"""NxtToolTip, opened offscreen: shows after the delay, obeys the setting.

Run with: python3 tests/test_tooltip_qml.py
"""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import shiboken6  # noqa: E402
import test_inspector  # noqa: E402,F401  (installs the FreeCAD stub)
from PySide6 import QtCore, QtGui, QtQuick  # noqa: E402

STORE: dict[str, object] = {}
App = sys.modules["FreeCAD"]
App.ParamGet = lambda _group: types.SimpleNamespace(
    GetBool=lambda k, d: STORE.get(k, d), GetInt=lambda _k, d: d,
    GetFloat=lambda _k, d: d, GetString=lambda _k, d: d)

from freecad.nxt.tree.theme import Theme  # noqa: E402

QML = ROOT / "freecad" / "nxt" / "resources" / "qml"
HOST = """
import QtQuick
import Nxt
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


view = QtQuick.QQuickView()
view.engine().addImportPath(str(QML))
view.rootContext().setContextProperty("theme", theme)
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
