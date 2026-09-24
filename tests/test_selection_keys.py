"""Space, the arrow keys and Shift+click, against a stand-in selection.

Run with: python3 tests/test_selection_keys.py   (needs PySide6)
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

from PySide6 import QtWidgets  # noqa: E402


class Selection:
    """FreeCADGui.Selection, kept in a list of names."""

    def __init__(self) -> None:
        self.names: list[str] = []

    def getSelection(self, *_doc: Any) -> list[Any]:
        return [DOC.getObject(n) for n in self.names]

    def clearSelection(self) -> None:
        self.names = []

    def addSelection(self, _doc: str, name: str) -> None:
        if name not in self.names:
            self.names.append(name)

    def removeSelection(self, _doc: str, name: str) -> None:
        self.names.remove(name)


class Obj:
    def __init__(self, name: str, visible: bool = True) -> None:
        self.Name = self.Label = name
        self.ViewObject = types.SimpleNamespace(Visibility=visible)


class Doc:
    Name = "Doc"

    def __init__(self) -> None:
        self.objects = {n: Obj(n) for n in "ABCDE"}
        self.log: list[str] = []

    def getObject(self, name: str) -> Obj:
        return self.objects[name]

    def openTransaction(self, name: str) -> None:
        self.log.append("open " + name)

    def commitTransaction(self) -> None:
        self.log.append("commit")

    def abortTransaction(self) -> None:
        self.log.append("abort")


DOC = Doc()
SELECTION = Selection()
App = types.ModuleType("FreeCAD")
App.Console = types.SimpleNamespace(PrintError=lambda _m: None,
                                    PrintMessage=lambda _m: None)
App.ActiveDocument = DOC
App.ParamGet = lambda _g: types.SimpleNamespace(
    GetBool=lambda _k, d: d, GetInt=lambda _k, d: d,
    GetFloat=lambda _k, d: d, GetString=lambda _k, d: d)
Gui = types.ModuleType("FreeCADGui")
Gui.Selection = SELECTION
sys.modules.update(FreeCAD=App, FreeCADGui=Gui)

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

from freecad.nxt.tree import bridge as bridge_mod  # noqa: E402


class Rows:
    """The tree model's row lookups, over five flat rows."""

    names = list("ABCDE")

    def row_of(self, name: str) -> int:
        return self.names.index(name) if name in self.names else -1

    def name_at(self, row: int) -> str | None:
        return self.names[row] if 0 <= row < len(self.names) else None

    def rowCount(self) -> int:
        return len(self.names)


def make_bridge() -> Any:
    bridge = bridge_mod.TreeBridge.__new__(bridge_mod.TreeBridge)
    bridge_mod.QtCore.QObject.__init__(bridge)
    bridge._tree = Rows()
    bridge._anchor = bridge._cursor = None
    bridge._snapshot = types.SimpleNamespace(doc_name="Doc")
    bridge._pushing_selection = False
    bridge.sync_selection = lambda: None
    bridge.invalidate = lambda *a, **k: None
    return bridge


class KeyTests(unittest.TestCase):

    def setUp(self) -> None:
        SELECTION.names = []
        for obj in DOC.objects.values():
            obj.ViewObject.Visibility = True
        DOC.log = []
        self.bridge = make_bridge()

    def test_shift_click_selects_the_range_from_the_anchor(self) -> None:
        self.bridge.select("B")
        self.bridge.selectRange("D")
        self.assertEqual(SELECTION.names, ["B", "C", "D"])
        self.bridge.selectRange("A")           # the anchor stays at B
        self.assertEqual(SELECTION.names, ["A", "B"])

    def test_down_and_up_move_the_selection(self) -> None:
        self.bridge.select("B")
        self.assertEqual(self.bridge.stepSelection(1, False), 2)
        self.assertEqual(SELECTION.names, ["C"])
        self.bridge.stepSelection(-1, False)
        self.assertEqual(SELECTION.names, ["B"])

    def test_the_ends_do_not_wrap(self) -> None:
        self.bridge.select("E")
        self.assertEqual(self.bridge.stepSelection(1, False), 4)
        self.assertEqual(SELECTION.names, ["E"])

    def test_shift_arrow_extends(self) -> None:
        self.bridge.select("B")
        self.bridge.stepSelection(1, True)
        self.bridge.stepSelection(1, True)
        self.assertEqual(SELECTION.names, ["B", "C", "D"])

    def test_with_nothing_selected_down_starts_at_the_top(self) -> None:
        self.assertEqual(self.bridge.stepSelection(1, False), 0)
        self.assertEqual(SELECTION.names, ["A"])

    def test_space_hides_all_selected_as_one_step(self) -> None:
        DOC.objects["C"].ViewObject.Visibility = False
        SELECTION.names = ["B", "C"]
        self.bridge.toggleSelectedVisibility()
        self.assertEqual([DOC.objects[n].ViewObject.Visibility
                          for n in "BC"], [False, False])
        self.assertEqual(DOC.log, ["open Toggle visibility", "commit"])

    def test_space_shows_all_when_all_are_hidden(self) -> None:
        for name in "BC":
            DOC.objects[name].ViewObject.Visibility = False
        SELECTION.names = ["B", "C"]
        self.bridge.toggleSelectedVisibility()
        self.assertTrue(all(DOC.objects[n].ViewObject.Visibility
                            for n in "BC"))


class Branches:
    """A Body `A` holding `B` and `C`, then `D` and `E` at the top."""

    children = {"A": ["B", "C"]}

    def __init__(self) -> None:
        self.expanded: set[str] = set()

    def _rows(self) -> list[tuple[str, int]]:
        rows = [("A", 0)]
        if "A" in self.expanded:
            rows += [("B", 1), ("C", 1)]
        return rows + [("D", 0), ("E", 0)]

    def row_of(self, name: str) -> int:
        names = [n for n, _d in self._rows()]
        return names.index(name) if name in names else -1

    def name_at(self, row: int) -> str | None:
        rows = self._rows()
        return rows[row][0] if 0 <= row < len(rows) else None

    def depth_at(self, row: int) -> int:
        rows = self._rows()
        return rows[row][1] if 0 <= row < len(rows) else 0

    def rowCount(self) -> int:
        return len(self._rows())

    def is_expanded(self, name: str) -> bool:
        return name in self.expanded

    def set_expanded(self, name: str, expanded: bool) -> None:
        (self.expanded.add if expanded else self.expanded.discard)(name)


class BranchTests(unittest.TestCase):

    def setUp(self) -> None:
        SELECTION.names = []
        self.bridge = make_bridge()
        self.bridge._tree = Branches()
        self.bridge._snapshot.nodes = {
            n: types.SimpleNamespace(children=Branches.children.get(n, []))
            for n in "ABCDE"}
        self.bridge.select("A")

    def test_right_opens_then_enters(self) -> None:
        self.assertEqual(self.bridge.stepBranch(1), 0)
        self.assertTrue(self.bridge._tree.is_expanded("A"))
        self.assertEqual(self.bridge.stepBranch(1), 1)
        self.assertEqual(SELECTION.names, ["B"])

    def test_left_goes_to_the_parent_then_closes(self) -> None:
        self.bridge.stepBranch(1)
        self.bridge.stepBranch(1)
        self.assertEqual(self.bridge.stepBranch(-1), 0)
        self.assertEqual(SELECTION.names, ["A"])
        self.bridge.stepBranch(-1)
        self.assertFalse(self.bridge._tree.is_expanded("A"))

    def test_a_leaf_at_the_top_stays_put(self) -> None:
        self.bridge.select("D")
        self.assertEqual(self.bridge.stepBranch(1), -1)
        self.assertEqual(self.bridge.stepBranch(-1), -1)
        self.assertEqual(SELECTION.names, ["D"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
