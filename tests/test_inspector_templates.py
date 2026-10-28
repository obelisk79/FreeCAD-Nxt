"""Property Inspector templates: Pad and Pocket laid out by task.

Run with: python3 tests/test_inspector_templates.py
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

from freecad.nxt.inspector import layout as inspector  # noqa: E402
from freecad.nxt.inspector import templates  # noqa: E402

TYPES = ["Length", "UpToLast", "UpToFirst", "UpToFace", "TwoLengths"]
SIDES = ["One side", "Two sides", "Symmetric"]
STARTS = ["Profile plane", "Offset", "Reference"]


Quantity = fakes.Quantity


class Feature:
    """A Pad with the properties FreeCAD 1.0 gives one, or some of them."""

    def __init__(self, type_id: str = "PartDesign::Pad",
                 **values: Any) -> None:
        self.TypeId = type_id
        self.Name = self.Label = type_id.split("::")[-1]
        self._props: dict[str, tuple[str, str, Any]] = {
            "Label": ("Base", "App::PropertyString", self.Name),
            "Type": ("Pad", "App::PropertyEnumeration", "Length"),
            "Length": ("Pad", "App::PropertyLength", Quantity("10 mm")),
            "Length2": ("Pad", "App::PropertyLength", Quantity("0 mm")),
            "Offset": ("Pad", "App::PropertyLength", Quantity("0 mm")),
            "Reversed": ("Pad", "App::PropertyBool", False),
            "Midplane": ("Pad", "App::PropertyBool", False),
            "TaperAngle": ("Pad", "App::PropertyAngle", Quantity("0 °")),
            "TaperAngle2": ("Pad", "App::PropertyAngle", Quantity("0 °")),
            "UseCustomVector": ("Pad", "App::PropertyBool", False),
            "Refine": ("Part Design", "App::PropertyBool", True),
            "Mystery": ("Pad", "App::PropertyFloat", 1.0),
        }
        self.PropertiesList = list(self._props)
        self.ExpressionEngine: list[tuple[str, str]] = []
        for name, (_g, _t, value) in self._props.items():
            setattr(self, name, value)
        for name, value in values.items():
            setattr(self, name, value)

    def getGroupOfProperty(self, prop: str) -> str:  # noqa: N802
        return self._props[prop][0]

    def getTypeIdOfProperty(self, prop: str) -> str:  # noqa: N802
        return self._props[prop][1]

    def getEditorMode(self, _prop: str) -> list[str]:  # noqa: N802
        return []

    def getDocumentationOfProperty(self, _prop: str) -> str:  # noqa: N802
        return ""

    def getEnumerationsOfProperty(self, prop: str) -> list[str]:  # noqa: N802
        return {"SideType": SIDES, "StartType": STARTS}.get(prop, TYPES)


def layout(*objects: Any, tab: str = inspector.DATA) -> list[dict]:
    return inspector.describe(list(objects), tab)


def names(group: dict) -> list[str]:
    """Every property a card shows: items, columns, then what follows."""
    out = [item["name"] for item in group["items"]]
    for column in group.get("columns", ()):
        out += [item["name"] for item in column["items"]]
    return out + [item["name"] for item in group.get("after", ())]


def modern(**values: Any) -> Feature:
    """A Pad as FreeCAD 27 has it: Sides, and a type for each side."""
    pad = Feature(**values)
    for name, kind, value in (
            ("SideType", "App::PropertyEnumeration", "One side"),
            ("Type2", "App::PropertyEnumeration", "Length"),
            ("TaperAngle2", "App::PropertyAngle", Quantity("0 °"))):
        pad._props[name] = ("Pad", kind, value)
        if name not in pad.PropertiesList:
            pad.PropertiesList.append(name)
        setattr(pad, name, values.get(name, value))
    return pad


class PadTests(unittest.TestCase):

    def test_the_cards_come_first_in_the_templates_order(self) -> None:
        groups = layout(modern())
        self.assertEqual([g["name"] for g in groups[:2]],
                         ["Extent", "Result"])
        extent = groups[0]
        self.assertEqual([i["name"] for i in extent["items"]], ["SideType"])
        self.assertEqual(len(extent["columns"]), 1)
        self.assertEqual(extent["columns"][0]["title"], "")
        self.assertEqual([i["name"] for i in extent["columns"][0]["items"]],
                         ["Length", "TaperAngle"])
        self.assertEqual([i["name"] for i in extent["after"]],
                         ["UseCustomVector"])

    def test_extent_has_no_heading_and_sides_no_label(self) -> None:
        extent = layout(modern())[0]
        self.assertFalse(extent["heading"])
        self.assertTrue(extent["open"])
        self.assertEqual(extent["items"][0]["label"], "")

    def test_multiple_faces_moves_under_part_design(self) -> None:
        pad = modern()
        pad._props["AllowMultiFace"] = ("SketchBased", "App::PropertyBool",
                                        True)
        pad.PropertiesList.append("AllowMultiFace")
        pad.AllowMultiFace = True
        groups = {g["name"]: names(g) for g in layout(pad)}
        self.assertIn("AllowMultiFace", groups["Part Design"])
        self.assertNotIn("SketchBased", groups)

    def test_shapes_and_materials_are_not_shown(self) -> None:
        pad = modern()
        for name, kind in (("Shape", "Part::PropertyPartShape"),
                           ("ShapeMaterial", "Materials::PropertyMaterial")):
            pad._props[name] = ("", kind, object())
            pad.PropertiesList.append(name)
            setattr(pad, name, object())
        shown = [n for g in layout(pad) for n in names(g)]
        self.assertNotIn("Shape", shown)
        self.assertNotIn("ShapeMaterial", shown)

    def test_type_leads_length_and_reversed_trails_direction(self) -> None:
        extent = layout(modern())[0]
        length, taper = extent["columns"][0]["items"]
        self.assertEqual(length["lead"]["name"], "Type")
        self.assertTrue(taper["narrow"])
        self.assertEqual(extent["after"][0]["trail"]["name"], "Reversed")

    def test_a_type_without_a_value_shows_alone(self) -> None:
        extent = layout(modern(Type="UpToLast"))[0]
        first = extent["columns"][0]["items"][0]
        self.assertEqual((first["name"], first["label"]), ("Type", "Up to"))

    def test_two_sides_add_a_second_column(self) -> None:
        extent = layout(modern(SideType="Two sides"))[0]
        self.assertEqual([c["title"] for c in extent["columns"]],
                         ["First side", "Second side"])
        self.assertEqual([i["name"] for i in extent["columns"][1]["items"]],
                         ["Length2", "TaperAngle2"])
        length = extent["columns"][1]["items"][0]
        self.assertEqual((length["label"], length["lead"]["name"]),
                         ("Length", "Type2"))

    def test_midplane_is_gone_once_sides_exist(self) -> None:
        everything = [n for g in layout(modern()) for n in names(g)]
        self.assertNotIn("Midplane", everything)

    def test_editors(self) -> None:
        extent = layout(modern())[0]
        sides = extent["items"][0]
        self.assertEqual(sides["editor"], "segmented")
        kind = extent["columns"][0]["items"][0]["lead"]
        self.assertEqual(kind["editor"], "dropdown")
        self.assertEqual(kind["optionLabels"][:2], ["Dimension", "To last"])
        self.assertNotIn("TwoLengths", kind["options"])

    def test_direction_is_two_named_states(self) -> None:
        direction = layout(modern())[0]["after"][0]
        self.assertEqual(direction["optionLabels"],
                         ["Sketch normal", "Custom"])

    def test_fields_follow_the_type(self) -> None:
        extent = layout(modern(Type="UpToFace"))[0]
        self.assertIn("Offset", names(extent))
        self.assertNotIn("Length", names(extent))
        self.assertNotIn("TaperAngle", names(extent))

    def test_an_older_freecad_with_two_lengths(self) -> None:
        extent = layout(Feature(Type="TwoLengths"))[0]
        self.assertEqual(len(extent["columns"]), 2)
        self.assertIn("Length2", names(extent))
        self.assertIn("TwoLengths",
                      extent["columns"][0]["items"][0]["lead"]["options"])

    def test_what_it_does_not_name_is_kept_closed_below(self) -> None:
        groups = layout(modern())
        rest = [g for g in groups if g.get("template") is None]
        self.assertTrue(rest[0]["rest"])
        kept = [n for g in rest for n in names(g)]
        self.assertEqual(sorted(kept), ["Label", "Mystery"])
        self.assertFalse(any(g["open"] for g in rest))
        placed = [n for g in groups for n in names(g)]
        self.assertEqual(len(placed), len(set(placed)))

    def test_a_pocket_shares_it_and_a_mixed_selection_does_not(self) -> None:
        self.assertEqual(layout(Feature("PartDesign::Pocket"))[0]["name"],
                         "Extent")
        both = layout(Feature(), Feature("PartDesign::Fillet"))
        self.assertNotIn("Extent", [g["name"] for g in both])

    def test_the_view_tab_is_left_generic(self) -> None:
        pad = Feature()
        pad.ViewObject = Feature("Gui::ViewProvider")
        self.assertNotIn("Extent",
                         [g["name"] for g in layout(pad, tab=inspector.VIEW)])


def started(start: str = "Profile plane", offset: str = "0 mm") -> Feature:
    """A FreeCAD 27 Pad with its start type and offset."""
    pad = modern()
    for name, kind, value in (
            ("StartType", "App::PropertyEnumeration", start),
            ("StartOffset", "App::PropertyLength", Quantity(offset)),
            ("StartReference", "App::PropertyLinkSub", None)):
        pad._props[name] = ("Pad", kind, value)
        pad.PropertiesList.append(name)
        setattr(pad, name, value)
    return pad


class StartTests(unittest.TestCase):

    def setUp(self) -> None:
        self.template = templates.for_objects([started()])

    def edits(self, pad: Feature, prop: str, value: Any) -> Any:
        return templates.coupled(self.template, [pad], prop, value)

    def test_profile_plane_shows_as_an_offset_of_zero(self) -> None:
        start = next(g for g in layout(started()) if g["name"] == "Start")
        offset = start["items"][0]
        kind = offset["beside"][0]
        self.assertEqual(kind["label"], "")
        self.assertEqual(kind["options"], ["Offset", "Reference"])
        self.assertEqual(kind["optionLabels"], ["Profile", "Reference"])
        self.assertEqual(kind["text"], "Offset")
        self.assertFalse(offset["readOnly"])
        self.assertEqual(len(start["items"]), 1)    # no reference yet

    def test_start_is_one_open_line(self) -> None:
        start = next(g for g in layout(started()) if g["name"] == "Start")
        self.assertTrue(start["open"])
        self.assertFalse(start["heading"])
        self.assertEqual(start["items"][0]["label"], "Start offset")

    def test_closed_when_sums_a_card_up(self) -> None:
        card = templates.Card(
            "Start", (templates.Item("StartOffset"),
                      templates.Item("StartType")),
            closed_when=(("StartOffset", (0,)),))
        template = templates.Template("t", ("PartDesign::Pad",), (card,))
        groups = {"Start": [inspector._entry(started(), n, {})
                            for n in ("StartOffset", "StartType")]}
        closed = templates.apply(template, [started()], groups)[0]
        self.assertFalse(closed["open"])
        self.assertEqual(closed["summary"], "0 mm · Profile plane")

    def test_typing_an_offset_makes_the_start_an_offset(self) -> None:
        self.assertEqual(self.edits(started(), "StartOffset", "2"),
                         [("StartType", "Offset"), ("StartOffset", "2")])
        self.assertEqual(self.edits(started(), "StartOffset", "0"),
                         [("StartType", "Offset"), ("StartOffset", "0")])

    def test_zero_never_goes_back_to_the_profile_plane(self) -> None:
        self.assertIsNone(self.edits(started("Offset", "2 mm"),
                                     "StartOffset", "0 mm"))

    def test_choosing_profile_writes_an_offset_start(self) -> None:
        self.assertEqual(self.edits(started("Reference", "0 mm"),
                                    "StartType", "Offset"),
                         [("StartType", "Offset")])
        self.assertEqual(self.edits(started(), "StartType", "Offset"),
                         [("StartType", "Offset")])
        self.assertEqual(self.edits(started("Offset"), "StartType",
                                    "Offset"), [])

    def test_a_reference_start_keeps_its_offset(self) -> None:
        self.assertIsNone(self.edits(started("Reference", "3 mm"),
                                     "StartOffset", "0"))

    def test_other_edits_are_left_alone(self) -> None:
        self.assertIsNone(self.edits(started(), "Length", "5"))


class ShowIfTests(unittest.TestCase):

    def test_a_missing_property_is_left_out_of_the_test(self) -> None:
        item = templates.Item(
            "Length2", show_if=(("SideType", ("Two sides",)),))
        self.assertTrue(templates.shown(item, [Feature()]))

    def test_any_test_holding_is_enough(self) -> None:
        item = templates.Item(
            "Length2", show_if=(("Type", ("TwoLengths",)),
                                ("Midplane", (True,))))
        self.assertFalse(templates.shown(item, [Feature()]))
        self.assertTrue(templates.shown(
            item, [Feature(Midplane=True)]))

    def test_the_shipped_files_load(self) -> None:
        templates.invalidate()
        ids = [t.id for t in templates.loaded()]
        self.assertIn("pd-extrude", ids)
        self.assertIn("pd-fillet", ids)


class Fillet(Feature):
    """A Fillet as FreeCAD gives one."""

    def __init__(self, **values: Any) -> None:
        super().__init__("PartDesign::Fillet")
        self._props = {
            "Label": ("Base", "App::PropertyString", "Fillet"),
            "Base": ("Base", "App::PropertyLinkSub", None),
            "SupportTransform": ("Base", "App::PropertyBool", False),
            "Radius": ("Fillet", "App::PropertyQuantityConstraint",
                       Quantity("1 mm")),
            "UseAllEdges": ("Fillet", "App::PropertyBool", False),
            "Refine": ("Part Design", "App::PropertyBool", False),
        }
        self.PropertiesList = list(self._props)
        for name, (_g, _t, value) in self._props.items():
            setattr(self, name, values.get(name, value))


class FilletTests(unittest.TestCase):

    def test_radius_and_edges_first(self) -> None:
        groups = layout(Fillet())
        self.assertEqual([g["name"] for g in groups[:2]],
                         ["Fillet", "Result"])
        self.assertEqual(names(groups[0]), ["Radius", "UseAllEdges", "Base"])
        self.assertEqual(groups[0]["items"][1]["optionLabels"],
                         ["Selected", "All"])

    def test_all_edges_hides_the_selection(self) -> None:
        self.assertEqual(names(layout(Fillet(UseAllEdges=True))[0]),
                         ["Radius", "UseAllEdges"])

    def test_result_switches(self) -> None:
        result = layout(Fillet())[1]
        self.assertEqual(names(result), ["Refine", "SupportTransform"])
        self.assertEqual({i["editor"] for i in result["items"]}, {"switch"})


class VarSet:
    """An App::VarSet: built-in Label and Label2, then added variables."""

    TypeId = "App::VarSet"

    def __init__(self, name: str = "VarSet") -> None:
        self.Name = self.Label = name
        self.Label2 = ""
        self.ExpressionEngine: list[tuple[str, str]] = []
        self._props: dict[str, tuple[str, str, str]] = {
            "Label": ("Base", "App::PropertyString", ""),
            "Label2": ("Base", "App::PropertyString", "")}
        self._added: set[str] = set()

    @property
    def PropertiesList(self) -> list[str]:  # noqa: N802 - FreeCAD API
        return list(self._props)

    def add(self, type_id: str, name: str, value: Any,
            tip: str = "") -> "VarSet":
        self._props[name] = ("Base", type_id, tip)
        self._added.add(name)
        setattr(self, name, value)
        return self

    def getPropertyStatus(self, prop: str) -> list[int]:  # noqa: N802
        return [21] if prop in self._added else []

    def getGroupOfProperty(self, prop: str) -> str:  # noqa: N802
        return self._props[prop][0]

    def getTypeIdOfProperty(self, prop: str) -> str:  # noqa: N802
        return self._props[prop][1]

    def getDocumentationOfProperty(self, prop: str) -> str:  # noqa: N802
        return self._props[prop][2]

    def getEditorMode(self, _prop: str) -> list[str]:  # noqa: N802
        return []

    def getEnumerationsOfProperty(self, _prop: str) -> list[str]:  # noqa: N802
        return []


def varset(name: str = "VarSet") -> VarSet:
    return (VarSet(name)
            .add("App::PropertyLength", "BaseLength", Quantity("250 mm"),
                 "Across the frame")
            .add("App::PropertyLength",
                 "SpindleClearanceHeightAboveTheSpoilboard",
                 Quantity("85 mm"), "Gap under the gantry")
            .add("App::PropertyInteger", "RailCount", 2))


class VarSetTests(unittest.TestCase):

    def test_variables_get_a_card_of_their_own_by_their_names(self) -> None:
        card = layout(varset())[0]
        self.assertEqual([v["label"] for v in card["variables"]],
                         ["BaseLength",
                          "SpindleClearanceHeightAboveTheSpoilboard",
                          "RailCount"])
        self.assertEqual(card["items"], [])
        self.assertTrue(card["editable"])

    def test_each_variable_carries_its_tooltip_and_type(self) -> None:
        first = layout(varset())[0]["variables"][0]
        self.assertEqual((first["tip"], first["typeLabel"]),
                         ("Across the frame", "Length"))

    def test_built_in_properties_stay_under_everything_else(self) -> None:
        rest = [g for g in layout(varset())[1:]]
        shown = [i["name"] for g in rest for i in g["items"]]
        self.assertEqual(sorted(shown), ["Label", "Label2"])

    def test_an_empty_varset_still_offers_to_add(self) -> None:
        card = layout(VarSet())[0]
        self.assertEqual((card["variables"], card["editable"]), ([], True))

    def test_two_varsets_share_values_but_not_names(self) -> None:
        card = layout(varset("A"), varset("B"))[0]
        self.assertEqual(len(card["variables"]), 3)
        self.assertFalse(card["editable"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
