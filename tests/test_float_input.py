"""The value field that floats beside a drag arrow in the 3D view.

Checks the field mirrors and types into a task panel spin box, and that
its QML loads and commits on Enter and restores on Escape.
Run with: python3 tests/test_float_input.py   (needs PySide6)
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

from PySide6 import QtCore, QtGui, QtQuick, QtWidgets  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

App = types.ModuleType("FreeCAD")
App.Console = types.SimpleNamespace(PrintError=lambda _m: None,
                                    PrintWarning=lambda _m: None,
                                    PrintLog=lambda _m: None)


class Quantity:
    """FreeCAD's quantity parser, for the few forms the tests use."""

    UNITS = {"": 1.0, "mm": 1.0, "cm": 10.0, "in": 25.4, "deg": 1.0}

    def __init__(self, text: str) -> None:
        number, _, unit = text.strip().partition(" ")
        if unit.strip() not in self.UNITS:
            raise ValueError(text)
        self.Value = float(number) * self.UNITS[unit.strip()]


App.Units = types.SimpleNamespace(Quantity=Quantity)
App.ParamGet = lambda _g: types.SimpleNamespace(
    GetBool=lambda _k, d: d, GetInt=lambda _k, d: d,
    GetFloat=lambda _k, d: d, GetString=lambda _k, d: d)
sys.modules.setdefault("FreeCAD", App)
sys.modules["FreeCAD"].Units = App.Units
sys.modules["FreeCAD"].Console = App.Console
sys.modules.setdefault("FreeCADGui", types.ModuleType("FreeCADGui"))

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

from freecad.nxt.tree import float_input  # noqa: E402
from freecad.nxt.tree.theme import Theme  # noqa: E402

QML = ROOT / "freecad" / "nxt" / "resources" / "qml" / "FloatingValue.qml"
QML_PROBLEMS: list[str] = []


def _handler(_mode: Any, _context: Any, message: str) -> None:
    if "error" in message.lower() or "cannot" in message.lower():
        QML_PROBLEMS.append(message)


QtCore.qInstallMessageHandler(_handler)


def settle(ms: int = 80) -> None:
    end = QtCore.QTime.currentTime().addMSecs(ms)
    while QtCore.QTime.currentTime() < end:
        APP.processEvents()


class QuantitySpin(QtWidgets.QDoubleSpinBox):
    """Gui::QuantitySpinBox's rawValue: what setting a value goes through."""

    def _raw(self) -> float:
        return self.value()

    def _set_raw(self, value: float) -> None:
        self.setValue(value)

    rawValue = QtCore.Property(float, _raw, _set_raw)


def spin_box(value: float = 50) -> QuantitySpin:
    spin = QuantitySpin()
    spin.setObjectName("lengthEdit")
    spin.setRange(0, 1000)
    spin.setValue(value)
    return spin


class Pad:
    Name = "Pad"

    def __init__(self) -> None:
        self.Length = types.SimpleNamespace(Value=50.0)


class FieldTests(unittest.TestCase):

    def setUp(self) -> None:
        self.spin = spin_box()
        self.pad = Pad()
        self.field = float_input.Field()
        self.field.bind(self.spin, "Length", self.pad)

    def test_a_value_sets_the_panel_and_the_feature(self) -> None:
        self.field.commit("75")
        self.assertEqual(self.spin.value(), 75)
        self.assertEqual(self.pad.Length, 75)

    def test_units_are_converted(self) -> None:
        self.field.commit("2 in")
        self.assertAlmostEqual(self.spin.value(), 50.8)

    def test_nonsense_changes_nothing(self) -> None:
        committed: list[bool] = []
        self.field.committed.connect(lambda: committed.append(True))
        self.field.commit("abc")
        self.assertEqual(self.spin.value(), 50)
        self.assertEqual(committed, [])

    def test_after_enter_nothing_more_is_set(self) -> None:
        self.field.finish("75")
        self.assertEqual(self.spin.value(), 75)
        self.field.commit("90")         # the box losing the keyboard
        self.assertEqual(self.spin.value(), 75)

    def test_a_closed_task_is_left_alone(self) -> None:
        # OK closed the task and deleted its field: no error, nothing set.
        import shiboken6
        committed: list[bool] = []
        self.field.committed.connect(lambda: committed.append(True))
        shiboken6.delete(self.spin)
        self.field.commit("90")
        self.field.sync()
        self.assertEqual(committed, [])

    def test_the_wheel_only_says_what_the_value_would_be(self) -> None:
        done: list[bool] = []
        self.field.committed.connect(lambda: done.append(True))
        start = self.spin._raw()
        step = self.spin.singleStep()
        self.assertEqual(self.field.stepped(2),
                         "%.2f" % (start + 2 * step))
        self.assertEqual(self.field.stepped(-3),
                         "%.2f" % (start - 3 * step))
        # Nothing was set, and nothing recomputed.
        self.assertEqual((self.spin._raw(), done), (start, []))

    def test_it_is_written_as_the_panel_writes_it(self) -> None:
        self.spin.setSuffix(" mm")
        self.assertEqual(self.field.stepped(1), "51.00 mm")

    def test_it_stays_within_the_fields_limits(self) -> None:
        self.assertEqual(self.field.stepped(-500), "0.00")
        self.assertEqual(self.field.stepped(5000), "1000.00")

    def test_it_shows_the_panels_value(self) -> None:
        self.assertEqual(self.field.text, self.spin.text())
        self.assertEqual(self.field.label, "Length")

    def test_it_follows_the_panel(self) -> None:
        self.spin.setValue(12.5)
        self.field.sync()
        self.assertEqual(self.field.text, self.spin.text())


class FocusClaimTests(unittest.TestCase):
    """The box asks for the keyboard until it has it, briefly."""

    def test_asks_again_until_it_has_the_keyboard(self) -> None:
        claim = float_input.FocusClaim()
        claim.start(0.0)
        self.assertTrue(claim.wanted(0.0, False))
        # The task panel took the keyboard back: ask again.
        self.assertTrue(claim.wanted(0.3, False))
        self.assertFalse(claim.wanted(0.4, True))

    def test_once_held_a_click_elsewhere_wins(self) -> None:
        claim = float_input.FocusClaim()
        claim.start(0.0)
        claim.wanted(0.1, True)
        self.assertFalse(claim.wanted(0.2, False))

    def test_gives_up_after_a_while(self) -> None:
        claim = float_input.FocusClaim()
        claim.start(0.0)
        self.assertFalse(claim.wanted(claim.WINDOW + 0.1, False))

    def test_a_new_edit_claims_again(self) -> None:
        claim = float_input.FocusClaim()
        claim.start(0.0)
        claim.wanted(0.1, True)
        claim.start(5.0)
        self.assertTrue(claim.wanted(5.1, False))


class PairTests(unittest.TestCase):
    """Which handle gets a box for which task field."""

    L, R = float_input.LINEAR, float_input.ROTATION

    def pair(self, showing: dict[str, list[bool]],
             fields: str, kind: str = "PartDesign::Pad") -> list[str]:
        return [name for _k, _p, name
                in float_input.pair(kind, showing, fields.split())]

    def test_one_length(self) -> None:
        self.assertEqual(self.pair(
            {self.L: [True, False], self.R: [False, False]},
            "lengthEdit offset"), ["lengthEdit"])

    def test_two_lengths_each_get_their_own(self) -> None:
        self.assertEqual(self.pair(
            {self.L: [True, True]}, "lengthEdit lengthEdit2"),
            ["lengthEdit", "lengthEdit2"])

    def test_tapers_follow_the_lengths(self) -> None:
        self.assertEqual(self.pair(
            {self.L: [True, True], self.R: [True, True]},
            "lengthEdit lengthEdit2 taperEdit taperEdit2"),
            ["lengthEdit", "lengthEdit2", "taperEdit", "taperEdit2"])

    def test_a_handle_without_its_field_gets_no_box(self) -> None:
        self.assertEqual(self.pair(
            {self.L: [True, True], self.R: [True, False]},
            "lengthEdit taperEdit2"), ["lengthEdit"])

    def test_a_revolution_pairs_its_angles(self) -> None:
        self.assertEqual(self.pair(
            {self.R: [True, True]}, "revolveAngle revolveAngle2",
            "PartDesign::Revolution"), ["revolveAngle", "revolveAngle2"])

    def test_an_unknown_feature_pairs_nothing(self) -> None:
        self.assertEqual(self.pair(
            {self.L: [True]}, "lengthEdit", "PartDesign::Hole"), [])

    def test_extra_handles_are_ignored(self) -> None:
        self.assertEqual(self.pair(
            {self.L: [True, True, True]}, "lengthEdit lengthEdit2"),
            ["lengthEdit", "lengthEdit2"])

    def test_tab_goes_round_the_boxes(self) -> None:
        order = ["lengthEdit", "lengthEdit2", "taperEdit"]
        step = float_input.next_box
        self.assertEqual(step(order, "lengthEdit"), "lengthEdit2")
        self.assertEqual(step(order, "taperEdit"), "lengthEdit")
        self.assertEqual(step(order, "lengthEdit", True), "taperEdit")
        self.assertEqual(step(["lengthEdit"], "lengthEdit"), "lengthEdit")
        self.assertEqual(step(order, "gone"), "lengthEdit")

    def test_tab_hands_the_keyboard_to_the_next_box(self) -> None:
        floating = float_input.FloatingInput()
        first, second = floating._box("lengthEdit"), floating._box(
            "lengthEdit2")
        floating._order = ["lengthEdit", "lengthEdit2"]
        asked: list[str] = []
        first.field.focusRequested.connect(lambda _s: asked.append("1"))
        second.field.focusRequested.connect(lambda _s: asked.append("2"))
        first.field.tab(False)
        second.field.tab(False)
        first.field.tab(True)
        self.assertEqual(asked, ["2", "1", "2"])

    def test_labels_tell_the_boxes_apart(self) -> None:
        self.assertEqual(
            [float_input.label_for(n) for n in (
                "lengthEdit", "lengthEdit2", "taperEdit", "taperEdit2",
                "revolveAngle")],
            ["Length", "Length 2", "Taper", "Taper 2", "Angle"])


class DeletedWidgetTests(unittest.TestCase):
    """The box's widget can be deleted under it, with its 3D view.

    Its view closed or switched: the timer must shrug that off, not
    raise every tick.
    """

    def test_a_deleted_box_is_forgotten_quietly(self) -> None:
        import shiboken6
        floating = float_input.FloatingInput()
        box = floating._box("lengthEdit")
        box.widget = QtWidgets.QWidget()
        floating._viewport = QtWidgets.QWidget()
        shiboken6.delete(box.widget)
        floating._update = lambda: False    # no edit going on
        floating._tick()
        self.assertIsNone(box.widget)
        floating._tick()                    # and again: still quiet
        floating._take_keyboard("lengthEdit")
        floating.remove()


class ShortcutTests(unittest.TestCase):

    def test_freecads_shortcuts_wait_while_the_box_is_typed_in(self) -> None:
        floating = float_input.FloatingInput()
        widget = QtWidgets.QLineEdit()
        widget.show()
        floating._box("lengthEdit").widget = widget
        override = QtGui.QKeyEvent(QtCore.QEvent.Type.ShortcutOverride,
                                   QtCore.Qt.Key.Key_V,
                                   QtCore.Qt.KeyboardModifier.NoModifier)
        override.ignore()
        widget.setFocus()
        settle()
        if widget.hasFocus():
            floating.eventFilter(widget, override)
            self.assertTrue(override.isAccepted())
        other = QtWidgets.QLineEdit()
        override.ignore()
        floating.eventFilter(other, override)
        self.assertFalse(override.isAccepted())


class TabKeyTests(unittest.TestCase):
    """Tab is taken at the widget, before Qt's focus chain has it."""

    def press(self, key: Any, modifiers: Any = None) -> tuple[bool, list]:
        floating = float_input.FloatingInput()
        widget = QtWidgets.QLineEdit()
        floating._box("lengthEdit").widget = widget
        sent: list[bool] = []
        floating._send_tab = lambda _w, back: sent.append(back)
        event = QtGui.QKeyEvent(
            QtCore.QEvent.Type.KeyPress, key,
            modifiers or QtCore.Qt.KeyboardModifier.NoModifier)
        return floating.eventFilter(widget, event), sent

    def test_tab_is_taken_and_goes_forward(self) -> None:
        self.assertEqual(self.press(QtCore.Qt.Key.Key_Tab), (True, [False]))

    def test_shift_tab_goes_back_however_it_arrives(self) -> None:
        shift = QtCore.Qt.KeyboardModifier.ShiftModifier
        self.assertEqual(self.press(QtCore.Qt.Key.Key_Backtab, shift),
                         (True, [True]))
        self.assertEqual(self.press(QtCore.Qt.Key.Key_Tab, shift),
                         (True, [True]))

    def test_the_wheel_is_kept_from_the_view_underneath(self) -> None:
        floating = float_input.FloatingInput()
        widget = QtWidgets.QLineEdit()
        floating._box("lengthEdit").widget = widget
        turned: list[tuple[int, bool]] = []
        floating._send_wheel = lambda _w, a, t: turned.append((a, t))

        def wheel(modifiers: Any) -> QtGui.QWheelEvent:
            return QtGui.QWheelEvent(
                QtCore.QPointF(5, 5), QtCore.QPointF(5, 5), QtCore.QPoint(),
                QtCore.QPoint(0, -120), QtCore.Qt.MouseButton.NoButton,
                modifiers, QtCore.Qt.ScrollPhase.NoScrollPhase, False)

        plain = wheel(QtCore.Qt.KeyboardModifier.NoModifier)
        plain.ignore()
        self.assertTrue(floating.eventFilter(widget, plain))
        self.assertTrue(plain.isAccepted())
        self.assertTrue(floating.eventFilter(
            widget, wheel(QtCore.Qt.KeyboardModifier.ControlModifier)))
        self.assertEqual(turned, [(-120, False), (-120, True)])
        # Another widget's wheel is its own.
        self.assertFalse(floating.eventFilter(QtWidgets.QLineEdit(), plain))

    def test_other_keys_pass(self) -> None:
        self.assertEqual(self.press(QtCore.Qt.Key.Key_A), (False, []))

    def test_another_widgets_tab_is_left_alone(self) -> None:
        floating = float_input.FloatingInput()
        event = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress,
                                QtCore.Qt.Key.Key_Tab,
                                QtCore.Qt.KeyboardModifier.NoModifier)
        self.assertFalse(floating.eventFilter(QtWidgets.QLineEdit(), event))


class QmlTests(unittest.TestCase):

    def setUp(self) -> None:
        self.spin = spin_box()
        self.field = float_input.Field()
        self.field.bind(self.spin, "Length")
        self.problems: list[str] = []
        self.view = QtQuick.QQuickView()
        self.view.rootContext().setContextProperty("field", self.field)
        self.theme = Theme()
        self.view.rootContext().setContextProperty("theme", self.theme)
        self.view.setSource(QtCore.QUrl.fromLocalFile(str(QML)))
        self.problems += [e.toString() for e in self.view.errors()]
        self.view.show()
        settle()
        self.input = next(
            i for i in self.items(self.view.rootObject())
            if i.metaObject().className().startswith("QQuickTextInput"))

    def tearDown(self) -> None:
        # The view goes first: its bindings read `field` and `theme`.
        self.view.setSource(QtCore.QUrl())
        del self.view
        self.assertEqual(QML_PROBLEMS, [])

    def items(self, item: Any) -> list[Any]:
        out, stack = [], [item]
        while stack:
            current = stack.pop()
            out.append(current)
            stack.extend(current.childItems())
        return out

    def test_it_loads_and_shows_the_value(self) -> None:
        self.assertEqual(self.problems, [])
        self.assertEqual(self.input.property("text"), self.spin.text())

    def test_an_edit_starts_with_the_value_selected(self) -> None:
        self.field.focusRequested.emit(True)
        settle()
        self.assertTrue(self.input.property("activeFocus"))
        self.assertEqual(self.input.property("selectedText"),
                         self.input.property("text"))

    def test_a_double_click_selects_the_value_to_type_over(self) -> None:
        grabbed: list[bool] = []
        self.field.grabbed.connect(lambda: grabbed.append(True))
        root = self.view.rootObject()
        centre = QtCore.QPoint(int(root.property("width") * 0.8),
                               int(root.property("height") / 2))
        QTest.mouseDClick(self.view, QtCore.Qt.MouseButton.LeftButton,
                          QtCore.Qt.KeyboardModifier.NoModifier, centre)
        settle()
        self.assertTrue(grabbed)
        self.assertTrue(self.input.property("activeFocus"))
        self.assertEqual(self.input.property("selectedText"),
                         self.input.property("text"))

    def test_losing_the_keyboard_keeps_the_value(self) -> None:
        committed: list[bool] = []
        self.field.committed.connect(lambda: committed.append(True))
        self.input.forceActiveFocus()
        self.input.setProperty("text", "64")
        self.input.setProperty("focus", False)
        self.view.rootObject().forceActiveFocus()
        settle()
        self.assertEqual(self.spin.value(), 64)
        self.assertTrue(committed)

    def test_losing_the_keyboard_unchanged_does_nothing(self) -> None:
        committed: list[bool] = []
        self.field.committed.connect(lambda: committed.append(True))
        self.input.forceActiveFocus()
        self.view.rootObject().forceActiveFocus()
        settle()
        self.assertEqual(committed, [])

    def test_tab_keeps_the_value_and_moves_on(self) -> None:
        tabbed: list[bool] = []
        self.field.tabbed.connect(tabbed.append)
        self.field.focusRequested.emit(True)
        settle()
        self.input.setProperty("text", "80")
        QTest.keyClick(self.view, QtCore.Qt.Key.Key_Tab)
        settle()
        self.assertEqual(self.spin._raw(), 80)
        QTest.keyClick(self.view, QtCore.Qt.Key.Key_Backtab,
                       QtCore.Qt.KeyboardModifier.ShiftModifier)
        settle()
        self.assertEqual(tabbed, [False, True])
        # And as the widget hands it over.
        QtCore.QMetaObject.invokeMethod(
            self.view.rootObject(), "tab",
            QtCore.Qt.ConnectionType.DirectConnection,
            QtCore.Q_ARG("QVariant", False))
        self.assertEqual(tabbed, [False, True, False])

    def test_the_wheel_shows_at_once_and_sets_when_it_rests(self) -> None:
        start = self.spin._raw()
        root = self.view.rootObject()
        centre = QtCore.QPointF(root.property("width") / 2,
                                root.property("height") / 2)
        wheel = QtGui.QWheelEvent(
            centre, self.view.mapToGlobal(centre.toPoint()),
            QtCore.QPoint(), QtCore.QPoint(0, 240),
            QtCore.Qt.MouseButton.NoButton,
            QtCore.Qt.KeyboardModifier.NoModifier,
            QtCore.Qt.ScrollPhase.NoScrollPhase, False)
        QtCore.QCoreApplication.sendEvent(self.view, wheel)
        settle(40)
        want = start + 2 * self.spin.singleStep()
        self.assertEqual(float(self.input.property("text")), want)
        self.assertEqual(self.spin._raw(), start)       # not yet
        settle(600)
        self.assertEqual(self.spin._raw(), want)
        self.assertEqual(self.input.property("text"), self.spin.text())

    def test_enter_commits_and_escape_restores(self) -> None:
        finished: list[bool] = []
        self.field.finished.connect(lambda: finished.append(True))
        self.input.forceActiveFocus()
        self.input.setProperty("text", "80")
        QTest.keyClick(self.view, QtCore.Qt.Key.Key_Return)
        settle()
        self.assertEqual(self.spin.value(), 80)
        self.assertTrue(finished, "Enter closes the edit")
        self.assertTrue(self.field.released)
        self.field.sync()
        self.input.forceActiveFocus()
        self.input.setProperty("text", "999")
        QTest.keyClick(self.view, QtCore.Qt.Key.Key_Escape)
        settle()
        self.assertEqual(self.input.property("text"), self.field.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
