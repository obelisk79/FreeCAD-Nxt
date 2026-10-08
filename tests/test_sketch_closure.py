"""Why a profile is not closed, from its edges alone.

Run with: python3 tests/test_sketch_closure.py
"""

from __future__ import annotations

import sys
import unittest
from math import cos, hypot, radians, sin
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from freecad.nxt import sketch_closure as closure  # noqa: E402
from freecad.nxt.sketch_closure import END, START, Edge  # noqa: E402

Point = tuple[float, float]


def line(index: int, start: Point, end: Point) -> Edge:
    mid = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
    return Edge(index, start, end, mid,
                hypot(end[0] - start[0], end[1] - start[1]), straight=True)


def arc(index: int, begin: float, finish: float, radius: float = 50.0,
        centre: Point = (0.0, 0.0)) -> Edge:
    """An arc from one angle to another, in degrees, either way round."""
    def at(degrees: float) -> Point:
        return (centre[0] + radius * cos(radians(degrees)),
                centre[1] + radius * sin(radians(degrees)))
    return Edge(index, at(begin), at(finish), at((begin + finish) / 2),
                radius * abs(radians(finish - begin)), centre=centre)


def square(side: float = 100.0, gap: float = 0.0) -> list[Edge]:
    """Four lines round a square; the last stops `gap` short of the first."""
    return [line(0, (0, 0), (side, 0)), line(1, (side, 0), (side, side)),
            line(2, (side, side), (0, side)), line(3, (0, side), (0, gap))]


class ClosureTests(unittest.TestCase):

    def test_a_closed_profile_has_nothing_to_mend(self) -> None:
        self.assertTrue(closure.inspect(square()).closed())

    def test_a_near_miss_is_a_gap_between_the_two_loose_ends(self) -> None:
        found = closure.inspect(square(gap=0.5))
        self.assertEqual(found.gaps, [((0, START), (3, END))])
        self.assertEqual((found.surplus, found.open_ends), ([], 0))

    def test_a_wide_opening_is_left_alone(self) -> None:
        found = closure.inspect(square(gap=20.0))
        self.assertEqual((found.gaps, found.open_ends), ([], 2))

    def test_near_is_relative_to_the_sketch(self) -> None:
        self.assertTrue(closure.inspect(square(1000.0, gap=5.0)).gaps)
        self.assertFalse(closure.inspect(square(100.0, gap=5.0)).gaps)

    def test_an_edge_drawn_twice_is_surplus(self) -> None:
        found = closure.inspect(square() + [line(4, (100, 0), (0, 0))])
        self.assertEqual((found.gaps, found.surplus, found.open_ends),
                         ([], [4], 0))

    def test_an_arc_over_a_chord_is_not_its_duplicate(self) -> None:
        arc = Edge(4, (0, 0), (100, 0), (50, -50), 157.0)
        self.assertEqual(closure.inspect(square() + [arc]).surplus, [])

    def test_an_edge_of_no_length_is_surplus(self) -> None:
        found = closure.inspect(square() + [line(4, (30, 30), (30, 30))])
        self.assertEqual((found.surplus, found.open_ends), ([4], 0))

    def test_a_gap_is_not_closed_onto_a_duplicate(self) -> None:
        edges = square(gap=0.5) + [line(4, (0, 0), (100, 0))]
        found = closure.inspect(edges)
        self.assertEqual(found.surplus, [4])
        self.assertEqual(found.gaps, [((0, START), (3, END))])

    def test_a_stray_edge_is_counted_not_touched(self) -> None:
        found = closure.inspect(square() + [line(4, (0, 0), (-40, -40))])
        self.assertEqual((found.gaps, found.open_ends), ([], 1))

    def test_each_loose_end_joins_its_nearest_only(self) -> None:
        edges = [line(0, (0, 0), (100, 0)), line(1, (100.2, 0), (100, 100)),
                 line(2, (100.6, 0), (200, 50))]
        found = closure.inspect(edges)
        self.assertEqual(found.gaps, [((0, END), (1, START))])
        self.assertEqual(found.open_ends, 4)

    def test_an_edge_is_not_joined_to_itself(self) -> None:
        nearly_a_ring = Edge(0, (10, 0), (10, 0.01), (-10, 0), 62.8)
        found = closure.inspect([nearly_a_ring])
        self.assertEqual((found.gaps, found.open_ends), ([], 2))

    def test_a_fork_is_counted(self) -> None:
        found = closure.inspect(square() + [line(4, (0, 0), (100, 100))])
        self.assertEqual((found.forks, found.open_ends, found.overlaps),
                         (2, 0, []))
        self.assertFalse(found.closed())

    def test_nothing_at_all(self) -> None:
        self.assertTrue(closure.inspect([]).closed())


class OverlapTests(unittest.TestCase):

    def test_a_closed_profile_is_not_searched(self) -> None:
        self.assertTrue(closure.inspect(square()).closed())

    def test_a_short_line_on_a_side(self) -> None:
        found = closure.inspect(square() + [line(4, (20, 0), (60, 0))])
        self.assertEqual((found.overlaps, found.open_ends), ([(0, 4)], 2))

    def test_one_drawn_from_the_corner(self) -> None:
        found = closure.inspect(square() + [line(4, (0, 0), (60, 0))])
        self.assertEqual(found.overlaps, [(0, 4)])

    def test_a_long_line_over_a_side_in_two_pieces(self) -> None:
        edges = [line(0, (0, 0), (40, 0)), line(5, (40, 0), (100, 0))]
        edges += square()[1:] + [line(4, (0, 0), (100, 0))]
        found = closure.inspect(edges)
        self.assertEqual(sorted(found.overlaps), [(0, 4), (5, 4)])

    def test_lines_part_way_over_each_other(self) -> None:
        edges = [line(0, (0, 0), (60, 0)), line(4, (40, 0), (100, 0))]
        found = closure.inspect(edges + square()[1:])
        self.assertEqual(found.overlaps, [(0, 4)])

    def test_lines_end_to_end_do_not_overlap(self) -> None:
        edges = [line(0, (0, 0), (40, 0)), line(4, (40, 0), (100, 0))]
        self.assertTrue(closure.inspect(edges + square()[1:]).closed())

    def test_the_sides_of_a_thin_slot_do_not_overlap(self) -> None:
        slot = [line(0, (0, 0), (100, 0)), line(1, (100, 0), (100, 0.05)),
                line(2, (100, 0.05), (0, 0.05)), line(3, (0, 0.05), (0, 0)),
                line(4, (0, 0), (-30, -30))]
        self.assertEqual(closure.inspect(slot).overlaps, [])

    def test_crossing_lines_do_not_overlap(self) -> None:
        found = closure.inspect(square() + [line(4, (50, -20), (50, 20))])
        self.assertEqual(found.overlaps, [])

    def test_an_arc_inside_another(self) -> None:
        ring = [arc(0, 0, 180), arc(1, 180, 360), arc(2, 30, 90)]
        self.assertEqual(closure.inspect(ring).overlaps, [(0, 2)])

    def test_whichever_way_round_they_were_drawn(self) -> None:
        ring = [arc(0, 180, 0), arc(1, 180, 360), arc(2, 90, 30)]
        self.assertEqual(closure.inspect(ring).overlaps, [(0, 2)])

    def test_an_arc_across_where_another_begins(self) -> None:
        ring = [arc(0, 0, 180), arc(1, 180, 360), arc(2, -20, 40)]
        found = closure.inspect(ring)
        self.assertEqual(sorted(found.overlaps), [(0, 2), (1, 2)])

    def test_arcs_of_other_circles_do_not_overlap(self) -> None:
        ring = [arc(0, 0, 180), arc(1, 180, 360), arc(2, 30, 90, radius=49),
                arc(3, 30, 90, centre=(1.0, 0.0))]
        self.assertEqual(closure.inspect(ring).overlaps, [])

    def test_two_halves_of_a_circle_are_closed(self) -> None:
        self.assertTrue(closure.inspect(
            [arc(0, 0, 180), arc(1, 180, 360)]).closed())

    def test_a_chord_does_not_overlap_its_arc(self) -> None:
        found = closure.inspect(
            [arc(0, 0, 180), line(1, (-50, 0), (50, 0)),
             line(2, (0, 0), (0, 80))])
        self.assertEqual(found.overlaps, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
