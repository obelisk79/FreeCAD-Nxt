"""Nxt's overlay: which mouse events the panel keeps, and which it hands on.

The panel sits over the 3D view. A press, a wheel turn or a move is the
panel's where it draws something (NxtTree.qml wantsPoint) and the 3D
view's everywhere else. These drive ViewOverlay.eventFilter with real Qt
events and a panel whose "drawing" is a rectangle, and check where each
one ends up.

Also the 3D view background watch (theme.ViewBackgroundWatch), which
re-tunes the overlay's ink when the view's background preference changes.

Run with: python3 tests/test_view_overlay.py   (needs PySide6)
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

from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

App = types.ModuleType("FreeCAD")
App.Console = types.SimpleNamespace(PrintLog=lambda _m: None,
                                    PrintError=lambda _m: None)
sys.modules.setdefault("FreeCAD", App)
sys.modules.setdefault("FreeCADGui", types.ModuleType("FreeCADGui"))
App = sys.modules["FreeCAD"]

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

from freecad.nxt.tree import theme, view_overlay  # noqa: E402

E = QtCore.QEvent.Type
LEFT = QtCore.Qt.MouseButton.LeftButton
NONE = QtCore.Qt.MouseButton.NoButton
PLAIN = QtCore.Qt.KeyboardModifier.NoModifier

#: Where the fake panel draws something: a pill, in its coordinates.
PILL = QtCore.QRectF(0, 0, 100, 20)


class Root(QtCore.QObject):
    """The QML root: draws only the pill."""

    @QtCore.Slot("QVariant", "QVariant", result="QVariant")
    def wantsPoint(self, x: Any, y: Any) -> Any:  # noqa: N802
        return PILL.contains(QtCore.QPointF(float(x), float(y)))


class Panel(QtWidgets.QWidget):
    """Stands in for the panel's QQuickWidget."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._root = Root(self)

    def rootObject(self) -> Any:  # noqa: N802
        return self._root


class Host(QtWidgets.QWidget):
    """The 3D view's GL widget: keeps what it is sent."""

    def __init__(self) -> None:
        super().__init__()
        self.got: list[tuple[Any, QtCore.QPointF]] = []

    def event(self, event: Any) -> bool:
        if event.type() in (E.MouseButtonPress, E.MouseMove,
                            E.MouseButtonRelease):
            self.got.append((event.type(), event.position()))
        return super().event(event)


class Dock(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._release_timer = QtCore.QTimer(self)


def mouse(kind: Any, x: float, y: float, button: Any = LEFT,
          buttons: Any = None) -> QtGui.QMouseEvent:
    held = buttons if buttons is not None else (
        NONE if kind == E.MouseButtonRelease or button == NONE else button)
    point = QtCore.QPointF(x, y)
    return QtGui.QMouseEvent(kind, point, point, button, held, PLAIN)


def wheel(x: float, y: float) -> QtGui.QWheelEvent:
    point = QtCore.QPointF(x, y)
    return QtGui.QWheelEvent(point, point, QtCore.QPoint(),
                             QtCore.QPoint(0, 120), NONE, PLAIN,
                             QtCore.Qt.ScrollPhase.NoScrollPhase, False)


class OverlayTests(unittest.TestCase):

    def setUp(self) -> None:
        self.dock = Dock()
        self.host = Host()
        self.host.resize(400, 300)
        self.panel = Panel(self.host)
        self.panel.setGeometry(10, 30, 200, 200)    # offset in the view
        self.dock._view = self.panel
        self.overlay = view_overlay.ViewOverlay(self.dock)
        self.overlay._host = self.host
        self.kept: list[Any] = []
        self.overlay._deliver = lambda event: self.kept.append(event.type())
        self.scrolled: list[int] = []
        self.overlay._scroll = lambda event: self.scrolled.append(
            event.angleDelta().y())
        self.zoomed: list[int] = []
        self.overlay._pass_wheel = lambda event: self.zoomed.append(
            event.angleDelta().y())

    def send(self, event: Any, to: Any = None) -> bool:
        return self.overlay.eventFilter(to or self.panel, event)

    # -- presses -----------------------------------------------------------

    def test_a_press_on_a_pill_is_the_panels(self) -> None:
        self.assertTrue(self.send(mouse(E.MouseButtonPress, 50, 10)))
        self.assertEqual(self.kept, [E.MouseButtonPress])
        self.assertEqual(self.host.got, [])

    def test_and_so_are_its_moves_and_release(self) -> None:
        self.send(mouse(E.MouseButtonPress, 50, 10))
        # Dragged off the pill: still the panel's press.
        self.send(mouse(E.MouseMove, 150, 150, NONE, LEFT))
        self.send(mouse(E.MouseButtonRelease, 150, 150))
        self.assertEqual(self.kept, [E.MouseButtonPress, E.MouseMove,
                                     E.MouseButtonRelease])
        self.assertEqual(self.host.got, [])
        self.assertFalse(self.overlay._owning)

    def test_a_press_off_the_pills_goes_to_the_3d_view(self) -> None:
        self.assertTrue(self.send(mouse(E.MouseButtonPress, 50, 100)))
        self.assertEqual(self.kept, [])
        kind, where = self.host.got[0]
        self.assertEqual(kind, E.MouseButtonPress)
        # In the view's coordinates: the panel sits at (10, 30).
        self.assertEqual((where.x(), where.y()), (60, 130))

    def test_and_so_do_its_moves_and_release(self) -> None:
        self.send(mouse(E.MouseButtonPress, 50, 100))
        # Dragged across a pill: still the 3D view's press (orbiting).
        self.send(mouse(E.MouseMove, 50, 10, NONE, LEFT))
        self.send(mouse(E.MouseButtonRelease, 50, 10))
        self.assertEqual([k for k, _w in self.host.got],
                         [E.MouseButtonPress, E.MouseMove,
                          E.MouseButtonRelease])
        self.assertEqual(self.kept, [])
        self.assertFalse(self.overlay._passing)

    def test_a_stale_press_is_forgotten_on_a_buttonless_move(self) -> None:
        # Its release went elsewhere - to a dialog the click opened.
        self.overlay._owning = self.overlay._passing = True
        self.send(mouse(E.MouseMove, 50, 10, NONE, NONE))
        self.assertFalse(self.overlay._owning or self.overlay._passing)

    # -- the wheel ---------------------------------------------------------

    def test_the_wheel_over_a_pill_scrolls_the_list(self) -> None:
        event = wheel(50, 10)
        self.assertTrue(self.send(event))
        self.assertEqual((self.scrolled, self.zoomed), ([120], []))
        self.assertTrue(event.isAccepted())

    def test_elsewhere_it_zooms_the_model(self) -> None:
        self.assertTrue(self.send(wheel(50, 100)))
        self.assertEqual((self.scrolled, self.zoomed), ([], [120]))

    # -- falling through ---------------------------------------------------

    def transparent(self) -> bool:
        return self.panel.testAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def test_off_the_pills_the_mouse_falls_through(self) -> None:
        self.assertTrue(self.send(mouse(E.MouseMove, 50, 100, NONE, NONE)))
        self.assertTrue(self.transparent())

    def test_and_comes_back_over_a_pill(self) -> None:
        self.send(mouse(E.MouseMove, 50, 100, NONE, NONE))
        # Now the 3D view hears the moves; (60, 40) is the pill's (50, 10).
        self.send(mouse(E.MouseMove, 60, 40, NONE, NONE), to=self.host)
        self.assertFalse(self.transparent())

    def test_over_a_pill_it_stays_the_panels(self) -> None:
        self.assertFalse(self.send(mouse(E.MouseMove, 50, 10, NONE, NONE)))
        self.assertFalse(self.transparent())

    # -- the 3D view going away ---------------------------------------------

    def test_a_hidden_view_parks_the_panel(self) -> None:
        parked: list[bool] = []
        self.overlay._park = lambda: parked.append(True)
        self.send(QtCore.QEvent(E.Hide), to=self.host)
        self.assertEqual(parked, [True])

    def test_a_release_in_the_view_ends_any_press(self) -> None:
        self.overlay._owning = self.overlay._passing = True
        self.send(mouse(E.MouseButtonRelease, 5, 5), to=self.host)
        self.assertFalse(self.overlay._owning or self.overlay._passing)


class Group:
    """A FreeCAD parameter group that tells its observers of changes."""

    def __init__(self) -> None:
        self.observers: list[Any] = []

    def Attach(self, observer: Any) -> None:  # noqa: N802
        self.observers.append(observer)

    def Detach(self, observer: Any) -> None:  # noqa: N802
        self.observers.remove(observer)

    def set(self, key: str) -> None:
        for observer in list(self.observers):
            observer.OnChange(self, key)


class BackgroundWatchTests(unittest.TestCase):

    def setUp(self) -> None:
        self.group = Group()
        self.saved = getattr(App, "ParamGet", None)
        App.ParamGet = lambda _path: self.group
        self.calls = 0
        self.watch = theme.ViewBackgroundWatch(self.count)

    def tearDown(self) -> None:
        App.ParamGet = self.saved

    def count(self) -> None:
        self.calls += 1

    def test_a_background_change_calls_back(self) -> None:
        self.watch.attach()
        for key in ("Simple", "BackgroundColor", "BackgroundColor2",
                    "BackgroundColor3", "Gradient"):
            self.group.set(key)
        self.assertEqual(self.calls, 5)

    def test_other_view_settings_do_not(self) -> None:
        self.watch.attach()
        self.group.set("AntiAliasing")
        self.assertEqual(self.calls, 0)

    def test_nothing_once_detached(self) -> None:
        self.watch.attach()
        self.watch.detach()
        self.group.set("BackgroundColor")
        self.assertEqual((self.calls, self.group.observers), (0, []))


if __name__ == "__main__":
    unittest.main(verbosity=2)
