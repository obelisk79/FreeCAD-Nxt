"""The drag guard: a 3D view gets the releases it never saw (issue #194).

Run with: python3 tests/test_drag_guard.py
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
sys.path.insert(0, str(ROOT / "tests"))


import fakes  # noqa: E402
from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
App, Gui = fakes.install()

from freecad.nxt.tools import drag_guard  # noqa: E402

Type = QtCore.QEvent.Type
Button = QtCore.Qt.MouseButton
LEFT, RIGHT, MIDDLE = (Button.LeftButton, Button.RightButton,
                       Button.MiddleButton)
NONE = Button.NoButton


class Viewport(QtWidgets.QWidget):
    """Records the button events that reach it, as Quarter would."""

    def __init__(self) -> None:
        super().__init__()
        self.seen: list[tuple[str, Any]] = []

    def event(self, e: Any) -> bool:  # noqa: N802
        names = {Type.MouseButtonPress: "press",
                 Type.MouseButtonRelease: "release"}
        if e.type() in names:
            self.seen.append((names[e.type()], e.button()))
        return super().event(e)


def send(widget: Any, kind: Any, button: Any, held: Any) -> None:
    point = QtCore.QPointF(10, 10)
    QtWidgets.QApplication.sendEvent(widget, QtGui.QMouseEvent(
        kind, point, point, button, held,
        QtCore.Qt.KeyboardModifier.NoModifier))


class LostReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.view = Viewport()
        self.other = QtWidgets.QWidget()
        self.guard = drag_guard.StaleDragGuard()
        self.guard._viewport = self.view  # as after a press in the view
        drag_guard.fc.active_view = lambda: None  # type: ignore
        self.guard.install()

    def tearDown(self) -> None:
        self.guard.remove()

    def test_right_drag_after_lost_left_release(self) -> None:
        send(self.view, Type.MouseButtonPress, LEFT, LEFT)
        # The release goes to another widget, as on X11 in the report.
        send(self.other, Type.MouseButtonRelease, LEFT, NONE)
        self.view.seen.clear()
        send(self.view, Type.MouseButtonPress, RIGHT, RIGHT)
        self.assertEqual(self.view.seen,
                         [("release", LEFT), ("press", RIGHT)])

    def test_idle_move_settles_a_lost_middle_release(self) -> None:
        send(self.view, Type.MouseButtonPress, MIDDLE, MIDDLE)
        self.view.seen.clear()
        send(self.view, Type.MouseMove, NONE, NONE)
        self.assertEqual(self.view.seen, [("release", MIDDLE)])
        send(self.view, Type.MouseMove, NONE, NONE)
        self.assertEqual(len(self.view.seen), 1)

    def test_second_press_of_a_button_still_down(self) -> None:
        send(self.view, Type.MouseButtonPress, LEFT, LEFT)
        self.view.seen.clear()
        send(self.view, Type.MouseButtonPress, LEFT, LEFT)
        self.assertEqual(self.view.seen,
                         [("release", LEFT), ("press", LEFT)])

    def test_normal_clicks_and_chords_untouched(self) -> None:
        send(self.view, Type.MouseButtonPress, LEFT, LEFT)
        send(self.view, Type.MouseMove, NONE, LEFT)
        send(self.view, Type.MouseButtonPress, RIGHT, LEFT | RIGHT)
        send(self.view, Type.MouseButtonRelease, RIGHT, LEFT)
        send(self.view, Type.MouseButtonRelease, LEFT, NONE)
        send(self.view, Type.MouseMove, NONE, NONE)
        self.assertEqual(self.view.seen, [
            ("press", LEFT), ("press", RIGHT),
            ("release", RIGHT), ("release", LEFT)])


if __name__ == "__main__":
    unittest.main()
