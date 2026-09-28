"""Tracing a face picked on a Body back to the feature that made it.

The element histories here are the ones FreeCAD 26.3 reported for a Body
of Pad, Pocket (ID 0x13), Pocket001 (0x16) and Pocket002, the tip.

Run with: python3 tests/test_picking.py
"""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from freecad.nxt.tree import picking  # noqa: E402


class Shape:
    """A shape's element map: name -> (owner ID, name before)."""

    def __init__(self, history: dict[str, tuple[int, str]]) -> None:
        self.history = history

    def getElementHistory(self, name: str) -> Any:
        if name not in self.history:
            return None
        owner, before = self.history[name]
        return (owner, before, [])


class Obj:
    def __init__(self, doc: Doc, name: str, ident: int,
                 history: dict[str, tuple[int, str]] | None = None) -> None:
        self.Document, self.Name, self.ID = doc, name, ident
        self.Shape = Shape(history or {})
        self.children: dict[str, Obj] = {}
        doc.Objects.append(self)

    def isDerivedFrom(self, type_name: str) -> bool:
        if self.Name.startswith("Sketch"):
            return type_name in ("Part::Feature", "Part::Part2DObject")
        return type_name in ("Part::Feature", "PartDesign::Feature")

    def getSubObject(self, subname: str,
                     retType: int = 0) -> Any:  # noqa: N803 - FreeCAD API
        return self.children.get(subname.split(".", 1)[0], self)


class Doc:
    def __init__(self) -> None:
        self.Objects: list[Obj] = []

    def getObject(self, name: str) -> Obj | None:
        return next((o for o in self.Objects if o.Name == name), None)


# Pocket001's own face: generated (;:G) from Sketch003's edges (0xf).
OWN = ";#134:46b;:H16,F"
# Made by Pocket (;:H13), then cut again (;:M) by Pocket001.
CHANGED = ";#132:467;:H16,F"
BEFORE_CHANGED = "#b8:1127;:M;CUT;:H13:7,F"
# Made by the Pad, passed on untouched by Pocket and Pocket001.
CARRIED = ";#12c:463;:H16,F"


def body() -> Doc:
    doc = Doc()
    top = Obj(doc, "Body", 1)
    Obj(doc, "Sketch002", 0x0d)
    Obj(doc, "Sketch003", 0x0f)
    Obj(doc, "Pad", 0x0a)
    Obj(doc, "Pocket", 0x13, {
        BEFORE_CHANGED: (0x13, "#a1:22;:G;XTR;:Hd:7,F")})
    Obj(doc, "Pocket001", 0x16)
    tip = Obj(doc, "Pocket002", 0x17, {
        OWN: (-0x16, "#85:4401;:G0;XTR;:Hf:8,F"),
        CHANGED: (0x16, BEFORE_CHANGED),
        ";#99:1;:H17,F": (0x17, "#98:2;:G;XTR;:Hf:8,F"),
    })
    top.children["Pocket002"] = tip
    return doc


class TargetTests(unittest.TestCase):

    def test_a_face_made_by_an_earlier_feature(self) -> None:
        self.assertEqual(picking.target(
            body(), "Body", "Pocket002." + OWN + ".Face23"), "Pocket001")

    def test_a_face_changed_later_goes_back_to_its_maker(self) -> None:
        self.assertEqual(picking.target(
            body(), "Body", "Pocket002." + CHANGED + ".Face22"), "Pocket")

    def test_a_face_carried_through_goes_back_to_its_maker(self) -> None:
        # Pocket001 passed the face on untouched: a bare tag, no marker.
        doc = body()
        doc.getObject("Pocket002").Shape.history[CARRIED] = (
            0x16, "#ac:1123;:H13,F")
        doc.getObject("Pocket").Shape.history["#ac:1123;:H13,F"] = (
            0x13, "#9a:40;:M;CUT;:Ha:7,F")
        doc.getObject("Pad").Shape.history["#9a:40;:M;CUT;:Ha:7,F"] = (
            0x0a, "#88:1;:G;XTR;:H9:7,F")
        self.assertEqual(picking.target(
            doc, "Body", "Pocket002." + CARRIED + ".Face5"), "Pad")

    def test_the_walk_stops_where_history_ends(self) -> None:
        doc = body()
        doc.getObject("Pocket").Shape.history = {}
        self.assertEqual(picking.target(
            doc, "Body", "Pocket002." + CHANGED + ".Face22"), "Pocket")

    def test_the_tips_own_face_stays_on_the_tip(self) -> None:
        self.assertEqual(picking.target(
            body(), "Body", "Pocket002.;#99:1;:H17,F.Face1"), "Pocket002")

    def test_no_element_map_falls_back_to_what_was_picked(self) -> None:
        self.assertEqual(picking.target(body(), "Body", "Pocket002.Face9"),
                         "Pocket002")

    def test_the_tag_in_the_name_when_freecad_has_no_history(self) -> None:
        self.assertEqual(picking.target(
            body(), "Body", "Pocket002.;#77:7;:H16,F.Face3"), "Pocket001")

    def test_an_object_without_an_element(self) -> None:
        self.assertEqual(picking.target(body(), "Body", ""), "Body")
        self.assertEqual(picking.target(body(), "Body", "Pocket002."),
                         "Pocket002")

    def test_an_unknown_object(self) -> None:
        self.assertIsNone(picking.target(body(), "Nothing", "Face1"))


class PickTests(unittest.TestCase):

    def entry(self) -> Any:
        return types.SimpleNamespace(
            Object=types.SimpleNamespace(Name="Body"),
            SubElementNames=["Pocket002.;#12:3;:H9,F.Face2",
                             "Pocket002." + OWN + ".Face23"])

    def test_the_selection_supplies_the_mapped_name(self) -> None:
        # What the observer is told, and what the selection holds.
        self.assertEqual(
            picking.full_pick("Pocket002", "Face23", [self.entry()]),
            ("Body", "Pocket002." + OWN + ".Face23"))
        self.assertEqual(
            picking.full_pick("Body", "Pocket002.Face23", [self.entry()]),
            ("Body", "Pocket002." + OWN + ".Face23"))
        self.assertEqual(
            picking.full_pick("Pocket002", "Face5", [self.entry()]),
            ("Pocket002", "Face5"))

    def test_the_whole_live_path(self) -> None:
        top, sub = picking.full_pick("Pocket002", "Face23", [self.entry()])
        self.assertEqual(picking.target(body(), top, sub), "Pocket001")

    def test_names(self) -> None:
        sub = "P.;#134:46b;:H16,F.Face23"
        self.assertEqual(picking.mapped_of(sub), "#134:46b;:H16,F")
        self.assertEqual(picking.element_of(sub), "Face23")
        self.assertEqual(picking.mapped_of("P.Face23"), "")
        self.assertEqual(picking.element_of("Pad001.Face6"), "Face6")
        self.assertEqual(picking.element_of("Pad001."), "")
        self.assertEqual(picking.element_of(""), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
