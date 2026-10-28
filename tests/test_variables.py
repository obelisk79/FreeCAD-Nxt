"""A VarSet's variables: renaming, tooltips and adding, as undo steps.

Run with: python3 tests/test_variables.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fakes  # noqa: E402

App, Gui = fakes.install()

from freecad.nxt.inspector import variables  # noqa: E402


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
        return [] if prop in self.BUILT_IN else [variables.DYNAMIC_STATUS]

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

    def test_a_rename_and_tooltip_are_one_undo_step(self) -> None:
        obj = self.varset()
        self.assertEqual(variables.edit(obj, "Width", "Span",
                                                  "Side to side"), "")
        self.assertIn("Span", obj.PropertiesList)
        self.assertEqual(obj.getDocumentationOfProperty("Span"),
                         "Side to side")
        self.assertEqual(obj.Document.log,
                         ["open Edit variable Width", "commit", "recompute"])

    def test_a_taken_name_is_refused_in_words(self) -> None:
        obj = self.varset()
        why = variables.edit(obj, "Width", "Label", "")
        self.assertIn("already taken", why)
        self.assertIn("Width", obj.PropertiesList)
        self.assertEqual(obj.Document.log[-1], "abort")

    def test_a_bad_name_says_what_a_name_may_be(self) -> None:
        why = variables.edit(self.varset(), "Width", "two words",
                                       "")
        self.assertIn("letters, digits and underscores", why)

    def test_an_empty_name_is_refused_before_freecad_sees_it(self) -> None:
        obj = self.varset()
        self.assertEqual(variables.edit(obj, "Width", "  ", ""),
                         "Enter a name.")
        self.assertEqual(obj.Document.log, [])

    def test_a_new_variable_joins_the_others_group(self) -> None:
        obj = self.varset()
        self.assertEqual(variables.add(
            obj, "App::PropertyBool", "Mirrored", "Flip it"), "")
        self.assertEqual(obj.getGroupOfProperty("Mirrored"), "Frame")
        self.assertEqual(obj.getTypeIdOfProperty("Mirrored"),
                         "App::PropertyBool")

    def test_only_the_offered_types_can_be_added(self) -> None:
        self.assertEqual(variables.add(
            self.varset(), "App::PropertyLink", "Other", ""),
            "Choose a type.")

    def test_only_variables_are_counted_as_added(self) -> None:
        self.assertEqual(variables.added(self.varset()), ("Width",))


if __name__ == "__main__":
    unittest.main(verbosity=2)
