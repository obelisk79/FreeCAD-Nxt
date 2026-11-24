"""Switching a feature between its additive and subtractive kinds.

Run with: python3 tests/test_variant.py   (needs PySide6)
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

import fakes  # noqa: E402

App, Gui = fakes.install()

from freecad.nxt.tools import variant  # noqa: E402

PAD_TYPES = ["Length", "UpToLast", "UpToFirst", "UpToFace", "TwoLengths"]
POCKET_TYPES = ["Length", "ThroughAll", "UpToFirst", "UpToFace",
                "TwoLengths"]


class Thing:
    """A document object: typed properties, links in, expressions."""

    def __init__(self, type_id: str, name: str,
                 props: dict[str, tuple[str, Any]] | None = None,
                 enums: dict[str, list[str]] | None = None,
                 read_only: tuple[str, ...] = ()) -> None:
        self.TypeId, self.Name, self.Label = type_id, name, name
        self._types = {p: t for p, (t, _v) in (props or {}).items()}
        self._enums = enums or {}
        self._read_only = read_only
        self.PropertiesList = ["Label", *self._types]
        self._types["Label"] = "App::PropertyString"
        self.InList: list[Any] = []
        self.ExpressionEngine: list[tuple[str, str]] = []
        for prop, (_t, value) in (props or {}).items():
            setattr(self, prop, value)

    def getTypeIdOfProperty(self, prop: str) -> str:  # noqa: N802
        return self._types[prop]

    def getEnumerationsOfProperty(self, prop: str) -> list[str]:  # noqa: N802
        return self._enums.get(prop, [])

    def getEditorMode(self, prop: str) -> list[str]:  # noqa: N802
        return ["ReadOnly"] if prop in self._read_only else []

    def setExpression(self, prop: str, expression: str) -> None:  # noqa: N802
        self.ExpressionEngine = [(p, e) for p, e in self.ExpressionEngine
                                 if p != prop] + [(prop, expression)]


def pad(**values: Any) -> Thing:
    props = {"Type": ("App::PropertyEnumeration", "Length"),
             "Length": ("App::PropertyLength", 12.0),
             "Profile": ("App::PropertyLinkSub", None),
             "Midplane": ("App::PropertyBool", False),
             "Operation": ("App::PropertyEnumeration", "Union")}
    thing = Thing("PartDesign::Pad", "Pad", props,
                  {"Type": PAD_TYPES, "Operation": ["Union"]})
    for name, value in values.items():
        setattr(thing, name, value)
    return thing


def pocket() -> Thing:
    props = {"Type": ("App::PropertyEnumeration", "Length"),
             "Length": ("App::PropertyLength", 5.0),
             "Profile": ("App::PropertyLinkSub", None),
             "Midplane": ("App::PropertyBool", False),
             "Operation": ("App::PropertyEnumeration", "Subtraction"),
             "Refine": ("App::PropertyBool", False)}
    return Thing("PartDesign::Pocket", "Pocket", props,
                 {"Type": POCKET_TYPES,
                  "Operation": ["Subtraction", "Common"]})


class CopyTests(unittest.TestCase):

    def test_shared_settings_are_copied(self) -> None:
        sketch = Thing("Sketcher::SketchObject", "Sketch")
        old, new = pad(Profile=(sketch, [""])), pocket()
        variant._copy(old, new)
        self.assertEqual((new.Length, new.Profile, new.Operation),
                         (12.0, (sketch, [""]), "Subtraction"))

    def test_a_choice_the_other_kind_lacks_is_left(self) -> None:
        new = pocket()
        variant._copy(pad(Type="UpToLast"), new)
        self.assertEqual(new.Type, "Length")

    def test_read_only_settings_are_left(self) -> None:
        new = pocket()
        new._read_only = ("Length",)
        variant._copy(pad(), new)
        self.assertEqual(new.Length, 5.0)

    def test_expressions_follow(self) -> None:
        old = pad()
        old.setExpression("Length", "Spreadsheet.depth")
        new = pocket()
        variant._copy(old, new)
        self.assertEqual(new.ExpressionEngine,
                         [("Length", "Spreadsheet.depth")])


class RelinkTests(unittest.TestCase):

    def test_links_and_expressions_move_to_the_new_feature(self) -> None:
        old, new = pad(), pocket()
        fillet = Thing("PartDesign::Fillet", "Fillet",
                       {"Base": ("App::PropertyLinkSub", (old, ["Edge3"]))})
        fillet.setExpression("Radius", "Pad.Length / 4 + PadX.Length")
        body = Thing("PartDesign::Body", "Body",
                     {"Group": ("App::PropertyLinkList", [old, new]),
                      "Tip": ("App::PropertyLink", old)})
        old.InList = [fillet, body, new]
        variant._relink(old, new)
        self.assertEqual(fillet.Base, (new, ["Edge3"]))
        self.assertEqual(fillet.ExpressionEngine,
                         [("Radius", "Pocket.Length / 4 + PadX.Length")])
        self.assertIs(body.Tip, new)
        self.assertEqual(body.Group, [old, new])    # the body's to change


class NamingTests(unittest.TestCase):

    def test_default_labels(self) -> None:
        self.assertTrue(variant._default_label(pad()))
        renamed = pad()
        renamed.Label = "Pad002"
        self.assertTrue(variant._default_label(renamed))
        renamed.Label = "Boss"
        self.assertFalse(variant._default_label(renamed))

    def test_kind_for_each_operation(self) -> None:
        feature = Thing("PartDesign::AdditiveHelix", "AdditiveHelix")
        self.assertEqual(variant.kind_for(feature, "Union"),
                         "PartDesign::AdditiveHelix")
        self.assertEqual(variant.kind_for(feature, "Common"),
                         "PartDesign::SubtractiveHelix")
        self.assertEqual(variant.kind_for(feature, "Bogus"), "")
        fillet = Thing("PartDesign::Fillet", "Fillet")
        self.assertEqual(variant.kind_for(fillet, "Common"), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
