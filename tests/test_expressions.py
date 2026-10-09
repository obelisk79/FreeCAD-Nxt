"""Expression editing: what is being typed, and what fits there.

Run with: python3 tests/test_expressions.py
"""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

sys.modules.setdefault("FreeCAD", types.ModuleType("FreeCAD"))
sys.modules.setdefault("FreeCADGui", types.ModuleType("FreeCADGui"))

from freecad.nxt import expressions as ex  # noqa: E402


class TokenTests(unittest.TestCase):

    def token(self, text: str, cursor: int | None = None) -> tuple:
        t = ex.token_at(text, len(text) if cursor is None else cursor)
        return t.start, t.owner, t.prefix

    def test_a_bare_name(self) -> None:
        self.assertEqual(self.token("=Le"), (1, "", "Le"))

    def test_after_an_operator(self) -> None:
        self.assertEqual(self.token("=Length * 2 + Pa"), (14, "", "Pa"))

    def test_a_property_of_an_object(self) -> None:
        self.assertEqual(self.token("=Pad.Len"), (5, "Pad", "Len"))

    def test_a_property_of_a_labelled_object(self) -> None:
        text = "=<<Base plate>>.Th"
        self.assertEqual(self.token(text), (16, "<<Base plate>>", "Th"))

    def test_a_label_being_typed(self) -> None:
        self.assertEqual(self.token("=<<Base pl"), (1, "", "<<Base pl"))

    def test_at_the_cursor_not_the_end(self) -> None:
        self.assertEqual(self.token("=Pad.Length * 2", 8), (5, "Pad", "Len"))

    def test_nothing_typed_yet(self) -> None:
        self.assertEqual(self.token("="), (1, "", ""))
        self.assertEqual(self.token("=Pad."), (5, "Pad", ""))


OBJECTS = [("Pad", "Pad"), ("Sketch", "Base profile"), ("VarSet", "Params")]
PROPS = {"Pad": ["Length", "Length2", "Offset"],
         "Sketch": ["Constraints", "Placement"],
         "Base profile": ["Constraints", "Placement"],
         "Params": ["Thickness", "Width"]}


def properties_of(name: str) -> Any:
    return PROPS.get(name)


class SuggestTests(unittest.TestCase):

    def labels(self, text: str, owner_props: tuple = ("Length",)) -> list:
        token = ex.token_at(text, len(text))
        return [(s.label, s.insert, s.kind) for s in ex.suggest(
            token, OBJECTS, owner_props, properties_of)]

    def test_properties_after_a_dot(self) -> None:
        self.assertEqual(self.labels("=Pad.Len"),
                         [("Length", "Length", "property"),
                          ("Length2", "Length2", "property")])

    def test_through_a_label(self) -> None:
        found = self.labels("=<<Params>>.Th")
        self.assertEqual(found[0], ("Thickness", "Thickness", "property"))

    def test_objects_by_name_or_label_with_the_right_reference(self) -> None:
        found = self.labels("=Ba")
        self.assertIn(("Base profile", "<<Base profile>>.", "object"), found)
        found = self.labels("=Pa")
        self.assertIn(("Params", "<<Params>>.", "object"), found)
        self.assertIn(("Pad", "Pad.", "object"), found)

    def test_the_owners_own_properties_and_functions(self) -> None:
        found = self.labels("=Le")
        self.assertEqual(found[0], ("Length", "Length", "property"))
        found = self.labels("=sq")
        self.assertIn(("sqrt", "sqrt(", "function"), found)

    def test_starts_with_before_contains(self) -> None:
        found = [label for label, _i, _k in self.labels("=Pad.L")]
        self.assertEqual(found, ["Length", "Length2"])
        found = [label for label, _i, _k in self.labels("=Pad.e")]
        self.assertEqual(found, ["Length", "Length2", "Offset"])
        self.assertEqual(self.labels("=Pad.set"),
                         [("Offset", "Offset", "property")])

    def test_an_unknown_object_offers_nothing(self) -> None:
        self.assertEqual(self.labels("=Nothing.L"), [])

    def test_at_most_the_limit(self) -> None:
        token = ex.token_at("=", 1)
        many = [("O%d" % i, "O%d" % i) for i in range(40)]
        self.assertEqual(len(ex.suggest(token, many, (), properties_of)),
                         ex.LIMIT)


class ApplyTests(unittest.TestCase):

    def test_replaces_what_was_typed(self) -> None:
        text = "=Pad.Len * 2"
        token = ex.token_at(text, 8)
        self.assertEqual(ex.apply_suggestion(text, token, 8, "Length"),
                         ("=Pad.Length * 2", 11))

    def test_and_the_rest_of_the_name_under_the_cursor(self) -> None:
        text = "=Pad.Lenxx"
        token = ex.token_at(text, 8)
        self.assertEqual(ex.apply_suggestion(text, token, 8, "Length")[0],
                         "=Pad.Length")

    def test_an_object_leaves_the_cursor_after_its_dot(self) -> None:
        text = "=Ba"
        token = ex.token_at(text, 3)
        self.assertEqual(
            ex.apply_suggestion(text, token, 3, "<<Base profile>>."),
            ("=<<Base profile>>.", 18))


class ValueTests(unittest.TestCase):

    def test_the_marker_comes_off(self) -> None:
        self.assertEqual(ex.strip_marker(" = Pad.Length * 2"),
                         "Pad.Length * 2")
        self.assertEqual(ex.strip_marker("2 mm"), "2 mm")

    def test_a_quantity_shows_as_the_user_writes_it(self) -> None:
        q = types.SimpleNamespace(UserString="20.00 mm")
        self.assertEqual(ex.describe_value(q), "20.00 mm")
        self.assertEqual(ex.describe_value(0.5), "0.5")
        self.assertEqual(ex.describe_value(3), "3")

    def test_references(self) -> None:
        self.assertEqual(ex.reference("Pad", "Pad"), "Pad")
        self.assertEqual(ex.reference("Sketch", "Base"), "<<Base>>")
        self.assertEqual(ex.unreference("<<Base>>"), "Base")
        self.assertEqual(ex.unreference("Doc#Pad"), "Pad")


if __name__ == "__main__":
    unittest.main(verbosity=2)
