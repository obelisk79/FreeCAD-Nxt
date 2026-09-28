"""FreeCAD's drag-handle steps, read and written in Nxt's terms.

Run with: python3 tests/test_gizmos.py
"""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

STORE: dict[str, dict[str, Any]] = {}


class Group:
    """One parameter group, kept in STORE."""

    def __init__(self, path: str) -> None:
        self.values = STORE.setdefault(path, {})

    def _get(self, key: str, default: Any) -> Any:
        return self.values.get(key, default)

    def _set(self, key: str, value: Any) -> None:
        self.values[key] = value

    GetInt = GetBool = GetFloat = GetString = _get
    SetInt = SetBool = SetFloat = SetString = _set


App = types.ModuleType("FreeCAD")
App.ParamGet = Group
App.Console = types.SimpleNamespace(PrintError=lambda _m: None)
sys.modules["FreeCAD"] = App

from freecad.nxt.tree import gizmos  # noqa: E402


class GizmoTests(unittest.TestCase):

    def setUp(self) -> None:
        STORE.clear()

    def gizmo(self, key: str) -> Any:
        return STORE[gizmos.GIZMOS][key]

    def test_freecads_own_defaults_read_as_coarse_first_and_shift(self):
        self.assertEqual(gizmos.read(), {
            "plain": "coarse", "key": "shift", "coarse": True,
            "step": 1.0, "linear": 5, "rotation": 5})

    def test_writing_fine_first_and_ctrl(self) -> None:
        gizmos.write({"plain": "fine", "key": "ctrl"})
        self.assertEqual(self.gizmo("DefaultCoarseDragBehavior"), 1)
        self.assertEqual(self.gizmo("FineSnapModifier"), 0x04000000)
        self.assertEqual(gizmos.read()["plain"], "fine")
        self.assertEqual(gizmos.read()["key"], "ctrl")

    def test_steps_and_limits(self) -> None:
        gizmos.write({"step": 0.5, "linear": 0, "rotation": 15,
                      "coarse": False})
        self.assertEqual(STORE[gizmos.HISTORY]["LastTranslationIncrement"],
                         0.5)
        self.assertEqual(self.gizmo("CoarseLinearSnapMultiplier"), 1)
        self.assertEqual(self.gizmo("CoarseRotationSnapMultiplier"), 15)
        self.assertFalse(self.gizmo("EnableCoarseSnap"))

    def test_defaults_are_applied_once_only(self) -> None:
        self.assertTrue(gizmos.apply_defaults_once())
        self.assertEqual(gizmos.read()["plain"], "fine")
        gizmos.write({"plain": "coarse", "key": "shift"})
        self.assertFalse(gizmos.apply_defaults_once())
        self.assertEqual(gizmos.read()["plain"], "coarse")

    def test_the_step_sizes_are_left_alone_by_the_defaults(self) -> None:
        gizmos.write({"linear": 10})
        gizmos.apply_defaults_once()
        self.assertEqual(gizmos.read()["linear"], 10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
