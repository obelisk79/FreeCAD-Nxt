"""The Property Inspector's layout, built from what objects say of themselves.

Run with: python3 tests/test_inspector.py
"""

from __future__ import annotations

import math
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

from freecad.nxt.tree import inspector  # noqa: E402


class Quantity:
    def __init__(self, text: str) -> None:
        self.UserString = text


class Vector:
    def __init__(self, x: float = 0, y: float = 0, z: float = 0) -> None:
        self.x, self.y, self.z = x, y, z

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Vector) and (
            (self.x, self.y, self.z) == (other.x, other.y, other.z))


class Rotation:
    def __init__(self, axis: Vector, angle_degrees: float) -> None:
        self.Axis = axis
        self.Angle = math.radians(angle_degrees)


class Placement:
    def __init__(self) -> None:
        self.Base = Vector(1, 2, 3)
        self.Rotation = Rotation(Vector(0, 0, 1), 90)


App.Rotation = Rotation


class Document:
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


class Thing:
    """A document object: properties with a group, a kind and modes."""

    def __init__(self, type_id: str, props: dict[str, tuple[str, str, Any]],
                 modes: dict[str, list[str]] | None = None,
                 document: Document | None = None) -> None:
        self.TypeId = type_id
        self.Label = type_id.split("::")[-1]
        self.Name = self.Label
        self.Document = document or Document()
        self._props = props
        self._modes = modes or {}
        self.PropertiesList = list(props)
        self.ExpressionEngine: list[tuple[str, str]] = []
        for name, (_group, _type, value) in props.items():
            setattr(self, name, value)

    def getGroupOfProperty(self, prop: str) -> str:
        return self._props[prop][0]

    def getTypeIdOfProperty(self, prop: str) -> str:
        return self._props[prop][1]

    def getEditorMode(self, prop: str) -> list[str]:
        return self._modes.get(prop, [])

    def getDocumentationOfProperty(self, prop: str) -> str:
        return "about " + prop

    def getEnumerationsOfProperty(self, prop: str) -> list[str]:
        return ["Dimension", "ThroughAll"]

    def setExpression(self, prop: str, expression: str | None) -> None:
        self.ExpressionEngine = [e for e in self.ExpressionEngine
                                 if e[0] != prop]
        if expression is not None:
            self.ExpressionEngine.append((prop, expression))


def helix(**overrides: Any) -> Thing:
    props = {
        "Label": ("Base", "App::PropertyString", "Helix"),
        "Placement": ("Base", "App::PropertyPlacement", Placement()),
        "Pitch": ("Helix", "App::PropertyLength", Quantity("5.00 mm")),
        "Height": ("Helix", "App::PropertyLength", Quantity("40.00 mm")),
        "LocalCoord": ("Helix", "App::PropertyEnumeration", "Dimension"),
        "Visible2": ("Helix", "App::PropertyBool", True),
        "Secret": ("Helix", "App::PropertyFloat", 1.0),
    }
    props.update(overrides)
    return Thing("Part::Helix", props, {"Secret": ["Hidden"]})


class DescribeTests(unittest.TestCase):

    def test_groups_are_freecads_with_the_own_group_first(self) -> None:
        groups = inspector.describe([helix()])
        self.assertEqual([g["name"] for g in groups], ["Helix", "Base"])
        self.assertTrue(groups[0]["open"])
        self.assertFalse(groups[1]["open"])     # Base starts collapsed

    def test_compact_kinds_take_half_a_row(self) -> None:
        items = {i["name"]: i for g in inspector.describe([helix()])
                 for i in g["items"]}
        self.assertFalse(items["Pitch"]["wide"])
        self.assertFalse(items["LocalCoord"]["wide"])
        self.assertTrue(items["Label"]["wide"])
        self.assertTrue(items["Placement"]["wide"])

    def test_labels_split_like_the_native_panel(self) -> None:
        self.assertEqual(inspector.label_for("UseCustomVector"),
                         "Use Custom Vector")
        self.assertEqual(inspector.label_for("Length2"), "Length2")

    def test_hidden_properties_are_left_out(self) -> None:
        names = [i["name"] for g in inspector.describe([helix()])
                 for i in g["items"]]
        self.assertNotIn("Secret", names)

    def test_a_quantity_shows_its_unit_apart(self) -> None:
        pitch = inspector.describe([helix()])[0]["items"][0]
        self.assertEqual((pitch["text"], pitch["unit"]), ("5.00", "mm"))
        self.assertEqual(pitch["tip"], "about Pitch")

    def test_a_placement_is_position_and_rotation(self) -> None:
        base = inspector.describe([helix()])[1]["items"]
        placement = next(i for i in base if i["name"] == "Placement")
        self.assertEqual([p["path"] for p in placement["parts"]],
                         ["Base.x", "Base.y", "Base.z",
                          "Axis.x", "Axis.y", "Axis.z", "Angle"])
        self.assertEqual(placement["parts"][6]["text"], "90")

    def test_an_addon_kind_falls_back_to_text(self) -> None:
        screw = Thing("Fasteners::Screw", {
            "ThreadData": ("Parameters", "App::PropertyPythonObject",
                           "<cache>"),
            "Base": ("Parameters", "App::PropertyLinkSub",
                     (types.SimpleNamespace(Label="Plate"), ["Face1"])),
        })
        items = inspector.describe([screw])[0]["items"]
        self.assertEqual(items[0]["kind"], "other")
        self.assertEqual(items[0]["text"], "<cache>")
        self.assertEqual(items[1]["kind"], "link")
        self.assertEqual(items[1]["links"], ["Plate"])

    def test_a_group_with_an_expression_opens(self) -> None:
        thing = helix()
        thing.setExpression("Label", "Spreadsheet.Name")
        base = inspector.describe([thing])[1]
        self.assertTrue(base["open"])

    def test_a_filter_keeps_matches_and_opens_their_groups(self) -> None:
        groups = inspector.describe([helix()], text_filter="place")
        self.assertEqual([i["name"] for g in groups for i in g["items"]],
                         ["Placement"])
        self.assertTrue(groups[0]["open"])

    def test_the_view_tab_reads_the_view_object(self) -> None:
        thing = helix()
        thing.ViewObject = Thing("Gui::ViewProvider", {
            "ShapeColor": ("Object Style", "App::PropertyColor",
                           (1.0, 0.5, 0.0)),
        })
        item = inspector.describe([thing], inspector.VIEW)[0]["items"][0]
        self.assertEqual((item["kind"], item["text"]), ("color", "#FF8000"))


class SeveralTests(unittest.TestCase):

    def test_only_shared_properties_of_the_same_kind(self) -> None:
        other = helix(Height=("Helix", "App::PropertyString", "tall"))
        del other._props["LocalCoord"]
        other.PropertiesList.remove("LocalCoord")
        names = [i["name"] for g in inspector.describe([helix(), other])
                 for i in g["items"]]
        self.assertIn("Pitch", names)
        self.assertNotIn("Height", names)       # a different kind
        self.assertNotIn("LocalCoord", names)   # not on both

    def test_differing_values_are_mixed(self) -> None:
        other = helix(Pitch=("Helix", "App::PropertyLength",
                             Quantity("8.00 mm")))
        items = {i["name"]: i for g in inspector.describe([helix(), other])
                 for i in g["items"]}
        self.assertTrue(items["Pitch"]["mixed"])
        self.assertFalse(items["Height"]["mixed"])

    def test_one_edit_is_one_undo_step_for_all(self) -> None:
        doc = Document()
        first, second = helix(), helix()
        first.Document = second.Document = doc
        self.assertTrue(inspector.apply([first, second], "Pitch", "7",
                                        unit="mm"))
        self.assertEqual((first.Pitch, second.Pitch), ("7 mm", "7 mm"))
        self.assertEqual(doc.log, ["open Edit Pitch", "commit", "recompute"])


class ApplyTests(unittest.TestCase):

    def test_equals_binds_an_expression(self) -> None:
        thing = helix()
        inspector.apply([thing], "Pitch", "= Height / 8")
        self.assertEqual(thing.ExpressionEngine, [("Pitch", "Height / 8")])

    def test_a_unit_typed_by_the_user_is_kept(self) -> None:
        thing = helix()
        inspector.apply([thing], "Pitch", "0.5 in", unit="mm")
        self.assertEqual(thing.Pitch, "0.5 in")

    def test_a_placement_component(self) -> None:
        thing = helix()
        inspector.apply([thing], "Placement", "12", part="Base.z")
        self.assertEqual(thing.Placement.Base.z, 12.0)
        inspector.apply([thing], "Placement", "45", part="Angle")
        self.assertAlmostEqual(math.degrees(thing.Placement.Rotation.Angle),
                               45.0)

    def test_a_colour(self) -> None:
        thing = helix()
        thing.ViewObject = Thing("Gui::ViewProvider", {
            "ShapeColor": ("Object Style", "App::PropertyColor",
                           (0.0, 0.0, 0.0)),
        }, document=thing.Document)
        inspector.apply([thing], "ShapeColor", "#FF0000", inspector.VIEW)
        self.assertEqual(thing.ViewObject.ShapeColor, (1.0, 0.0, 0.0))

    def test_a_failure_aborts(self) -> None:
        thing = helix()
        self.assertFalse(inspector.apply([thing], "Missing", "1"))
        self.assertEqual(thing.Document.log[-1], "abort")


if __name__ == "__main__":
    unittest.main(verbosity=2)
