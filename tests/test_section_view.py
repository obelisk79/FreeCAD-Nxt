"""Section view: the parts that need no 3D view.

Run with: python3 tests/test_section_view.py
"""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fakes  # noqa: E402

App, Gui = fakes.install()

from freecad.nxt.tools import section_view  # noqa: E402


class Vec:
    """Enough of App.Vector for the plane maths."""

    def __init__(self, x=0.0, y=0.0, z=0.0):  # type: ignore[no-untyped-def]
        self.x, self.y, self.z = float(x), float(y), float(z)

    def dot(self, o):  # type: ignore[no-untyped-def]
        return self.x * o.x + self.y * o.y + self.z * o.z

    def cross(self, o):  # type: ignore[no-untyped-def]
        return Vec(self.y * o.z - self.z * o.y, self.z * o.x - self.x * o.z,
                   self.x * o.y - self.y * o.x)

    def normalize(self):  # type: ignore[no-untyped-def]
        n = self.dot(self) ** 0.5
        self.x, self.y, self.z = self.x / n, self.y / n, self.z / n
        return self


App.Vector = Vec


class PlaneTests(unittest.TestCase):

    def test_the_axes_span_the_plane(self) -> None:
        for n in (Vec(1, 0, 0), Vec(0, 0, 1), Vec(1, 1, 1).normalize()):
            u, v = section_view.plane_axes(n)
            for a, b in ((u, n), (v, n), (u, v)):
                self.assertAlmostEqual(a.dot(b), 0.0)

    def test_the_cut_faces_the_camera(self) -> None:
        axis = section_view.facing_axis(Vec(0.2, -0.9, 0.3))
        self.assertEqual((axis.x, axis.y, axis.z), (0.0, -1.0, 0.0))


class ShadeTests(unittest.TestCase):

    def test_cap_and_ink_are_the_body_darkened(self) -> None:
        shade = section_view.shade
        self.assertEqual(shade((1.0, 0.5, 0.0), 0.4), (0.4, 0.2, 0.0))

    def test_desaturating_moves_toward_grey(self) -> None:
        desaturate = section_view.desaturate
        self.assertEqual(desaturate((0.5, 0.5, 0.5), 0.3), (0.5, 0.5, 0.5))
        r, g, b = desaturate((0.0, 1.0, 0.0), 1.0)
        self.assertAlmostEqual(r, g)
        self.assertAlmostEqual(g, b)
        r, g, b = desaturate((0.0, 1.0, 0.0), 0.3)
        self.assertGreater(g, r)
        self.assertGreater(r, 0.0)

    def test_a_stipple_is_32_rows_of_32_bits(self) -> None:
        for pattern in section_view.PATTERNS.values():
            self.assertEqual(len(pattern), 128)
        lines = section_view.PATTERNS["horizontal"]
        step = section_view.HATCH_STEP
        width = section_view.HATCH_WIDTH
        self.assertEqual(lines[0:4 * width], b"\xff" * 4 * width)
        self.assertEqual(lines[4 * width:4 * step],
                         bytes(4 * (step - width)))

    def test_the_hatch_tile_is_its_stipple_in_rgba(self) -> None:
        tile = section_view.pattern_rgba(section_view.PATTERNS["horizontal"])
        self.assertEqual(len(tile), 32 * 32 * 4)
        self.assertEqual(tile[:4], b"\xff" * 4)
        width = section_view.HATCH_WIDTH
        self.assertEqual(tile[32 * 4 * width:32 * 4 * width + 4], bytes(4))

    def test_the_tile_steps_in_powers_of_two(self) -> None:
        tile = section_view.snapped_tile
        self.assertEqual(tile(2.0 / 32), 2.0)
        self.assertEqual(tile(2.3 / 32), 2.0)
        self.assertEqual(tile(3.5 / 32), 4.0)

    def test_a_part_always_gets_the_same_hatch(self) -> None:
        pick = section_view.pattern_for
        self.assertEqual(pick("Body"), pick("Body"))
        self.assertIn(pick("Body"), section_view.PATTERNS)
        picks = {pick("Body%03d" % i) for i in range(30)}
        self.assertGreater(len(picks), 1)

    def test_a_colour_from_the_view_provider(self) -> None:
        red = types.SimpleNamespace(DiffuseColor=(1.0, 0.0, 0.0, 1.0))
        obj = types.SimpleNamespace(
            ViewObject=types.SimpleNamespace(ShapeAppearance=[red]))
        self.assertEqual(section_view.body_colour(obj), (1.0, 0.0, 0.0))
        bare = types.SimpleNamespace(ViewObject=None)
        self.assertEqual(section_view.body_colour(bare),
                         section_view.DEFAULT_BODY)


class FrameTests(unittest.TestCase):

    def test_the_buttons_take_the_top_left_corner(self) -> None:
        corners = [(0, 0), (100, 0), (100, 80), (0, 80)]   # y up
        self.assertEqual(section_view.top_left(corners), 3)
        self.assertEqual(section_view.top_left(corners, avoid=3), 0)

    def test_tilts_snap_to_their_step(self) -> None:
        snap = section_view.snap_angle
        self.assertEqual(snap(7.4, 5.0), 5.0)
        self.assertEqual(snap(8.0, 15.0), 15.0)
        self.assertEqual(snap(7.4, 0.0), 7.4)

    def test_distance_to_an_arc(self) -> None:
        arc = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]
        self.assertAlmostEqual(
            section_view.polyline_distance((12.0, 5.0), arc), 2.0)

    def test_distance_to_the_frame_edge(self) -> None:
        d = section_view.segment_distance
        self.assertAlmostEqual(d((5, 3), (0, 0), (10, 0)), 3.0)
        self.assertAlmostEqual(d((13, 4), (0, 0), (10, 0)), 5.0)

    def test_a_drag_follows_the_normal_on_screen(self) -> None:
        # One unit along the normal shows as 4 px to the right.
        moved = section_view.drag_amount((0, 0), (8, 3), (4, 0), 4, True)
        self.assertAlmostEqual(moved, 2.0)

    def test_head_on_up_brings_the_plane_closer(self) -> None:
        amount = section_view.drag_amount
        self.assertAlmostEqual(amount((0, 0), (0, 10), (0.1, 0), 5, True),
                               -2.0)
        self.assertAlmostEqual(amount((0, 0), (0, 10), (0.1, 0), 5, False),
                               2.0)


class Pl:
    """Placements as offsets along x, enough to follow nesting."""

    def __init__(self, x: float = 0.0) -> None:
        self.x = x

    def multiply(self, other: "Pl") -> "Pl":
        return Pl(self.x + other.x)


App.Placement = Pl


class Shape:

    def __init__(self, solids: int = 1, x: float = 0.0,
                 length: float = 1.0) -> None:
        self.Solids = [0] * solids
        self.Placement = Pl(x)
        self.BoundBox = types.SimpleNamespace(
            isValid=lambda: True, DiagonalLength=length)

    def isNull(self) -> bool:
        return False

    def copy(self) -> "Shape":
        return Shape(len(self.Solids), self.Placement.x)


def thing(name: str, visible: bool = True, geo: object = None,
          group: object = None, solids: int = 1, x: float = 0.0,
          types_: tuple[str, ...] = (), children: list | None = None,
          colour: tuple[float, float, float] | None = None,
          link: object = None) -> types.SimpleNamespace:
    view = types.SimpleNamespace(Visibility=visible)
    if colour is not None:
        view.ShapeAppearance = [types.SimpleNamespace(DiffuseColor=colour)]
    obj = types.SimpleNamespace(Name=name, ViewObject=view,
                                Placement=Pl(x), Group=children or [],
                                shape=Shape(solids, x))
    obj.getParentGeoFeatureGroup = lambda: geo
    obj.getParentGroup = lambda: group
    obj.isDerivedFrom = lambda t: t in types_
    obj.getLinkedObject = lambda _recurse: link or obj
    return obj


def instances(*objects: types.SimpleNamespace) -> list:
    doc = types.SimpleNamespace(Objects=list(objects))
    return section_view.cut_instances(doc, lambda o: o.shape)


class SolidsTests(unittest.TestCase):

    def test_a_solid_with_no_usable_box_is_left_out(self) -> None:
        broken = thing("Broken")
        broken.shape = Shape(length=float("inf"))
        found = instances(thing("Good"), broken)
        self.assertEqual([i.name for i in found], ["Good"])

    def test_a_body_is_counted_once(self) -> None:
        body = thing("Body")
        tip = thing("Pad", geo=body)
        self.assertEqual([i.name for i in instances(body, tip)], ["Body"])

    def test_hidden_and_solidless_objects_are_left_out(self) -> None:
        found = instances(thing("Box"), thing("Hidden", visible=False),
                          thing("Sketch", solids=0))
        self.assertEqual([i.name for i in found], ["Box"])

    def test_an_assembly_is_cut_part_by_part(self) -> None:
        red, green = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
        arm = thing("Arm", x=1, colour=red)
        boom = thing("Boom", x=2, colour=green)
        assembly = thing("Assembly", x=10, types_=("App::Part",),
                         children=[arm, boom])
        arm.getParentGroup = boom.getParentGroup = lambda: assembly
        found = instances(assembly, arm, boom)
        self.assertEqual([(i.name, i.colour, i.shape.Placement.x)
                          for i in found],
                         [("Arm", red, 11), ("Boom", green, 12)])

    def test_a_link_shows_its_target_colour(self) -> None:
        blue = (0.0, 0.0, 1.0)
        body = thing("Body", colour=blue, visible=False)
        link = thing("Link", link=body)
        found = instances(body, link)
        self.assertEqual([(i.name, i.colour) for i in found],
                         [("Link", blue)])


class CapTrimTests(unittest.TestCase):
    """A cap is trimmed by the other sections' planes, on the CPU."""

    SQUARE = [(0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (2.0, 2.0, 0.0),
              (0.0, 2.0, 0.0)]

    def clip(self, *planes: tuple) -> list:
        return section_view.clip_polygon(self.SQUARE, list(planes))

    def test_no_other_section_keeps_the_whole_quad(self) -> None:
        self.assertEqual(self.clip(), self.SQUARE)

    def test_the_kept_side_is_the_one_the_normal_faces(self) -> None:
        self.assertEqual(self.clip(((1.0, 0.0, 0.0), 1.0)),
                         [(1.0, 0.0, 0.0), (2.0, 0.0, 0.0),
                          (2.0, 2.0, 0.0), (1.0, 2.0, 0.0)])

    def test_a_slanted_plane_cuts_a_corner_off(self) -> None:
        self.assertEqual(self.clip(((1.0, 1.0, 0.0), 3.0)),
                         [(2.0, 1.0, 0.0), (2.0, 2.0, 0.0),
                          (1.0, 2.0, 0.0)])

    def test_a_plane_past_the_quad_leaves_no_cap(self) -> None:
        self.assertEqual(self.clip(((1.0, 0.0, 0.0), 5.0)), [])

    def test_two_planes_both_trim(self) -> None:
        kept = self.clip(((1.0, 0.0, 0.0), 1.0), ((0.0, -1.0, 0.0), -1.0))
        self.assertEqual(sorted(kept), [(1.0, 0.0, 0.0), (1.0, 1.0, 0.0),
                                        (2.0, 0.0, 0.0), (2.0, 1.0, 0.0)])

    def test_the_seam_is_the_edge_the_other_plane_made(self) -> None:
        plane = ((1.0, 0.0, 0.0), 1.0)
        kept = self.clip(plane)
        self.assertEqual(section_view.seams(kept, [plane], 1e-9),
                         [((1.0, 2.0, 0.0), (1.0, 0.0, 0.0))])

    def test_an_untrimmed_cap_has_no_seam(self) -> None:
        self.assertEqual(section_view.seams(self.SQUARE, [], 1e-9), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
