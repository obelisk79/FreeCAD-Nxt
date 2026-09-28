"""Where floating fields go beside their targets in the 3D view.

Locks down the rules in placement.py - beside, never on top; inside the
view; never overlapping each other - so that adding more fields cannot
quietly break the first.

Run with: python3 tests/test_placement.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from freecad.nxt.tree.placement import (  # noqa: E402
    GAP,
    Rect,
    beside,
    bounding,
    from_viewport,
    layout,
)

VIEW = Rect(0, 0, 800, 600)
W, H = 120, 26


class BesideTests(unittest.TestCase):

    def test_to_the_right_centred_on_the_target(self) -> None:
        arrow = Rect(300, 200, 20, 100)
        spot = beside(arrow, W, H, VIEW)
        self.assertEqual(spot.x, arrow.right + GAP)
        self.assertEqual(spot.centre_y, arrow.centre_y)
        self.assertFalse(spot.overlaps(arrow))

    def test_it_follows_the_target(self) -> None:
        # The arrow moves up the screen as it is dragged: so does the box.
        before = beside(Rect(300, 300, 20, 100), W, H, VIEW)
        after = beside(Rect(300, 250, 20, 100), W, H, VIEW)
        self.assertEqual(after.y - before.y, -50)
        self.assertEqual(after.x, before.x)

    def test_to_the_left_when_the_right_is_out_of_view(self) -> None:
        arrow = Rect(740, 200, 20, 100)
        spot = beside(arrow, W, H, VIEW)
        self.assertEqual(spot.right, arrow.x - GAP)

    def test_kept_inside_the_view(self) -> None:
        for arrow in (Rect(-50, -80, 20, 40), Rect(300, 590, 20, 100),
                      Rect(300, -200, 20, 100)):
            spot = beside(arrow, W, H, VIEW)
            self.assertGreaterEqual(spot.x, VIEW.x)
            self.assertGreaterEqual(spot.y, VIEW.y)
            self.assertLessEqual(spot.right, VIEW.right)
            self.assertLessEqual(spot.bottom, VIEW.bottom)

    def test_clear_of_what_is_already_placed(self) -> None:
        arrow = Rect(300, 200, 20, 100)
        first = beside(arrow, W, H, VIEW)
        second = beside(arrow, W, H, VIEW, [first])
        self.assertFalse(second.overlaps(first))


class LayoutTests(unittest.TestCase):

    def test_several_fields_never_overlap(self) -> None:
        # A two-sided pad: two arrows on one axis, close together.
        arrows = [Rect(300, 150, 20, 100), Rect(300, 260, 20, 100),
                  Rect(305, 200, 20, 80)]
        placed = layout(arrows, [(W, H)] * 3, VIEW)
        for i, a in enumerate(placed):
            for b in placed[i + 1:]:
                self.assertFalse(a.overlaps(b))
            for arrow in arrows:
                self.assertFalse(a.overlaps(arrow))

    def test_the_same_targets_give_the_same_layout(self) -> None:
        arrows = [Rect(300, 150, 20, 100), Rect(310, 170, 20, 100)]
        self.assertEqual(layout(arrows, [(W, H)] * 2, VIEW),
                         layout(arrows, [(W, H)] * 2, VIEW))

    def test_one_field_is_placed_as_beside_places_it(self) -> None:
        arrow = Rect(300, 200, 20, 100)
        self.assertEqual(layout([arrow], [(W, H)], VIEW)[0].x,
                         beside(arrow, W, H, VIEW).x)


class ViewportTests(unittest.TestCase):
    """FreeCAD's viewport points are bottom-up; widgets are top-down."""

    def test_the_bottom_of_the_view_is_the_bottom_of_the_widget(self):
        self.assertEqual(from_viewport(10, 0, 600), (10, 600))
        self.assertEqual(from_viewport(10, 600, 600), (10, 0))

    def test_up_in_the_view_is_up_on_screen(self) -> None:
        # An arrow dragged up the screen: FreeCAD's y grows, Qt's shrinks.
        _, low = from_viewport(300, 200, 600)
        _, high = from_viewport(300, 260, 600)
        self.assertLess(high, low)

    def test_device_pixels_become_logical_pixels(self) -> None:
        self.assertEqual(from_viewport(400, 1000, 1200, ratio=2.0),
                         (200, 100))


class BoundingTests(unittest.TestCase):

    def test_projected_corners(self) -> None:
        corners = [(310, 120), (330, 120), (310, 220), (330, 220),
                   (312, 118), (328, 222)]
        self.assertEqual(bounding(corners), Rect(310, 118, 20, 104))
        self.assertIsNone(bounding([]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
