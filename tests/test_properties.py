"""The detail strip's key values: what is shown, and how edits land.

Run with: python3 tests/test_properties.py
"""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

App = types.ModuleType("FreeCAD")
App.Console = types.SimpleNamespace(PrintError=lambda _m: None,
                                    PrintMessage=lambda _m: None)
sys.modules["FreeCAD"] = App

from freecad.nxt.tree import properties  # noqa: E402


class Quantity:
    def __init__(self, text: str) -> None:
        self.UserString = text


class FakeDocument:
    def __init__(self) -> None:
        self.log: list[str] = []

    def openTransaction(self, name: str) -> None:
        self.log.append("open " + name)

    def commitTransaction(self) -> None:
        self.log.append("commit")

    def abortTransaction(self) -> None:
        self.log.append("abort")

    def recompute(self) -> None:
        self.log.append("recompute")


class FakePad:
    """Enough of a PartDesign::Pad for the strip."""

    TypeId = "PartDesign::Pad"
    Name = "Pad"

    _types = {"Length": "App::PropertyLength",
              "Type": "App::PropertyEnumeration",
              "Reversed": "App::PropertyBool",
              "Label": "App::PropertyString",
              "Secret": "App::PropertyLength"}

    def __init__(self) -> None:
        self.Document = FakeDocument()
        self.PropertiesList = list(self._types)
        self.Length: Any = Quantity("10 mm")
        self.Type = "Dimension"
        self.Reversed = False
        self.Label = "Pad"
        self.Secret = Quantity("1 mm")
        self.ExpressionEngine: list[tuple[str, str]] = []

    def getTypeIdOfProperty(self, prop: str) -> str:
        return self._types[prop]

    def getEditorMode(self, prop: str) -> list[str]:
        return ["Hidden"] if prop == "Secret" else []

    def getEnumerationsOfProperty(self, prop: str) -> list[str]:
        return ["Dimension", "ThroughAll"]

    def setExpression(self, prop: str, expression: str | None) -> None:
        self.ExpressionEngine = [e for e in self.ExpressionEngine
                                 if e[0] != prop]
        if expression is not None:
            self.ExpressionEngine.append((prop, expression))


class DescribeTests(unittest.TestCase):

    def test_the_pad_shows_its_defining_values_in_order(self) -> None:
        entries = properties.describe(FakePad())
        self.assertEqual([e["name"] for e in entries],
                         ["Length", "Type", "Reversed"])
        length, kind, reversed_ = entries
        self.assertEqual((length["kind"], length["text"]),
                         ("quantity", "10 mm"))
        self.assertEqual(kind["options"], ["Dimension", "ThroughAll"])
        self.assertFalse(reversed_["checked"])

    def test_a_bound_expression_is_reported(self) -> None:
        pad = FakePad()
        pad.setExpression("Length", "Sketch.Width * 2")
        self.assertEqual(properties.describe(pad)[0]["expression"],
                         "Sketch.Width * 2")

    def test_an_unknown_type_shows_nothing_rather_than_a_guess(self) -> None:
        pad = FakePad()
        pad.TypeId = "Addon::Mystery"
        self.assertEqual(properties.describe(pad), [])

    def test_hidden_properties_are_not_counted(self) -> None:
        self.assertEqual(properties.visible_count(FakePad()), 4)


class ApplyTests(unittest.TestCase):

    def test_a_value_is_one_undo_step(self) -> None:
        pad = FakePad()
        self.assertTrue(properties.apply(pad, "Length", "12 mm"))
        self.assertEqual(pad.Length, "12 mm")
        self.assertEqual(pad.Document.log,
                         ["open Edit Length", "commit", "recompute"])

    def test_equals_binds_an_expression(self) -> None:
        pad = FakePad()
        properties.apply(pad, "Length", "= Sketch.Width * 2")
        self.assertEqual(pad.ExpressionEngine,
                         [("Length", "Sketch.Width * 2")])

    def test_a_plain_value_clears_an_expression(self) -> None:
        pad = FakePad()
        pad.setExpression("Length", "Sketch.Width")
        properties.apply(pad, "Length", "5 mm")
        self.assertEqual(pad.ExpressionEngine, [])

    def test_a_bool_is_set_as_a_bool(self) -> None:
        pad = FakePad()
        properties.apply(pad, "Reversed", True)
        self.assertIs(pad.Reversed, True)

    def test_a_failure_aborts_the_transaction(self) -> None:
        pad = FakePad()
        pad.getTypeIdOfProperty = None     # type: ignore[assignment]
        self.assertFalse(properties.apply(pad, "Length", "5 mm"))
        self.assertEqual(pad.Document.log[-1], "abort")


if __name__ == "__main__":
    unittest.main(verbosity=2)
