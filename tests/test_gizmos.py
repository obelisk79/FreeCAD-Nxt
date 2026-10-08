"""FreeCAD's drag-handle steps, read and written in Nxt's terms.

Run with: python3 tests/test_gizmos.py
"""

from __future__ import annotations

import sys
import tempfile
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

    def GetInts(self) -> list[str]:
        return [k for k, v in self.values.items()
                if isinstance(v, int) and not isinstance(v, bool)]

    def RemInt(self, key: str) -> None:
        del self.values[key]

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

    def enabled(self) -> Any:
        return STORE[gizmos.GIZMOS].get(gizmos.ENABLED, "unset")

    def test_handles_are_off_inside_and_back_on_after(self) -> None:
        with gizmos.hidden():
            self.assertIs(self.enabled(), False)
        self.assertIs(self.enabled(), True)

    def test_they_come_back_even_if_the_edit_fails(self) -> None:
        with self.assertRaises(RuntimeError):
            with gizmos.hidden():
                raise RuntimeError("setEdit failed")
        self.assertIs(self.enabled(), True)

    def test_a_user_who_has_them_off_keeps_them_off(self) -> None:
        Group(gizmos.GIZMOS).SetBool(gizmos.ENABLED, False)
        with gizmos.hidden():
            self.assertIs(self.enabled(), False)
        self.assertIs(self.enabled(), False)

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


class RestoreTests(unittest.TestCase):
    """Putting back what Nxt's defaults replaced."""

    def setUp(self) -> None:
        STORE.clear()

    def values(self) -> dict[str, Any]:
        return {k: v for k, v in STORE[gizmos.GIZMOS].items()
                if k in gizmos.OURS}

    def test_unset_before_is_unset_again(self) -> None:
        gizmos.apply_defaults_once()
        self.assertTrue(gizmos.restore_freecads())
        self.assertEqual(self.values(), {})
        self.assertEqual(gizmos.read()["plain"], "coarse")

    def test_set_before_is_set_back(self) -> None:
        gizmos.write({"key": "alt"})
        gizmos.apply_defaults_once()
        gizmos.restore_freecads()
        self.assertEqual(self.values(), {"FineSnapModifier": gizmos.ALT})

    def test_a_value_changed_since_is_the_users(self) -> None:
        gizmos.apply_defaults_once()
        gizmos.write({"key": "shift"})
        gizmos.restore_freecads()
        self.assertEqual(self.values(), {"FineSnapModifier": gizmos.SHIFT})

    def test_only_once_and_set_again_if_nxt_runs_again(self) -> None:
        self.assertFalse(gizmos.restore_freecads())     # never applied
        gizmos.apply_defaults_once()
        gizmos.restore_freecads()
        self.assertFalse(gizmos.restore_freecads())
        self.assertTrue(gizmos.apply_defaults_once())
        self.assertEqual(gizmos.read()["key"], "ctrl")

    def test_only_when_nxt_is_disabled_or_gone(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / gizmos.MANIFEST).write_text("")
            gizmos.apply_defaults_once()
            self.assertFalse(gizmos.restore_if_leaving(root))
            (root / gizmos.DISABLED).write_text("")
            self.assertTrue(gizmos.restore_if_leaving(root))
            gizmos.apply_defaults_once()
            (root / gizmos.DISABLED).unlink()
            (root / gizmos.MANIFEST).unlink()
            self.assertTrue(gizmos.restore_if_leaving(root))


if __name__ == "__main__":
    unittest.main(verbosity=2)
