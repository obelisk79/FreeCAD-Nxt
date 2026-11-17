"""Opening things for editing from the tree: datums open their attachment.

Run with: python3 tests/test_editing.py
"""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fakes  # noqa: E402

App, Gui = fakes.install()

from freecad.nxt.tools import editing  # noqa: E402


class Obj:
    def __init__(self, name: str, *bases: str, attachable: bool = True):
        self.Name = name
        self._bases = bases
        if attachable:
            self.MapMode = "FlatFace"

    def isDerivedFrom(self, base: str) -> bool:  # noqa: N802
        return base in self._bases


class GuiDoc:
    def __init__(self, objects: dict[str, Any]) -> None:
        self.Document = types.SimpleNamespace(getObject=objects.get)
        self.reset = 0

    def getInEdit(self) -> Any:  # noqa: N802
        return None

    def resetEdit(self) -> None:  # noqa: N802
        self.reset += 1


class DatumTests(unittest.TestCase):

    def test_datums_are_recognised(self) -> None:
        for bases in (("Part::Datum",), ("App::DatumElement",)):
            self.assertTrue(editing.is_datum(Obj("D", *bases)))

    def test_origin_planes_and_other_objects_are_not(self) -> None:
        origin = Obj("XY", "App::DatumElement", "App::OriginFeature")
        self.assertFalse(editing.is_datum(origin))
        self.assertFalse(editing.is_datum(Obj("Pad", "PartDesign::Feature")))
        self.assertFalse(editing.is_datum(
            Obj("D", "Part::Datum", attachable=False)))
        self.assertFalse(editing.is_datum(None))


class AttachmentTests(unittest.TestCase):

    def setUp(self) -> None:
        self.plane = Obj("DatumPlane", "Part::Datum")
        Gui.getDocument = lambda _n: GuiDoc({"DatumPlane": self.plane})
        self.opened: list[Any] = []
        self.ran: list[str] = []
        Gui.runCommand = lambda name, _i=0: self.ran.append(name)
        Gui.Selection = types.SimpleNamespace(
            clearSelection=lambda: None,
            addSelection=lambda _d, _n: None)

    def decline(self) -> None:
        """Nxt's panel does not open: FreeCAD's way is the fallback."""
        patcher = mock.patch.object(editing, "open_nxt_attachment",
                                    return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self) -> None:
        sys.modules.pop("AttachmentEditor", None)
        sys.modules.pop("AttachmentEditor.Commands", None)

    def install_editor(self) -> None:
        commands = types.ModuleType("AttachmentEditor.Commands")
        commands.editAttachment = (
            lambda obj, **kw: self.opened.append((obj, kw)))
        package = types.ModuleType("AttachmentEditor")
        package.Commands = commands
        sys.modules["AttachmentEditor"] = package
        sys.modules["AttachmentEditor.Commands"] = commands

    def test_nxts_panel_opens_first(self) -> None:
        self.install_editor()
        with mock.patch.object(editing, "open_nxt_attachment",
                               return_value=True) as nxt:
            editing.edit_attachment("Doc", "DatumPlane")
        nxt.assert_called_once_with(self.plane)
        self.assertEqual(self.opened, [])

    def test_the_attachment_editor_opens_with_its_own_undo_step(self):
        self.decline()
        self.install_editor()
        editing.edit_attachment("Doc", "DatumPlane")
        self.assertEqual(self.opened, [(self.plane, {
            "take_selection": False, "create_transaction": True})])
        self.assertEqual(self.ran, [])

    def test_without_it_the_command_is_run(self) -> None:
        self.decline()
        sys.modules["AttachmentEditor"] = None  # type: ignore[assignment]
        editing.edit_attachment("Doc", "DatumPlane")
        self.assertEqual(self.ran, ["Part_EditAttachment"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
