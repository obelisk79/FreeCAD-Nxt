"""Inspector edits to a feature in edit go through its task panel's fields.

Run with: python3 tests/test_task_sync.py   (needs PySide6)
"""

from __future__ import annotations

import os
import sys
import types
import unittest
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fakes  # noqa: E402
from PySide6 import QtCore, QtWidgets  # noqa: E402

App, Gui = fakes.install()

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

from freecad.nxt.tools import task_sync  # noqa: E402

TYPES = ["Length", "UpToLast", "UpToFirst", "UpToFace", "TwoLengths",
         "UpToShape"]
SIDES = ["One side", "Two sides", "Symmetric"]


class Quantity:
    def __init__(self, text: str) -> None:
        number, _, unit = text.partition(" ")
        self.Value = float(number) * (10.0 if unit == "cm" else 1.0)


class Pad:
    TypeId = "PartDesign::Pad"
    Name = "Pad"
    Document = types.SimpleNamespace(Name="Doc")

    def getEnumerationsOfProperty(self, prop: str) -> list[str]:  # noqa: N802
        if prop == "StartType":
            return ["Profile plane", "Offset", "Reference"]
        return SIDES if prop == "SideType" else TYPES


class Spin(QtWidgets.QWidget):
    """Stands in for Gui::QuantitySpinBox: a rawValue property."""

    def __init__(self, parent: Any) -> None:
        super().__init__(parent)
        self.setProperty("rawValue", 0.0)


class TaskTests(unittest.TestCase):

    def setUp(self) -> None:
        self.pad = Pad()
        self.main = QtWidgets.QWidget()
        self.sides = QtWidgets.QComboBox(self.main)
        self.sides.setObjectName("sidesMode")
        self.sides.addItems(["One sided", "Two sided", "Symmetric"])
        self.mode = QtWidgets.QComboBox(self.main)
        self.mode.setObjectName("changeMode")
        self.mode.addItems(["Dimension", "To last", "To first",
                            "Up to face", "Up to shape"])
        self.reversed = QtWidgets.QCheckBox(self.main)
        self.reversed.setObjectName("checkBoxReversed")
        self.length = Spin(self.main)
        self.length.setObjectName("lengthEdit")
        self.changed: list[int] = []
        self.sides.currentIndexChanged.connect(self.changed.append)
        App.Units = types.SimpleNamespace(Quantity=Quantity)
        Gui.getMainWindow = lambda: self.main
        self.editing: Any = self.pad
        Gui.getDocument = lambda _n: types.SimpleNamespace(
            getInEdit=lambda: types.SimpleNamespace(Object=self.editing))
        Gui.Control = types.SimpleNamespace(activeDialog=lambda: True)

    def test_a_choice_is_made_in_the_panels_box(self) -> None:
        self.assertTrue(task_sync.set_in_task([self.pad], "SideType",
                                              "Two sides"))
        self.assertEqual(self.sides.currentIndex(), 1)
        self.assertEqual(self.changed, [1])     # the panel's handler ran

    def test_type_skips_the_value_its_box_does_not_list(self) -> None:
        task_sync.set_in_task([self.pad], "Type", "UpToShape")
        self.assertEqual(self.mode.currentText(), "Up to shape")
        self.assertFalse(task_sync.set_in_task([self.pad], "Type",
                                               "TwoLengths"))

    def test_a_length_keeps_the_fields_unit(self) -> None:
        self.assertTrue(task_sync.set_in_task([self.pad], "Length",
                                              "2", "cm"))
        self.assertEqual(self.length.property("rawValue"), 20.0)

    def test_a_number_replaces_the_fields_expression(self) -> None:
        self.pad.ExpressionEngine = [("Length", "VarSet.depth")]
        cleared: list[Any] = []
        self.pad.setExpression = lambda p, e: cleared.append((p, e))
        bound: list[Any] = []

        class Binding:
            def __init__(self, widget: Any) -> None:
                self.widget = widget

            def bind(self, obj: Any, prop: str) -> None:
                bound.append((self.widget, obj, prop))

        Gui.ExpressionBinding = Binding
        self.assertTrue(task_sync.set_in_task([self.pad], "Length", "3",
                                              "mm"))
        self.assertEqual(cleared, [("Length", None)])
        self.assertEqual(bound, [(self.length, self.pad, "Length")])
        self.assertEqual(self.length.property("rawValue"), 3.0)

    def test_a_check_box(self) -> None:
        task_sync.set_in_task([self.pad], "Reversed", True)
        self.assertTrue(self.reversed.isChecked())

    def direction_fields(self) -> tuple[Any, list[Any]]:
        """The Pad panel's direction list and its x, y and z fields."""
        listed = QtWidgets.QComboBox(self.main)
        listed.setObjectName("directionCB")
        listed.addItems(["Sketch normal", "Select reference…",
                         "Custom direction"])
        fields = []
        for name in ("XDirectionEdit", "YDirectionEdit", "ZDirectionEdit"):
            field = QtWidgets.QDoubleSpinBox(self.main)
            field.setRange(-1e9, 1e9)
            field.setObjectName(name)
            fields.append(field)
        return listed, fields

    def test_a_custom_direction_is_chosen_in_the_panels_list(self) -> None:
        listed, _fields = self.direction_fields()
        chosen: list[int] = []
        listed.activated.connect(chosen.append)
        self.assertTrue(task_sync.set_in_task([self.pad], "UseCustomVector",
                                              True))
        self.assertEqual((listed.currentIndex(), chosen), (2, [2]))
        task_sync.set_in_task([self.pad], "UseCustomVector", False)
        self.assertEqual(listed.currentIndex(), 0)

    def test_a_reference_is_an_item_of_the_panels_list(self) -> None:
        listed, _fields = self.direction_fields()
        self.assertTrue(task_sync.set_in_task([self.pad], "ReferenceAxis",
                                              "Select reference…"))
        self.assertEqual(listed.currentIndex(), 1)

    def test_a_directions_components_go_to_its_fields(self) -> None:
        _listed, fields = self.direction_fields()
        self.pad.ExpressionEngine = []
        self.assertTrue(task_sync.set_parts_in_task(
            [self.pad], "Direction", [("x", "1"), ("z", "0.5")]))
        self.assertEqual([f.value() for f in fields], [1.0, 0.0, 0.5])

    def test_a_component_takes_an_expression_or_drops_one(self) -> None:
        _listed, fields = self.direction_fields()
        expressions: list[Any] = []
        self.pad.setExpression = lambda p, e: expressions.append((p, e))
        self.pad.evalExpression = lambda _e: 2.0
        bound: list[Any] = []

        class Binding:
            def __init__(self, widget: Any) -> None:
                self.widget = widget

            def bind(self, _obj: Any, path: str) -> None:
                bound.append((self.widget, path))

        Gui.ExpressionBinding = Binding
        self.pad.ExpressionEngine = []
        self.assertTrue(task_sync.set_parts_in_task(
            [self.pad], "Direction", [("y", "=Length / 5")]))
        self.assertEqual(expressions, [("Direction.y", "Length / 5")])
        self.assertEqual(bound, [(fields[1], "Direction.y")])
        self.assertEqual(fields[1].value(), 2.0)
        # FreeCAD keeps a component's path with a leading dot.
        self.pad.ExpressionEngine = [(".Direction.y", "Length / 5")]
        task_sync.set_parts_in_task([self.pad], "Direction", [("y", "0")])
        self.assertEqual(expressions[-1], ("Direction.y", None))
        self.assertEqual(fields[1].value(), 0.0)

    def test_a_new_edit_starts_at_an_offset(self) -> None:
        start = QtWidgets.QComboBox(self.main)
        start.setObjectName("startMode")
        start.addItems(["Profile plane", "Offset", "Reference"])
        self.pad.StartType = "Profile plane"
        self.assertTrue(task_sync.start_with_offset(self.pad))
        self.assertEqual(start.currentIndex(), 1)
        self.pad.StartType = "Reference"
        self.assertFalse(task_sync.wants_offset_start(self.pad))

    def face_field(self) -> tuple[Any, Any]:
        line = QtWidgets.QLineEdit(self.main)
        line.setObjectName("lineFaceName")
        button = QtWidgets.QToolButton(self.main)
        button.setObjectName("buttonFace")
        button.setCheckable(True)
        button.setChecked(True)         # the panel is picking a face itself
        return line, button

    def test_a_picked_face_reaches_the_panels_field(self) -> None:
        line, button = self.face_field()
        base = types.SimpleNamespace(Name="Pad001", Label="Base")
        self.pad.UpToFace = (base, ["Face6"])
        task_sync.reference_to_task(self.pad, "UpToFace")
        self.assertEqual(line.text(), "Base:Face6")
        self.assertEqual((line.property("FeatureName"),
                          line.property("FaceName")), ("Pad001", "Face6"))
        self.assertFalse(button.isChecked())

    def test_a_removed_face_empties_the_panels_field(self) -> None:
        line, _button = self.face_field()
        line.setText("Base:Face6")
        line.setProperty("FeatureName", "Pad001")
        self.pad.UpToFace = None
        task_sync.reference_to_task(self.pad, "UpToFace")
        self.assertEqual(line.text(), "")
        self.assertIsNone(line.property("FeatureName"))

    def test_the_panels_own_picking_shows_on_its_card(self) -> None:
        _line, button = self.face_field()
        groups = [{"items": [{"name": "UpToFace", "kind": "link"},
                             {"name": "Length", "kind": "quantity"}]}]
        task_sync.mark_panel_picks(groups, self.pad)
        self.assertEqual([i.get("picking") for i in groups[0]["items"]],
                         [True, None])
        task_sync.stop_panel_pick(self.pad, "UpToFace")
        self.assertFalse(button.isChecked())

    def test_references_are_picked_never_typed(self) -> None:
        self.face_field()
        self.assertTrue(task_sync.is_reference([self.pad], "UpToFace"))
        self.assertFalse(task_sync.is_reference([self.pad], "Length"))
        self.assertFalse(task_sync.set_in_task([self.pad], "UpToFace",
                                               "Pad001"))

    def test_a_primitives_size_goes_to_its_own_field(self) -> None:
        radius = Spin(self.main)
        radius.setObjectName("cylinderRadius")
        cylinder = Pad()
        cylinder.TypeId = "PartDesign::SubtractiveCylinder"
        self.editing = cylinder
        self.assertTrue(task_sync.set_in_task([cylinder], "Radius", "4",
                                              "mm"))
        self.assertEqual(radius.property("rawValue"), 4.0)

    def test_a_prisms_sides_are_a_whole_number(self) -> None:
        sides = QtWidgets.QSpinBox(self.main)
        sides.setObjectName("prismPolygon")
        prism = Pad()
        prism.TypeId = "PartDesign::AdditivePrism"
        self.editing = prism
        self.assertTrue(task_sync.set_in_task([prism], "Polygon", "8"))
        self.assertEqual(sides.value(), 8)

    def boolean(self) -> tuple[Any, Any, Any]:
        bodies = QtWidgets.QListWidget(self.main)
        bodies.setObjectName("listWidgetBodies")
        add = QtWidgets.QToolButton(self.main)
        add.setObjectName("buttonBodyAdd")
        add.setCheckable(True)
        shown = {}

        def body(name: str) -> Any:
            view = types.SimpleNamespace(Visibility=False)
            shown[name] = view
            return types.SimpleNamespace(Name=name, Label=name + " label",
                                         ViewObject=view)
        tool_a, tool_b = body("BodyA"), body("BodyB")
        doc = types.SimpleNamespace(
            Name="Doc", getObject=lambda n: {"BodyA": tool_a,
                                             "BodyB": tool_b}.get(n))
        boolean = types.SimpleNamespace(
            TypeId="PartDesign::Boolean", Name="Boolean", Document=doc,
            Group=[tool_a, tool_b])
        self.editing = boolean
        return boolean, bodies, add

    def test_the_panel_picks_a_booleans_bodies(self) -> None:
        boolean, _bodies, add = self.boolean()
        self.assertTrue(task_sync.start_panel_pick(boolean, "Group"))
        self.assertTrue(add.isChecked())
        self.assertTrue(task_sync.panel_picks(boolean, "Group"))
        self.assertFalse(task_sync.start_panel_pick(boolean, "Type"))

    def test_the_panels_list_follows_the_bodies(self) -> None:
        boolean, bodies, _add = self.boolean()
        task_sync.list_to_task(boolean, "Group")
        role = QtCore.Qt.ItemDataRole.UserRole
        self.assertEqual([bodies.item(r).data(role)
                          for r in range(bodies.count())],
                         ["BodyA", "BodyB"])
        removed = boolean.Group.pop()
        task_sync.list_to_task(boolean, "Group")
        self.assertEqual(bodies.count(), 1)
        self.assertTrue(removed.ViewObject.Visibility)

    def test_a_booleans_bodies_are_never_typed(self) -> None:
        boolean, _bodies, _add = self.boolean()
        self.assertFalse(task_sync.set_in_task([boolean], "Group", "BodyA"))

    def pattern(self) -> Any:
        pattern = Pad()
        pattern.TypeId = "PartDesign::LinearPattern"
        pattern.getEnumerationsOfProperty = lambda prop: (  # type: ignore
            ["Features", "Whole shape"] if prop == "TransformMode"
            else ["Extent", "Spacing"])
        self.editing = pattern
        return pattern

    def test_the_second_direction_has_its_own_fields(self) -> None:
        first, second = Spin(self.main), Spin(self.main)
        for spin in (first, second):
            spin.setObjectName("spinSpacing")
        pattern = self.pattern()
        self.assertTrue(task_sync.set_in_task([pattern], "Offset2", "5",
                                              "mm"))
        self.assertEqual((first.property("rawValue"),
                          second.property("rawValue")), (0.0, 5.0))

    def test_a_count_is_offset_as_uintspinbox_keeps_it(self) -> None:
        class UIntSpinBox(QtWidgets.QSpinBox):
            """As Gui::UIntSpinBox: Qt's value is the count + INT_MIN."""

        count = UIntSpinBox(self.main)
        count.setRange(task_sync.UINT_OFFSET, task_sync.UINT_OFFSET + 1000)
        count.setObjectName("spinOccurrences")
        pattern = self.pattern()
        self.assertTrue(task_sync.set_in_task([pattern], "Occurrences",
                                              "3"))
        self.assertEqual(count.value() - task_sync.UINT_OFFSET, 3)

    def test_a_path_patterns_mode_is_a_choice_made(self) -> None:
        modes = QtWidgets.QComboBox(self.main)
        modes.setObjectName("spacingMode")
        modes.addItems(["Fixed count", "Fixed spacing", "Both"])
        chosen: list[int] = []
        modes.activated.connect(chosen.append)
        path = Pad()
        path.TypeId = "PartDesign::PathPattern"
        path.getEnumerationsOfProperty = lambda _p: [  # type: ignore
            "Fixed count", "Fixed spacing", "Fixed count and spacing"]
        self.editing = path
        self.assertTrue(task_sync.set_in_task([path], "SpacingMode",
                                              "Fixed spacing"))
        self.assertEqual((modes.currentIndex(), chosen), (1, [1]))

    def test_what_a_pattern_repeats_is_a_radio_choice(self) -> None:
        body = QtWidgets.QRadioButton(self.main)
        body.setObjectName("radioTransformBody")
        tools = QtWidgets.QRadioButton(self.main)
        tools.setObjectName("radioTransformToolShapes")
        clicked: list[str] = []
        tools.clicked.connect(lambda: clicked.append("tools"))
        pattern = self.pattern()
        self.assertTrue(task_sync.set_in_task([pattern], "TransformMode",
                                              "Features"))
        self.assertTrue(tools.isChecked())
        self.assertEqual(clicked, ["tools"])
        self.assertFalse(task_sync.set_in_task([pattern], "TransformMode",
                                               "Bogus"))

    def test_the_panel_picks_a_patterns_features(self) -> None:
        listed = QtWidgets.QListWidget(self.main)
        listed.setObjectName("listWidgetFeatures")
        add = QtWidgets.QToolButton(self.main)
        add.setObjectName("buttonAddFeature")
        add.setCheckable(True)
        pattern = self.pattern()
        self.assertTrue(task_sync.start_panel_pick(pattern, "Originals"))
        self.assertTrue(add.isChecked())
        pad = types.SimpleNamespace(
            Name="Pad", Label="Boss",
            ViewObject=types.SimpleNamespace(Visibility=False))
        pattern.Originals = []
        listed.addItem("Boss")
        listed.item(0).setData(QtCore.Qt.ItemDataRole.UserRole, "Pad")
        pattern.Document = types.SimpleNamespace(Name="Doc",
                                                 getObject=lambda _n: pad)
        task_sync.list_to_task(pattern, "Originals")
        self.assertEqual(listed.count(), 0)
        self.assertFalse(pad.ViewObject.Visibility)     # never shown

    def test_left_to_the_property_otherwise(self) -> None:
        self.assertFalse(task_sync.set_in_task([self.pad], "Length",
                                               "=Sketch.Width"))
        self.assertFalse(task_sync.set_in_task([self.pad], "Refine", True))
        self.assertFalse(task_sync.set_in_task([self.pad, Pad()],
                                               "Reversed", True))
        self.editing = None
        self.assertFalse(task_sync.set_in_task([self.pad], "Reversed",
                                               True))
        self.assertFalse(self.reversed.isChecked())


if __name__ == "__main__":
    unittest.main(verbosity=2)
