"""The isolate mode: what it shows and hides, and that it puts it back.

Run with: python3 tests/test_isolate.py
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
sys.path.insert(0, str(ROOT / "tests"))

import test_inspector  # noqa: E402,F401  (installs the FreeCAD stub)

App = sys.modules["FreeCAD"]
Gui = sys.modules.setdefault("FreeCADGui", types.ModuleType("FreeCADGui"))

from freecad.nxt import isolate  # noqa: E402


class Obj:
    def __init__(self, name: str, shown: bool = True,
                 group: list[Obj] | None = None) -> None:
        self.Name = self.Label = name
        self.ViewObject = types.SimpleNamespace(Visibility=shown)
        self.Group = group or []
        self.InList: list[Obj] = []
        for child in self.Group:
            child.InList.append(self)


class Doc:
    def __init__(self, *objects: Obj) -> None:
        self.Name = "Doc"
        self.Objects = list(objects)

    def getObject(self, name: str) -> Any:  # noqa: N802
        return next((o for o in self.Objects if o.Name == name), None)


def model() -> Doc:
    """Body(Sketch, Pad[hidden], Pocket=tip), Box, Part(Cyl)."""
    sketch = Obj("Sketch", shown=False)
    pad = Obj("Pad", shown=False)
    pocket = Obj("Pocket")
    body = Obj("Body", group=[sketch, pad, pocket])
    box = Obj("Box")
    cyl = Obj("Cyl")
    part = Obj("Part", group=[cyl])
    return Doc(body, sketch, pad, pocket, box, part, cyl)


def shown(doc: Doc) -> set[str]:
    return {o.Name for o in doc.Objects if o.ViewObject.Visibility}


class PlanTests(unittest.TestCase):

    def test_a_container_keeps_its_contents_as_they_were(self) -> None:
        doc = model()
        kept, changes = isolate.plan(doc.Objects, [doc.getObject("Body")])
        self.assertEqual(kept, {"Body", "Sketch", "Pad", "Pocket"})
        self.assertEqual(changes, {"Box": False, "Part": False,
                                   "Cyl": False})

    def test_a_feature_is_shown_with_its_body_and_the_tip_hidden(self) -> None:
        doc = model()
        kept, changes = isolate.plan(doc.Objects, [doc.getObject("Pad")])
        self.assertEqual(kept, {"Pad", "Body"})
        self.assertEqual(changes, {"Pad": True, "Pocket": False,
                                   "Box": False, "Part": False,
                                   "Cyl": False})


class ModeTests(unittest.TestCase):

    def setUp(self) -> None:
        self.doc = model()
        App.ActiveDocument = self.doc
        App.getDocument = lambda _name: self.doc
        self.gui_doc = types.SimpleNamespace(Modified=False)
        Gui.getDocument = lambda _name: self.gui_doc  # type: ignore
        self.mode = isolate.Isolation()
        self.before = shown(self.doc)

    def test_enter_and_exit_put_everything_back(self) -> None:
        heard: list[bool] = []
        self.mode.changed.connect(lambda: heard.append(self.mode.active()))
        self.assertTrue(self.mode.isolate(["Pad"]))
        self.assertEqual(shown(self.doc), {"Body", "Pad"})
        self.assertEqual(self.mode.text(), "Isolated: Pad")
        self.assertTrue(self.mode.keptNames["Pad"])
        self.assertTrue(self.mode.exit())
        self.assertEqual(shown(self.doc), self.before)
        self.assertEqual(heard, [True, False])
        self.assertFalse(self.mode.exit())

    def test_it_does_not_leave_the_document_modified(self) -> None:
        self.gui_doc.Modified = True        # as setting Visibility would
        self.mode._was_modified = None
        self.mode.isolate(["Box"])
        self.mode.exit()
        # Modified going in: left alone. Clean going in: cleaned.
        self.assertTrue(self.gui_doc.Modified)
        self.gui_doc.Modified = False
        self.mode.isolate(["Box"])
        self.gui_doc.Modified = True
        self.mode.exit()
        self.assertFalse(self.gui_doc.Modified)

    def test_a_save_keeps_the_users_view(self) -> None:
        self.mode.isolate(["Box"])
        self.mode.saving("Doc")
        self.assertEqual(shown(self.doc), self.before)
        self.mode.saved("Doc")
        self.assertEqual(shown(self.doc), {"Box"})
        self.mode.exit()

    def test_other_documents_and_deletions_end_it(self) -> None:
        self.mode.isolate(["Box"])
        self.mode.document_activated("Other")
        self.assertFalse(self.mode.active())
        self.assertEqual(shown(self.doc), self.before)
        self.mode.isolate(["Box"])
        self.mode.object_deleted("Doc", "Box")
        self.assertFalse(self.mode.active())

    def test_toggle(self) -> None:
        self.mode.toggle(["Box"])
        self.assertTrue(self.mode.active())
        self.mode.toggle(["Box"])
        self.assertFalse(self.mode.active())

    def test_nothing_to_isolate(self) -> None:
        self.assertFalse(self.mode.isolate(["Missing"]))
        self.assertFalse(self.mode.active())


class EscapeTests(unittest.TestCase):
    """Escape leaves the mode unless it means something else."""

    def setUp(self) -> None:
        from PySide6 import QtCore, QtGui, QtWidgets

        from freecad.nxt import isolate_notice
        self.QtCore, self.QtGui = QtCore, QtGui
        self.app = (QtWidgets.QApplication.instance()
                    or QtWidgets.QApplication([]))
        self.dialog: Any = None
        Gui.Control = types.SimpleNamespace(  # type: ignore[attr-defined]
            activeDialog=lambda: self.dialog)
        Gui.ActiveDocument = types.SimpleNamespace(  # type: ignore
            getInEdit=lambda: None)
        self.mode = types.SimpleNamespace(on=True)
        self.mode.active = lambda: self.mode.on
        self.exits = 0

        def leave() -> bool:
            self.exits += 1
            self.mode.on = False
            return True
        self.mode.exit = leave
        self.filter = isolate_notice.EscapeToExit(self.mode)
        self.target = QtWidgets.QWidget()

    def press(self, key: Any = None) -> bool:
        qt = self.QtCore.Qt
        key = key or qt.Key.Key_Escape
        event = self.QtGui.QKeyEvent(self.QtCore.QEvent.Type.KeyPress, key,
                                     qt.KeyboardModifier.NoModifier)
        return self.filter.eventFilter(self.target, event)

    def test_escape_leaves(self) -> None:
        self.assertTrue(self.press())
        self.assertEqual(self.exits, 1)
        self.assertFalse(self.press())      # off now: Escape passes on

    def test_other_keys_pass(self) -> None:
        self.assertFalse(self.press(self.QtCore.Qt.Key.Key_A))
        self.assertEqual(self.exits, 0)

    def test_a_task_panel_keeps_its_escape(self) -> None:
        self.dialog = object()
        self.assertFalse(self.press())
        self.assertEqual(self.exits, 0)

    def test_an_edit_keeps_its_escape(self) -> None:
        Gui.ActiveDocument = types.SimpleNamespace(  # type: ignore
            getInEdit=lambda: object())
        self.assertFalse(self.press())
        self.assertEqual(self.exits, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
