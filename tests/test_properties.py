"""The detail strip's key values: what is shown, and how edits land.

Run with: python3 tests/test_properties.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fakes  # noqa: E402

App, Gui = fakes.install()

from freecad.nxt.inspector import properties  # noqa: E402


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


class FakeVarSet:
    """Enough of an App::VarSet: added properties, tooltips, rename."""

    TypeId = "App::VarSet"
    Name = "VarSet"
    BUILT_IN = ("Label",)

    def __init__(self) -> None:
        self.Document = FakeDocument()
        self.Label = "VarSet"
        self.ExpressionEngine: list[tuple[str, str]] = []
        self._types = {"Label": "App::PropertyString"}
        self._docs: dict[str, str] = {}
        self._groups: dict[str, str] = {}

    @property
    def PropertiesList(self) -> list[str]:  # noqa: N802 - FreeCAD API
        return list(self._types)

    def addProperty(self, type_id: str, name: str, group: str = "",
                    doc: str = "") -> None:
        if name in self._types:
            raise NameError("Property VarSet.%s already exists" % name)
        if not name.isidentifier():
            raise NameError("Invalid property name '%s'" % name)
        self._types[name] = type_id
        self._docs[name], self._groups[name] = doc, group
        setattr(self, name, Quantity("0 mm"))

    def renameProperty(self, old: str, new: str) -> None:
        if new in self._types:
            raise NameError("Property VarSet.%s already exists" % new)
        if not new.isidentifier():
            raise NameError("Invalid property name '%s'" % new)
        self._types = {new if k == old else k: v
                       for k, v in self._types.items()}
        self._docs[new] = self._docs.pop(old, "")
        self._groups[new] = self._groups.pop(old, "")
        setattr(self, new, getattr(self, old))

    def getPropertyStatus(self, prop: str) -> list[int]:
        return [] if prop in self.BUILT_IN else [properties.DYNAMIC_STATUS]

    def getTypeIdOfProperty(self, prop: str) -> str:
        return self._types[prop]

    def getDocumentationOfProperty(self, prop: str) -> str:
        return self._docs.get(prop, "")

    def setDocumentationOfProperty(self, prop: str, doc: str) -> None:
        self._docs[prop] = doc

    def getGroupOfProperty(self, prop: str) -> str:
        return self._groups.get(prop, "")

    def getEditorMode(self, prop: str) -> list[str]:
        return []


class VariableTests(unittest.TestCase):

    def varset(self) -> FakeVarSet:
        obj = FakeVarSet()
        obj.addProperty("App::PropertyLength", "Width", "Frame", "Across")
        obj.Document.log.clear()
        return obj

    def test_variables_carry_their_tooltip_and_type(self) -> None:
        entry = properties.describe(self.varset())[0]
        self.assertEqual((entry["name"], entry["tip"], entry["typeLabel"],
                          entry["variable"]),
                         ("Width", "Across", "Length", True))

    def test_a_rename_and_tooltip_are_one_undo_step(self) -> None:
        obj = self.varset()
        self.assertEqual(properties.edit_variable(obj, "Width", "Span",
                                                  "Side to side"), "")
        self.assertIn("Span", obj.PropertiesList)
        self.assertEqual(obj.getDocumentationOfProperty("Span"),
                         "Side to side")
        self.assertEqual(obj.Document.log,
                         ["open Edit variable Width", "commit", "recompute"])

    def test_a_taken_name_is_refused_in_words(self) -> None:
        obj = self.varset()
        why = properties.edit_variable(obj, "Width", "Label", "")
        self.assertIn("already taken", why)
        self.assertIn("Width", obj.PropertiesList)
        self.assertEqual(obj.Document.log[-1], "abort")

    def test_a_bad_name_says_what_a_name_may_be(self) -> None:
        why = properties.edit_variable(self.varset(), "Width", "two words",
                                       "")
        self.assertIn("letters, digits and underscores", why)

    def test_an_empty_name_is_refused_before_freecad_sees_it(self) -> None:
        obj = self.varset()
        self.assertEqual(properties.edit_variable(obj, "Width", "  ", ""),
                         "Enter a name.")
        self.assertEqual(obj.Document.log, [])

    def test_a_new_variable_joins_the_others_group(self) -> None:
        obj = self.varset()
        self.assertEqual(properties.add_variable(
            obj, "App::PropertyBool", "Mirrored", "Flip it"), "")
        self.assertEqual(obj.getGroupOfProperty("Mirrored"), "Frame")
        self.assertEqual(obj.getTypeIdOfProperty("Mirrored"),
                         "App::PropertyBool")

    def test_only_the_offered_types_can_be_added(self) -> None:
        self.assertEqual(properties.add_variable(
            self.varset(), "App::PropertyLink", "Other", ""),
            "Choose a type.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
