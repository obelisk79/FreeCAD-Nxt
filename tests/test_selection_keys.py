"""Selection keys and 3D picks, against a stand-in selection.

Space, the arrow keys and Shift+click; revealing objects picked in the
3D view; and the undo step an edit begun from Nxt runs in.

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

    def getSelectionEx(self, *_args: Any) -> list[Any]:
        return []

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
                                    PrintMessage=lambda _m: None,
                                    PrintLog=lambda _m: None)
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


class PickTests(unittest.TestCase):
    """Picking in the 3D view scrolls to the row and flashes it."""

    def setUp(self) -> None:
        SELECTION.names = []
        self.bridge = make_bridge()
        rows = self.bridge._tree
        rows.selected = frozenset()
        rows.revealed = []
        rows.selection = lambda: rows.selected
        rows.set_selection = lambda names: setattr(
            rows, "selected", frozenset(names))
        rows.reveal = rows.revealed.append
        self.bridge._snapshot.nodes = dict.fromkeys("ABCDE")
        self.bridge._picked = []
        self.bridge._origins = []
        self.bridge._reveal_timer = types.SimpleNamespace(start=lambda: None)
        self.bridge._arrows_timer = types.SimpleNamespace(start=lambda: None)
        self.bridge.sync_selection = types.MethodType(
            bridge_mod.TreeBridge.sync_selection, self.bridge)
        self.scrolled: list[int] = []
        self.flashed: list[list[str]] = []
        self.bridge.revealTreeRow.connect(self.scrolled.append)
        self.bridge.flashRows.connect(self.flashed.append)

    def pick(self, *names: str) -> None:
        for name in names:
            SELECTION.addSelection("Doc", name)
            self.bridge.sync_selection(picked=True)
        self.bridge._reveal_picked()

    def test_a_pick_opens_its_path_scrolls_and_flashes(self) -> None:
        self.pick("D")
        self.assertEqual(self.bridge._tree.revealed, ["D"])
        self.assertEqual(self.scrolled, [3])
        self.assertEqual(self.flashed, [["D"]])

    def test_a_box_selection_scrolls_to_the_first_row(self) -> None:
        self.pick("E", "B", "D")
        self.assertEqual(self.scrolled, [1])
        self.assertEqual(self.flashed, [["E", "B", "D"]])

    def test_only_what_was_added_is_revealed(self) -> None:
        self.pick("B")
        self.pick("D")
        self.assertEqual(self.flashed[-1], ["D"])

    def test_the_panels_own_selection_does_not_scroll(self) -> None:
        self.bridge.select("C")
        self.bridge._reveal_picked()
        self.assertEqual(self.scrolled, [])

    def test_the_maker_is_marked_until_the_selection_changes(self) -> None:
        original = bridge_mod.picking.target
        bridge_mod.App.getDocument = lambda _name: DOC
        bridge_mod.picking.target = lambda _doc, _top, _sub: "B"
        try:
            SELECTION.addSelection("Doc", "E")
            self.bridge.sync_selection()
            self.bridge.picked("Doc", "E", "Face1")
            self.bridge._reveal_picked()
        finally:
            bridge_mod.picking.target = original
        self.assertEqual(self.bridge.pickOrigins, ["B"])
        SELECTION.clearSelection()
        self.bridge.sync_selection()
        self.assertEqual(self.bridge.pickOrigins, [])

    def test_the_selected_object_is_not_marked_as_well(self) -> None:
        SELECTION.addSelection("Doc", "D")
        self.bridge.sync_selection(picked=True)
        self.bridge._reveal_picked()
        self.assertEqual(self.bridge.pickOrigins, [])
        self.assertEqual(self.flashed, [["D"]])

    def test_it_can_be_turned_off(self) -> None:
        original = bridge_mod.settings.get
        bridge_mod.settings.get = lambda key: (
            False if key == "FollowSelection" else original(key))
        try:
            self.pick("D")
        finally:
            bridge_mod.settings.get = original
        self.assertEqual(self.scrolled, [])


class EditTransactionTests(unittest.TestCase):
    """An edit begun from Nxt runs in an undo step Cancel can abort."""

    def setUp(self) -> None:
        self.log: list[Any] = []
        self.active: str | None = None
        self.editing: Any = None
        App.getActiveTransaction = lambda: self.active
        App.setActiveTransaction = self.open
        App.closeActiveTransaction = lambda abort=False: self.log.append(
            ("close", abort))
        pad = types.SimpleNamespace(Name="Pad", Label="Pad")
        gui_doc = types.SimpleNamespace(
            Document=types.SimpleNamespace(getObject=lambda n: pad),
            getInEdit=lambda: self.editing,
            resetEdit=lambda: None,
            setEdit=self.set_edit)
        Gui.getDocument = lambda _name: gui_doc
        self.bridge = make_bridge()
        self.can_edit = True

    def open(self, name: str, persist: bool = False) -> None:
        self.active = name
        self.log.append(("open", name, persist))

    def set_edit(self, obj: Any) -> None:
        self.log.append(("edit", obj.Name))
        if self.can_edit:
            self.editing = obj

    def test_the_edit_opens_its_own_undo_step_first(self) -> None:
        self.bridge._enter_edit("Doc", "Pad")
        self.assertEqual(self.log, [("open", "Edit Pad", True),
                                    ("edit", "Pad")])

    def test_an_open_step_is_left_to_whoever_opened_it(self) -> None:
        self.active = "Something else"
        self.bridge._enter_edit("Doc", "Pad")
        self.assertEqual(self.log, [("edit", "Pad")])

    def test_no_edit_no_step(self) -> None:
        self.can_edit = False
        self.bridge._enter_edit("Doc", "Pad")
        self.assertEqual(self.log[-1], ("close", True))


class RootDropTests(unittest.TestCase):
    """Dropping a row on the document's name: out of its container."""

    def setUp(self) -> None:
        self.bridge = make_bridge()
        self.bridge._recompute_timer = types.SimpleNamespace(
            start=lambda: None)
        self.dragged: list[str] = []
        self.allow = True
        group = DOC.objects["A"]
        member = DOC.objects["B"]
        group.Group = [member]
        group.ViewObject.canDragObject = lambda _o: self.allow
        group.ViewObject.dragObject = lambda o: self.dragged.append(o.Name)
        member.InList = [group]
        DOC.objects["C"].InList = []
        DOC.log = []

    def tearDown(self) -> None:
        del DOC.objects["A"].Group
        for name in "BC":
            del DOC.objects[name].InList

    def test_a_member_leaves_its_container_in_one_step(self) -> None:
        self.assertTrue(self.bridge.canDropOnRoot(["B"]))
        self.assertTrue(self.bridge.dropOnRoot(["B"]))
        self.assertEqual(self.dragged, ["B"])
        self.assertEqual(DOC.log, ["open Move to top level", "commit"])

    def test_already_at_the_top(self) -> None:
        self.assertFalse(self.bridge.canDropOnRoot(["C"]))

    def test_a_container_that_refuses_keeps_it(self) -> None:
        self.allow = False
        self.assertFalse(self.bridge.canDropOnRoot(["B"]))
        self.assertFalse(self.bridge.dropOnRoot(["B"]))
        self.assertEqual(self.dragged, [])


class BodyDropTests(unittest.TestCase):
    """Out of a Body, whose view provider releases nothing."""

    def setUp(self) -> None:
        self.bridge = make_bridge()
        self.bridge._recompute_timer = types.SimpleNamespace(
            start=lambda: None)
        self.removed: list[str] = []
        body = types.SimpleNamespace(Name="Body", TypeId="PartDesign::Body")
        plane = types.SimpleNamespace(Name="XY_Plane")
        body.Origin = types.SimpleNamespace(Name="Origin",
                                            OriginFeatures=[plane])
        body.ViewObject = types.SimpleNamespace(
            canDragObject=lambda _o: False, dragObject=lambda _o: None)
        body.removeObject = lambda o: self.removed.append(o.Name)

        def member(name: str, solid: bool, needs: list[Any]) -> Any:
            obj = types.SimpleNamespace(
                Name=name, InList=[body], OutList=needs,
                OutListRecursive=needs,
                isDerivedFrom=lambda t: solid and t == "PartDesign::Feature")
            return obj
        pad = member("Pad", True, [])
        self.objects = {
            "VarSet": member("VarSet", False, []),
            "Attached": member("Attached", False, [plane]),
            "Free": member("Free", False, []),
            "Profile": member("Profile", False, []),
            "Pad": pad,
        }
        # Pad reads the VarSet through an expression and is built on Profile.
        self.objects["VarSet"].TypeId = "App::VarSet"
        self.objects["VarSet"].InList = [body, pad]
        self.objects["Profile"].InList = [body, pad]
        body.Group = list(self.objects.values())
        self.saved = DOC.objects
        DOC.objects = dict(self.saved, **self.objects)
        DOC.log = []

    def tearDown(self) -> None:
        DOC.objects = self.saved

    def test_a_varset_or_free_sketch_may_leave(self) -> None:
        self.assertTrue(self.bridge.canDropOnRoot(["VarSet", "Free"]))
        self.assertTrue(self.bridge.dropOnRoot(["VarSet"]))
        self.assertEqual(self.removed, ["VarSet"])

    def test_a_sketch_on_the_bodys_planes_stays(self) -> None:
        self.assertFalse(self.bridge.canDropOnRoot(["Attached"]))

    def test_a_sketch_a_feature_is_built_on_stays(self) -> None:
        self.assertFalse(self.bridge.canDropOnRoot(["Profile"]))

    def test_a_solid_feature_stays(self) -> None:
        self.assertFalse(self.bridge.canDropOnRoot(["Pad"]))
        self.assertFalse(self.bridge.dropOnRoot(["Pad"]))
        self.assertEqual(self.removed, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
