"""The services: what works with the model panel closed.

Run with: python3 tests/test_services.py
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import types  # noqa: E402

import test_inspector  # noqa: E402,F401  (installs the FreeCAD stub)
from PySide6 import QtWidgets  # noqa: E402

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
MAIN = QtWidgets.QMainWindow()
Gui = sys.modules.setdefault("FreeCADGui", types.ModuleType("FreeCADGui"))
Gui.getMainWindow = lambda: MAIN  # type: ignore[attr-defined]

from freecad.nxt import services  # noqa: E402
from freecad.nxt.tree import editing  # noqa: E402


class Parts:
    """Stands in for the double-click editor and the floating field."""

    log: list[str] = []

    def __init__(self, _owner: Any) -> None:
        pass

    def install(self) -> None:
        self.log.append("install")

    def remove(self) -> None:
        self.log.append("remove")


class ServicesTests(unittest.TestCase):

    def setUp(self) -> None:
        Parts.log = []
        import freecad.nxt.tree.face_edit as face_edit
        import freecad.nxt.tree.float_input as float_input
        self.saved = (face_edit.DoubleClickEditor,
                      float_input.FloatingInput, editing.enter_edit)
        face_edit.DoubleClickEditor = Parts  # type: ignore
        float_input.FloatingInput = Parts  # type: ignore
        self.edits: list[tuple[str, str]] = []
        editing.enter_edit = lambda d, n: self.edits.append((d, n))

    def tearDown(self) -> None:
        services.stop()
        import freecad.nxt.tree.face_edit as face_edit
        import freecad.nxt.tree.float_input as float_input
        (face_edit.DoubleClickEditor, float_input.FloatingInput,
         editing.enter_edit) = self.saved

    def test_no_theme_until_started(self) -> None:
        self.assertIsNone(services.theme())

    def test_start_is_idempotent_and_installs_both(self) -> None:
        first = services.start()
        self.assertIs(services.start(), first)
        self.assertEqual(Parts.log, ["install", "install"])
        services.stop()
        self.assertEqual(Parts.log[-2:], ["remove", "remove"])
        self.assertIsNone(services.instance())

    def test_an_edit_is_announced_then_deferred(self) -> None:
        live = services.start()
        assert live is not None
        heard: list[tuple[str, str]] = []
        live.featurePicked.connect(lambda d, n: heard.append((d, n)))
        live.edit_feature("Doc", "Pad")
        self.assertEqual(heard, [("Doc", "Pad")])
        self.assertEqual(self.edits, [])        # not inside the event
        APP.processEvents()
        self.assertEqual(self.edits, [("Doc", "Pad")])

    def test_the_edit_needs_no_panel(self) -> None:
        live = services.start()
        assert live is not None
        live.edit_feature("Doc", "Pocket")       # nobody listening
        APP.processEvents()
        self.assertEqual(self.edits, [("Doc", "Pocket")])


if __name__ == "__main__":
    unittest.main(verbosity=2)
