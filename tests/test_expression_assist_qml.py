"""Expression help in a field (ExpressionAssist.qml), driven for real.

A TextField with an owner, and an `expressions` that knows a small fake
document: typing "=" opens the list and the result, the arrows and Tab
pick and put a suggestion in, and a field with no owner stays plain.

Run with: python3 tests/test_expression_assist_qml.py   (needs PySide6)
"""

from __future__ import annotations

import os
import sys
import types
import unittest
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6 import QtCore, QtGui, QtQml, QtQuick, QtWidgets  # noqa: E402,F401
from PySide6.QtTest import QTest  # noqa: E402

App = types.ModuleType("FreeCAD")
App.Console = types.SimpleNamespace(PrintError=lambda _m: None,
                                    PrintWarning=lambda _m: None,
                                    PrintLog=lambda _m: None)
App.ParamGet = lambda _g: types.SimpleNamespace(
    GetBool=lambda _k, d: d, GetInt=lambda _k, d: d,
    GetFloat=lambda _k, d: d, GetString=lambda _k, d: d,
    GetUnsigned=lambda _k, d: d)
sys.modules.setdefault("FreeCAD", App)
sys.modules.setdefault("FreeCADGui", types.ModuleType("FreeCADGui"))

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

from freecad.nxt import expressions as ex  # noqa: E402
from freecad.nxt.tree.theme import Theme  # noqa: E402

QML = ROOT / "freecad" / "nxt" / "resources" / "qml"
#: Every view made, kept to the end of the run: torn down mid-run, the
#: fields' bindings would read a `theme` that had already gone.
KEEP: list[Any] = []
PROPS = {"Pad": ["Length", "Length2"], "Params": ["Thickness"]}


class FakeExpressions(ex.Expressions):
    """Expressions over a document of a Pad and a VarSet."""

    @QtCore.Slot(str, str, int, result="QVariantList")
    def suggest(self, owner: str, text: str,  # noqa: N802
                cursor: int) -> list[dict[str, str]]:
        token = ex.token_at(text, cursor)
        return [s.as_dict() for s in ex.suggest(
            token, [("Pad", "Pad"), ("VarSet", "Params")], ["Length"],
            PROPS.get)]

    @QtCore.Slot(str, str, result="QVariantMap")
    def evaluate(self, owner: str, text: str) -> dict[str, Any]:  # noqa: N802
        expression = ex.strip_marker(text)
        if expression == "Params.Thickness * 2":
            return {"ok": True, "text": "6.00 mm"}
        return {"ok": False, "text": "Unknown name" if expression else ""}


def settle(ms: int = 60) -> None:
    deadline = QtCore.QDeadlineTimer(ms)
    while not deadline.hasExpired():
        APP.processEvents()


PROBLEMS: list[str] = []


class AssistTests(unittest.TestCase):
    """One window for every test: focus goes to the active window only."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.view = QtQuick.QQuickView()
        cls.view.engine().addImportPath(str(QML))
        cls.view.engine().warnings.connect(
            lambda ws: PROBLEMS.extend(w.toString() for w in ws))
        context = cls.view.rootContext()
        cls.theme = Theme()
        context.setContextProperty("theme", cls.theme)
        cls.helper = FakeExpressions()
        context.setContextProperty("expressions", cls.helper)
        cls.component = QtQml.QQmlComponent(cls.view.engine())
        cls.component.setData(b"""
import QtQuick
import Nxt
Item {
    width: 300; height: 200
    TextField { objectName: "f"; x: 10; y: 10; width: 200
                owner: "Doc#Pad" }
    TextField { objectName: "g"; x: 10; y: 60; width: 200 }
}""", QtCore.QUrl("file:///assist.qml"))
        cls.root = cls.component.create(context)
        PROBLEMS.extend(e.toString() for e in cls.component.errors())
        cls.root.setParentItem(cls.view.contentItem())
        cls.view.resize(300, 200)
        cls.view.show()
        cls.view.requestActivate()
        settle(150)
        cls.field = cls.root.findChild(QtCore.QObject, "f")
        cls.input = cls.part(cls.field, "QQuickTextInput")
        cls.assist = cls.part(cls.field, "ExpressionAssist")
        KEEP.extend((cls.view, cls.root, cls.theme, cls.helper,
                     cls.component))

    def setUp(self) -> None:
        self.view.requestActivate()
        self.input.setProperty("text", "")
        settle()

    def tearDown(self) -> None:
        self.assertEqual(PROBLEMS, [])

    @staticmethod
    def part(item: Any, kind: str) -> Any:
        return next(c for c in item.childItems()
                    if c.metaObject().className().startswith(kind))

    def on(self, item: Any, signal: str, slot: Any) -> None:
        """Connect to a signal declared in QML."""
        QtCore.QObject.connect(item, QtCore.SIGNAL(signal + "()"), slot)

    def key(self, key: Any) -> None:
        QTest.keyClick(self.view, key)
        settle()

    def type(self, text: str, into: Any = None) -> None:
        target = into or self.input
        target.forceActiveFocus()
        settle()
        target.setProperty("text", text)
        target.setProperty("cursorPosition", len(text))
        settle()
        self.assertTrue(target.property("activeFocus"))

    def suggestions(self) -> list[str]:
        found = self.assist.property("suggestions")
        if hasattr(found, "toVariant"):
            found = found.toVariant()
        return [s["label"] for s in found]

    def test_a_plain_value_has_no_help(self) -> None:
        self.type("12")
        self.assertFalse(self.assist.property("typing"))

    def test_an_expression_lists_what_fits(self) -> None:
        self.type("=Pa")
        self.assertTrue(self.assist.property("typing"))
        self.assertIn("Pad", self.suggestions())
        self.assertIn("Params", self.suggestions())

    def test_tab_puts_the_pick_in(self) -> None:
        self.type("=Para")
        self.key(QtCore.Qt.Key.Key_Tab)
        self.assertEqual(self.input.property("text"), "=<<Params>>.")
        self.assertEqual(self.suggestions(), ["Thickness"])

    def test_arrows_pick_and_return_puts_it_in(self) -> None:
        self.type("=Pad.Len")
        self.key(QtCore.Qt.Key.Key_Down)
        self.key(QtCore.Qt.Key.Key_Return)
        self.assertEqual(self.input.property("text"), "=Pad.Length2")

    def test_return_without_a_pick_is_the_fields(self) -> None:
        accepted: list[bool] = []
        self.on(self.field, "accepted", lambda: accepted.append(True))
        self.type("=Pad.Len")
        self.key(QtCore.Qt.Key.Key_Return)
        self.assertEqual(accepted, [True])
        self.assertEqual(self.input.property("text"), "=Pad.Len")

    def test_the_result_shows(self) -> None:
        self.type("=Params.Thickness * 2")
        result = self.assist.property("result")
        if hasattr(result, "toVariant"):
            result = result.toVariant()
        self.assertEqual(result, {"ok": True, "text": "6.00 mm"})

    def test_escape_hides_the_list_then_is_the_fields(self) -> None:
        dismissed: list[bool] = []
        self.on(self.field, "dismissed", lambda: dismissed.append(True))
        self.type("=Pa")
        self.key(QtCore.Qt.Key.Key_Escape)
        self.assertEqual(dismissed, [])
        self.key(QtCore.Qt.Key.Key_Escape)
        self.assertEqual(dismissed, [True])

    def test_no_owner_no_help(self) -> None:
        other = self.root.findChild(QtCore.QObject, "g")
        self.type("=Pa", into=self.part(other, "QQuickTextInput"))
        assist = self.part(other, "ExpressionAssist")
        self.assertFalse(assist.property("typing"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
