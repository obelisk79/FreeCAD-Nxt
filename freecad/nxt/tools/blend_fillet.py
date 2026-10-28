"""Rolling-ball fillet built from booleans instead of BRepFilletAPI.

For each edge, the section between the edge, the ball's two contact
points and its arc is cut from a convex edge or fused onto a concave one:
extruded along a straight edge and turned about a circular edge between
coaxial faces (both exact), or lofted along anything else (approximate,
and reported). A round running on along a crease that fades out to
tangent is built into the faces instead (fillet_fade.py).
"""

from __future__ import annotations

import math
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import FreeCAD as App
import Part

from ..resources import ICONS

FEATURE_NAME = "NxtFillet"
#: Part Design's Python feature that Mirrored and the patterns accept:
#: it carries the material it adds or removes (AddSubShape).
FEATURE_TYPE = "PartDesign::FeatureAddSubPython"
#: What files from before 0.6 made, upgraded on opening (fillet_upgrade).
OLD_FEATURE_TYPE = "PartDesign::FeaturePython"
CHAMFER_NAME = "NxtChamfer"
DEFAULT_RADIUS = 1.0
#: Stations per radius of edge length on a curved edge, and their bounds.
STATIONS_PER_RADIUS = 2.0
MIN_STATIONS = 3
MAX_STATIONS = 64
#: Relative tolerance for parallel axes and points on an axis.
AXIS_TOLERANCE = 1e-9
FULL_TURN = 2 * math.pi
#: Edges this close to parallel at a shared vertex run on tangentially.
TANGENT_TOLERANCE = 1e-4
#: Faces closer to flat or to folded back than this get no fillet.
MIN_TURN = 1e-3
#: Distance used to tell which side of the edge a face lies on.
PROBE = 1e-3
#: Faces walked each way from the edge looking for the ball's contact.
MAX_LEGS = 8
#: Points this close, as a fraction of the radius, are the same point.
WALK_TOLERANCE = 1e-5
#: Contacts this far off a face, as a fraction of the radius, miss it.
FIT_TOLERANCE = 1e-4
#: Halvings when searching for the largest radius that fits.
FIT_STEPS = 14
#: Points sampled along a B-spline to tell whether it is a line or arc.
FORM_SAMPLES = 8
#: How far, in radii, an added blend runs past an end its face trims.
END_REACH = 3.0
#: Refinements of a free-form contact, and how far off the radius the
#: settled ball may be.
ROLL_STEPS = 12
ROLL_TOLERANCE = 1e-3


@dataclass
class Profile:
    """A face's outline in the section plane: a circle, or else a line."""

    centre: App.Vector | None = None
    radius: float = 0.0


@dataclass
class Station:
    point: App.Vector
    tangent: App.Vector
    centre: App.Vector
    contact1: App.Vector
    contact2: App.Vector
    profile1: Profile = field(default_factory=Profile)
    profile2: Profile = field(default_factory=Profile)


def _normal(face: Any, point: App.Vector) -> App.Vector:
    u, v = face.Surface.parameter(point)
    return face.normalAt(u, v).normalize()


def _faces_of(shape: Any, edge: Any) -> list[Any]:
    return [f for f in shape.ancestorsOfType(edge, Part.Face)]


#: The solid whose edges are being filleted, for inside/outside tests.
_solid: list[Any] = []
#: Set while chamfering: the ball's arc is replaced by its chord.
_flat: list[bool] = []
#: Set while a held handle previews: booleans' results are not checked.
_held: list[bool] = []
#: While chamfering an edge, its distance per unit of ball radius.
_scale: list[float] = []


def _noun() -> str:
    return "distance" if _flat and _flat[-1] else "radius"


def _shown(radius: float) -> float:
    """A ball radius as the user set it: a chamfer's distance."""
    return radius * _scale[-1] if _scale else radius


def _blend(touch1: App.Vector, touch2: App.Vector, centre: App.Vector,
           radius: float) -> Any:
    """The ball's arc between its contacts, or its chord for a chamfer."""
    if _flat and _flat[-1]:
        return Part.LineSegment(touch1, touch2).toShape()
    halfway = (touch1 - centre) + (touch2 - centre)
    halfway.normalize()
    return Part.Arc(touch1, centre + halfway * radius, touch2).toShape()


def _contains(shape: Any, at: App.Vector, tolerance: float) -> bool:
    """Point-in-solid that also works on a feature's compound."""
    return any(s.isInside(at, tolerance, True)
               for s in (list(shape.Solids) or [shape]))


def _inside(at: App.Vector) -> bool | None:
    """Whether `at` is in the solid being filleted; None if none is set.

    A feature's shape is often a compound, so its solids are asked.
    """
    if not _solid:
        return None
    shape = _solid[-1]
    step = _step()
    if _far_from(shape, at, step / 10):
        return False
    return any(s.isInside(at, step / 10, False)
               for s in (list(shape.Solids) or [shape]))


def _far_from(shape: Any, point: App.Vector, gap: float) -> bool:
    """Whether `point` is surely more than `gap` from `shape`: its box."""
    box = shape.BoundBox
    box.enlarge(gap)
    return not box.isInside(point)


def _apart(a: Any, b: Any, gap: float) -> bool:
    """Whether two shapes are surely more than `gap` apart: their boxes."""
    box = a.BoundBox
    box.enlarge(gap)
    return not box.intersect(b.BoundBox)


def _step() -> float:
    return max(_solid[-1].BoundBox.DiagonalLength * 1e-5, 1e-4)


def _oriented(point: App.Vector, n1: App.Vector,
              n2: App.Vector) -> tuple[bool, App.Vector, App.Vector] | None:
    """Convexity and truly outward normals, read from the solid.

    Just off the edge, towards each mix of the two normals, a convex
    edge has material in one quadrant and a concave one in three; the
    odd quadrant also shows which way each face really faces, whatever
    the face's own orientation says.
    """
    if not _solid:
        return None
    key = (id(_solid[-1]), _rounded(point), _rounded(n1), _rounded(n2))
    if key not in _oriented_seen:
        _oriented_seen[key] = _read_quadrants(point, n1, n2)
    return _oriented_seen[key]


#: _oriented's answers for the current fillet; each costs four
#: point-in-solid tests and the same edge is asked many times.
_oriented_seen: dict[tuple[Any, ...], Any] = {}


def _rounded(v: App.Vector) -> tuple[float, float, float]:
    return (round(v.x, 7), round(v.y, 7), round(v.z, 7))


def _read_quadrants(point: App.Vector, n1: App.Vector, n2: App.Vector
                    ) -> tuple[bool, App.Vector, App.Vector] | None:
    step = _step()
    found = {(a, b): bool(_inside(point + (n1 * a + n2 * b) * step))
             for a in (1, -1) for b in (1, -1)}
    material = [k for k, v in found.items() if v]
    if len(material) == 1:
        a, b = material[0]
        return True, n1 * -a, n2 * -b
    if len(material) == 3:
        a, b = next(k for k, v in found.items() if not v)
        return False, n1 * a, n2 * b
    return None


def _material_says(point: App.Vector, n1: App.Vector,
                   n2: App.Vector) -> bool | None:
    """Convexity from the solid itself, or None if it cannot tell."""
    found = _oriented(point, n1, n2)
    return None if found is None else found[0]


def _is_convex(face1: Any, point: App.Vector, tangent: App.Vector,
               n1: App.Vector, n2: App.Vector) -> bool:
    said = _material_says(point, n1, n2)
    if said is not None:
        return said
    across = tangent.cross(n1).normalize()
    vertex = Part.Vertex
    ahead = face1.distToShape(vertex(point + across * PROBE))[0]
    behind = face1.distToShape(vertex(point - across * PROBE))[0]
    into_face1 = across if ahead < behind else -across
    return into_face1.dot(n2) < 0


def _station(face1: Any, face2: Any, edge: Any, u: float, radius: float,
             convex: bool | None) -> tuple[Station, bool] | None:
    point = edge.valueAt(u)
    tangent = edge.tangentAt(u).normalize()
    n1, n2 = _normal(face1, point), _normal(face2, point)
    cosine = n1.dot(n2)
    if 1 - abs(cosine) < MIN_TURN:
        return None
    # Judged mid-edge: at an end the corner may already be cut away.
    middle = edge.valueAt((edge.FirstParameter + edge.LastParameter) / 2)
    m1, m2 = _normal(face1, middle), _normal(face2, middle)
    found = _oriented(middle, m1, m2)
    if found is not None:
        convex = found[0]
        n1 = n1 if found[1].dot(m1) > 0 else -n1
        n2 = n2 if found[2].dot(m2) > 0 else -n2
        cosine = n1.dot(n2)
    elif convex is None:
        convex = _is_convex(face1, point, tangent, n1, n2)
    side = -1 if convex else 1
    centre = point + (n1 + n2) * (side * radius / (1 + cosine))
    return Station(point, tangent, centre,
                   centre - n1 * (side * radius),
                   centre - n2 * (side * radius)), convex


def _moved(profile: Profile, offset: App.Vector) -> Profile:
    if profile.centre is None:
        return profile
    return Profile(profile.centre + offset, profile.radius)


def _shifted(station: Station, offset: App.Vector) -> Station:
    return Station(station.point + offset, station.tangent,
                   station.centre + offset, station.contact1 + offset,
                   station.contact2 + offset,
                   _moved(station.profile1, offset),
                   _moved(station.profile2, offset))


def _profile(face: Any, point: App.Vector, tangent: App.Vector) -> Profile:
    """The face's outline in the plane across the edge at `point`.

    A circle for a cylinder along the edge, a sphere, or a torus turned
    about the edge's axis; a line for planes, and for cylinders and cones
    turned about it. Anything else is taken as its tangent line.
    """
    surface = face.Surface
    if isinstance(surface, Part.Cylinder) and _parallel(surface.Axis,
                                                        tangent):
        axis = App.Vector(surface.Axis)
        axis.normalize()
        along = (point - surface.Center).dot(axis)
        return Profile(surface.Center + axis * along, surface.Radius)
    if isinstance(surface, Part.Sphere):
        return Profile(App.Vector(surface.Center), surface.Radius)
    if isinstance(surface, Part.Toroid):
        axis = App.Vector(surface.Axis)
        axis.normalize()
        radial = point - surface.Center
        radial = radial - axis * radial.dot(axis)
        radial.normalize()
        return Profile(surface.Center + radial * surface.MajorRadius,
                       surface.MinorRadius)
    return Profile()


def _exact(face: Any, tangent: App.Vector) -> bool:
    """Whether a straight edge's face keeps one outline along it."""
    surface = face.Surface
    return isinstance(surface, Part.Plane) or (
        isinstance(surface, Part.Cylinder)
        and _parallel(surface.Axis, tangent))


Point2 = tuple[float, float]
#: A line (point, direction) or a circle (centre, radius) in the plane.
Curve2 = tuple[str, Point2, Any]


def _cross2(a: Point2, b: Point2) -> float:
    return a[0] * b[1] - a[1] * b[0]


def _meet(a: Curve2, b: Curve2) -> list[Point2]:
    """Where two lines or circles in the plane cross."""
    if a[0] == "circle" and b[0] == "line":
        a, b = b, a
    if a[0] == "line" and b[0] == "line":
        (_, q1, w1), (_, q2, w2) = a, b
        det = _cross2(w1, w2)
        if abs(det) < 1e-12:
            return []
        s = _cross2((q2[0] - q1[0], q2[1] - q1[1]), w2) / det
        return [(q1[0] + w1[0] * s, q1[1] + w1[1] * s)]
    if a[0] == "line":
        (_, q, w), (_, c, r) = a, b
        f = (q[0] - c[0], q[1] - c[1])
        aa = w[0] ** 2 + w[1] ** 2
        bb = 2 * (f[0] * w[0] + f[1] * w[1])
        cc = f[0] ** 2 + f[1] ** 2 - r ** 2
        disc = bb * bb - 4 * aa * cc
        if disc < 0:
            return []
        roots = [(-bb + k * math.sqrt(disc)) / (2 * aa) for k in (-1, 1)]
        return [(q[0] + w[0] * t, q[1] + w[1] * t) for t in roots]
    (_, c1, r1), (_, c2, r2) = a, b
    dx, dy = c2[0] - c1[0], c2[1] - c1[1]
    d = math.hypot(dx, dy)
    if d < 1e-12 or d > r1 + r2 or d < abs(r1 - r2):
        return []
    along = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
    h = math.sqrt(max(r1 * r1 - along * along, 0.0))
    mx, my = c1[0] + along * dx / d, c1[1] + along * dy / d
    return [(mx - h * dy / d, my + h * dx / d),
            (mx + h * dy / d, my - h * dx / d)]


def _rolled(face1: Any, face2: Any, edge: Any, u: float, radius: float,
            convex: bool | None) -> tuple[Station, bool] | None:
    """The ball touching both faces as they really are, not as planes.

    In the plane across the edge, each face's outline is moved the
    radius towards the ball; the centre is where the two moved outlines
    meet, nearest the flat-face estimate.
    """
    rough = _station(face1, face2, edge, u, radius, convex)
    if rough is None:
        return None
    guess, convex = rough
    point, tangent = guess.point, guess.tangent
    side = -1 if convex else 1
    normals = ((guess.centre - guess.contact1) * (side / radius),
               (guess.centre - guess.contact2) * (side / radius))
    profiles = (_profile(face1, point, tangent),
                _profile(face2, point, tangent))
    if all(p.centre is None for p in profiles):
        return guess, convex
    e1 = App.Vector(normals[0])
    e2 = tangent.cross(e1)
    e2.normalize()

    def flat(v: App.Vector) -> Point2:
        d = v - point
        return (d.dot(e1), d.dot(e2))

    curves: list[Curve2] = []
    for n, profile in zip(normals, profiles):
        towards = n * (side * radius)
        if profile.centre is None:
            along = tangent.cross(n)
            curves.append(("line", flat(point + towards),
                           (along.dot(e1), along.dot(e2))))
        else:
            reach = (point + towards - profile.centre).Length
            curves.append(("circle", flat(profile.centre), reach))
    near = flat(guess.centre)
    found = _meet(curves[0], curves[1])
    if not found:
        raise ValueError("the %s does not fit between the faces" % _noun())
    x, y = min(found, key=lambda q: (q[0] - near[0]) ** 2
               + (q[1] - near[1]) ** 2)
    centre = point + e1 * x + e2 * y

    def contact(n: App.Vector, profile: Profile) -> App.Vector:
        if profile.centre is None:
            return centre - n * (side * radius)
        out = centre - profile.centre
        out.normalize()
        return profile.centre + out * profile.radius

    return Station(point, tangent, centre,
                   contact(normals[0], profiles[0]),
                   contact(normals[1], profiles[1]),
                   profiles[0], profiles[1]), convex


#: Most an edge may turn between two sections of a lofted blend, degrees.
MAX_TURN_PER_STATION = 10.0
#: Why a round is not carried on along a crease that fades out.
NO_RUN_OUT = ("the round could not be run out where the faces turn "
              "tangent; it stops where the edge before it ends")
#: Why an edge is skipped when its blend will not go into the part.
NO_JOIN = ("it could not be blended into the part here; the faces it "
           "meets curve too tightly for this size. Try a smaller size, or "
           "round this edge in a feature of its own")


def _turn(edge: Any) -> float:
    """How far the edge's direction turns along it, in degrees."""
    first, last = edge.FirstParameter, edge.LastParameter
    tangents = [edge.tangentAt(first + (last - first) * k / 16)
                for k in range(17)]
    return sum(math.degrees(a.getAngle(b))
               for a, b in zip(tangents, tangents[1:]))


def _bend(edge: Any) -> float:
    """The tightest radius the edge bends round; inf if it is straight."""
    first, last = edge.FirstParameter, edge.LastParameter
    most = 0.0
    for k in range(17):
        try:
            most = max(most, edge.curvatureAt(first + (last - first) * k / 16))
        except Exception:  # noqa: BLE001 - a point without curvature
            pass
    return 1 / most if most > 1e-12 else math.inf


def _crossed(solid: Any) -> bool:
    """Whether the solid's faces run through each other."""
    try:
        solid.check(True)
    except Exception:  # noqa: BLE001 - what the check reports
        return True
    return False


def _parameters(edge: Any, radius: float) -> list[float]:
    first, last = edge.FirstParameter, edge.LastParameter
    if isinstance(edge.Curve, Part.Line):
        return [first, last]
    count = round(edge.Length / radius * STATIONS_PER_RADIUS)
    # A tight bend needs sections close together, however short.
    count = max(count, round(_turn(edge) / MAX_TURN_PER_STATION) + 1)
    count = max(MIN_STATIONS, min(MAX_STATIONS, count))
    if edge.isClosed():
        step = (last - first) / count
        return [first + i * step for i in range(count)]
    step = (last - first) / (count - 1)
    return [first + i * step for i in range(count)]


def _along(profile: Profile, start: App.Vector, end: App.Vector) -> Any:
    """The face's outline from `start` to `end`, a line or a short arc."""
    if profile.centre is None:
        return Part.LineSegment(start, end).toShape()
    halfway = (start - profile.centre) + (end - profile.centre)
    halfway.normalize()
    mid = profile.centre + halfway * profile.radius
    return Part.Arc(start, mid, end).toShape()


def _section(station: Station, radius: float) -> Any:
    """The edge's corner, its two contact points, and the arc between.

    Its sides follow the two faces, so the boolean meets them face on
    face rather than at a tangent.
    """
    return Part.Wire([
        _along(station.profile1, station.point, station.contact1),
        _blend(station.contact1, station.contact2, station.centre, radius),
        _along(station.profile2, station.contact2, station.point),
    ])


def _wide_section(station: Station, radius: float,
                  push: float | None = None) -> Any:
    """The ball's arc, closed by a corner pushed past the edge.

    Its sides cross the faces instead of following them: a face curved
    across the section would otherwise leave a sliver, or lose one, on
    the far side of a straight side. `push`, if less than the radius,
    keeps the corners of sections round a tight bend from crossing.
    """
    outward = station.point - station.centre
    outward.normalize()
    reach = radius if push is None else min(radius, push)
    corner = station.point + outward * reach
    return Part.Wire([
        Part.LineSegment(corner, station.contact1).toShape(),
        _blend(station.contact1, station.contact2, station.centre, radius),
        Part.LineSegment(station.contact2, corner).toShape(),
    ])


@dataclass
class Leg:
    """One edge of the cut outline, walked from `start` to `end`."""

    edge: Any
    start: App.Vector
    end: App.Vector


def _near(a: App.Vector, b: App.Vector, tolerance: float) -> bool:
    return (a - b).Length < tolerance


def _walks(wire: Any, point: App.Vector, tolerance: float) -> list[list[Leg]]:
    """The outline's edges in order, each way from the corner."""
    edges = list(wire.Edges)

    def ends(edge: Any) -> tuple[App.Vector, App.Vector]:
        return edge.Vertexes[0].Point, edge.Vertexes[-1].Point

    walks: list[list[Leg]] = []
    for first in [e for e in edges
                  if any(_near(p, point, tolerance) for p in ends(e))]:
        legs: list[Leg] = []
        used = {id(first)}
        edge, at = first, point
        while edge is not None and len(legs) < MAX_LEGS:
            a, b = ends(edge)
            far = b if _near(a, at, tolerance) else a
            legs.append(Leg(edge, at, far))
            at = far
            if _near(at, point, tolerance):
                break
            edge = next((e for e in edges if id(e) not in used
                         and any(_near(p, at, tolerance) for p in ends(e))),
                        None)
            if edge is not None:
                used.add(id(edge))
        walks.append(legs)
    if len(walks) != 2:
        raise _UnsupportedError("the outline does not pass through the edge")
    return walks


class _UnsupportedError(ValueError):
    """The outline has curves other than lines and arcs."""


class _CoveredError(ValueError):
    """The ball reaches a face standing on the edge's own: it trims it."""


def _towards_ball(shape: Any, leg: Any, tangent: App.Vector,
                  convex: bool, step: float) -> App.Vector:
    """Across the leg, into the material for a convex edge, else out."""
    edge = leg.edge
    middle = (edge.FirstParameter + edge.LastParameter) / 2
    at = edge.valueAt(middle)
    across = tangent.cross(edge.tangentAt(middle))
    across.normalize()
    inside = _contains(shape, at + across * step, step / 10)
    if inside != convex:
        across = -across
    return across


def _walked(shape: Any, edge: Any, u: float,
            radius: float) -> tuple[Any, bool, App.Vector]:
    """The cut outline at `u`, rolling over the faces the ball reaches.

    The solid's own outline across the edge is walked from the corner
    until both sides meet the ball. Returns the section face, whether
    the edge is convex, and the ball's centre.
    """
    faces = _faces_of(shape, edge)
    rough = _station(faces[0], faces[1], edge, u, radius, None)
    if rough is None:
        raise ValueError("the faces meet tangentially")
    guess, convex = rough
    point, tangent = guess.point, guess.tangent
    tolerance = radius * WALK_TOLERANCE
    step = radius * 1e-3
    wires = shape.slice(tangent, tangent.dot(point))
    if not wires:
        raise _UnsupportedError("the edge has no outline across it")
    wire = min(wires, key=lambda w: w.distToShape(Part.Vertex(point))[0])
    walks = _walks(wire, point, tolerance)

    e1 = App.Vector(guess.contact1 - guess.centre)
    e1.normalize()
    e2 = tangent.cross(e1)
    e2.normalize()

    def flat(v: App.Vector) -> Point2:
        d = v - point
        return (d.dot(e1), d.dot(e2))

    fit = radius * FIT_TOLERANCE
    near = flat(guess.centre)

    def offset(form: Form, leg: Leg, d: App.Vector) -> Curve2:
        middle, size, at, along, _free = form
        if middle is None:
            return ("line", flat(at + d * radius),
                    (along.dot(e1), along.dot(e2)))
        moved = (at + d * radius - middle).Length
        return ("circle", flat(middle), moved)

    def touch(form: Form, leg: Leg, d: App.Vector,
              centre: App.Vector) -> App.Vector:
        middle, size, at, along, _free = form
        if middle is None:
            return centre - d * radius
        out = centre - middle
        out.normalize()
        return middle + out * size

    def on(leg: Leg, p: App.Vector) -> bool:
        return leg.edge.distToShape(Part.Vertex(p))[0] < tolerance

    def roll(leg1: Leg, leg2: Leg) -> Rolled | None:
        """The ball against both legs: centre and the two contacts.

        A free-form leg is taken as its circle of curvature at the
        contact, refined until the ball settles.
        """
        d1 = _towards_ball(shape, leg1, tangent, convex, step)
        d2 = _towards_ball(shape, leg2, tangent, convex, step)
        at1, at2 = _middle(leg1.edge), _middle(leg2.edge)
        settled = None
        for _ in range(ROLL_STEPS):
            f1, f2 = _form(leg1.edge, fit, at1), _form(leg2.edge, fit, at2)
            found = _meet(offset(f1, leg1, d1), offset(f2, leg2, d2))
            if not found:
                return None
            x, y = min(found, key=lambda q: (q[0] - near[0]) ** 2
                       + (q[1] - near[1]) ** 2)
            centre = point + e1 * x + e2 * y
            t1 = touch(f1, leg1, d1, centre)
            t2 = touch(f2, leg2, d2, centre)
            if f1[4] or f2[4]:
                t1, t2 = _nearest(leg1.edge, t1), _nearest(leg2.edge, t2)
            if settled is not None and (centre - settled).Length < fit:
                break
            settled = centre
            if not (f1[4] or f2[4]):
                break
            at1 = leg1.edge.Curve.parameter(t1)
            at2 = leg2.edge.Curve.parameter(t2)
        if not (on(leg1, t1) and on(leg2, t2)):
            return None
        if any(abs((centre - t).Length - radius) > radius * ROLL_TOLERANCE
               for t in (t1, t2)):
            return None
        return centre, t1, t2

    def overlaps(legs: list[Leg]) -> bool:
        """Whether the ball rolled onto a face curving against it.

        That is another fillet's round (or hollow) of the opposite kind:
        this one would have to blend into it.
        """
        for leg in legs:
            middle, _size, at, _along, _free = _form(
                leg.edge, fit, _middle(leg.edge))
            if middle is None:
                continue
            d = _towards_ball(shape, leg, tangent, convex, step)
            if (middle - leg.edge.valueAt(_middle(leg.edge))).dot(d) < 0:
                return True
        return False

    def inward(legs: list[Leg]) -> bool:
        """Whether a rounded edge's walk turns up an inner corner.

        Past one the ball would have to sit in the material it rounds:
        the edge's faces end there, so the ball does not fit.
        """
        for a, b in zip(legs, legs[1:]):
            d = _towards_ball(shape, a, tangent, convex, step)
            at = b.edge.Curve.parameter(b.start)
            ahead = b.edge.tangentAt(at)
            if ahead.dot(b.end - b.start) < 0:
                ahead = -ahead
            if ahead.dot(d) < -MIN_TURN:
                return True
        return False

    pairs = sorted(((i, j) for i in range(len(walks[0]))
                    for j in range(len(walks[1]))), key=sum)
    covered = False
    for i, j in pairs:
        if convex and (inward(walks[0][:i + 1]) or inward(walks[1][:j + 1])):
            covered = True
            continue
        leg1, leg2 = walks[0][i], walks[1][j]
        rolled = roll(leg1, leg2)
        if rolled is not None:
            centre, t1, t2 = rolled
            if overlaps(walks[0][1:i + 1]) or overlaps(walks[1][1:j + 1]):
                kind = "chamfers" if _noun() == "distance" else "fillets"
                raise OverlapError(
                    "Cannot generate overlapping %s; the largest %s "
                    "that stays on its own faces is %.4g mm"
                    % (kind, _noun(),
                       _shown(_largest_fit(faces, edge, radius))))
            return _outline(walks[0][:i], leg1, t1, walks[1][:j], leg2,
                            t2, centre, radius, fit), convex, centre
    if covered:
        raise _CoveredError("a face stands within the %s's reach" % _noun())
    raise ValueError("the %s does not fit between the faces" % _noun())


#: (centre or None for a line, radius, a point on it, its direction,
#: whether it is free-form and only matches there).
Form = tuple[Any, float, App.Vector, App.Vector, bool]
#: A settled ball: its centre and its two contacts.
Rolled = tuple[App.Vector, App.Vector, App.Vector]


def _middle(edge: Any) -> float:
    return (edge.FirstParameter + edge.LastParameter) / 2


def _nearest(edge: Any, point: App.Vector) -> App.Vector:
    return edge.distToShape(Part.Vertex(point))[1][0][0]


def _form(edge: Any, tolerance: float, at: float) -> Form:
    """The line or circle an outline edge follows, near parameter `at`.

    Lines and arcs are exact; a B-spline that runs through one within
    `tolerance` is taken as it. Anything else is taken as its circle of
    curvature at `at`, which holds only there.
    """
    curve = edge.Curve
    start, end = edge.Vertexes[0].Point, edge.Vertexes[-1].Point
    if isinstance(curve, Part.Line):
        return None, 0.0, start, end - start, False
    if isinstance(curve, Part.Circle):
        return App.Vector(curve.Center), curve.Radius, start, end - start, \
            False
    first, last = edge.FirstParameter, edge.LastParameter
    points = [edge.valueAt(first + (last - first) * k / FORM_SAMPLES)
              for k in range(FORM_SAMPLES + 1)]
    chord = Part.LineSegment(points[0], points[-1]).toShape()
    if (points[-1] - points[0]).Length > tolerance and all(
            chord.distToShape(Part.Vertex(p))[0] < tolerance
            for p in points):
        return None, 0.0, start, end - start, False
    circle: Any
    try:
        circle = Part.Circle(points[0], points[FORM_SAMPLES // 2],
                             points[-1])
    except Exception:  # noqa: BLE001 - collinear or coincident points
        circle = None
    if circle is not None and all(
            abs((p - circle.Center).Length - circle.Radius) < tolerance
            for p in points):
        return App.Vector(circle.Center), circle.Radius, start, \
            end - start, False
    here = edge.valueAt(at)
    direction = edge.tangentAt(at)
    try:
        bend = curve.curvature(at)
    except Exception:  # noqa: BLE001 - treat as straight here
        bend = 0.0
    if bend < 1e-12:
        return None, 0.0, here, direction, True
    return App.Vector(curve.centerOfCurvature(at)), 1 / bend, here, \
        direction, True


def _part_of(leg: Leg, end: App.Vector, tolerance: float) -> Any:
    edge = leg.edge
    curve = edge.Curve
    if isinstance(curve, Part.Line):
        return Part.LineSegment(leg.start, end).toShape()
    if isinstance(curve, Part.Circle):
        middle = curve.Center
        halfway = (leg.start - middle) + (end - middle)
        halfway.normalize()
        return Part.Arc(leg.start, middle + halfway * curve.Radius,
                        end).toShape()
    a, b = curve.parameter(leg.start), curve.parameter(end)
    return curve.toShape(min(a, b), max(a, b))


def _outline(whole1: list[Leg], last1: Leg, touch1: App.Vector,
             whole2: list[Leg], last2: Leg, touch2: App.Vector,
             centre: App.Vector, radius: float, fit: float) -> Any:
    pieces = [leg.edge.copy() for leg in whole1 + whole2]
    for leg, end in ((last1, touch1), (last2, touch2)):
        if (leg.start - end).Length > radius * WALK_TOLERANCE:
            pieces.append(_part_of(leg, end, fit))
    pieces.append(_blend(touch1, touch2, centre, radius))
    wire = Part.Wire(Part.__sortEdges__(pieces))
    if not wire.isClosed():
        raise ValueError("the cut outline does not close (%d pieces, "
                         "%d after the corner)" % (len(pieces),
                                                   len(whole1 + whole2)))
    face = Part.Face(wire)
    if not face.isValid():
        tolerance = radius * WALK_TOLERANCE
        face.fix(tolerance, tolerance, tolerance)
    if not face.isValid():
        raise ValueError("the cut outline is not a valid face")
    return face


def _open_beyond(shape: Any, at: App.Vector) -> bool:
    """Whether nothing is there: the tool may run past the edge's end."""
    return not _contains(shape, at, 1e-7)


def _fits(faces: list[Any], edge: Any, radius: float) -> bool:
    """Whether the ball touches both faces within their bounds."""
    middle = (edge.FirstParameter + edge.LastParameter) / 2
    try:
        found = _rolled(faces[0], faces[1], edge, middle, radius, None)
    except ValueError:
        return False
    if found is None:
        return False
    station = found[0]
    tolerance = radius * FIT_TOLERANCE
    return all(face.distToShape(Part.Vertex(contact))[0] < tolerance
               for face, contact in zip(faces, (station.contact1,
                                                station.contact2)))


class OverlapError(Exception):
    """The fillet would run into another fillet; not a fallback case."""


def _largest_fit(faces: list[Any], edge: Any, radius: float) -> float:
    """The largest radius up to `radius` whose ball stays on the faces."""
    low, high = 0.0, radius
    for _ in range(FIT_STEPS):
        middle = (low + high) / 2
        if _fits(faces, edge, middle):
            low = middle
        else:
            high = middle
    return low


def _sharp_outer_rim(shape: Any, face: Any, edge: Any,
                     near: App.Vector) -> bool:
    """Whether the face's rim nearest `near` is a sharp outer edge.

    It must turn outward onto a face that can trim what is added beyond
    it: a plane, or a cylinder, cone, sphere or torus.
    """
    rims = [r for r in face.Edges if not r.isSame(edge)]
    if not rims:
        return False
    rim = min(rims, key=lambda r: r.distToShape(Part.Vertex(near))[0])
    beyond = [f for f in _faces_of(shape, rim) if not f.isSame(face)]
    if len(beyond) != 1 or not _trimming(beyond[0]):
        return False
    middle = _middle(rim)
    point = rim.valueAt(middle)
    tangent = rim.tangentAt(middle).normalize()
    n1, n2 = _normal(face, point), _normal(beyond[0], point)
    if 1 - abs(n1.dot(n2)) < MIN_TURN:
        return False
    return _is_convex(face, point, tangent, n1, n2)


def _trimmed_overflow(shape: Any, faces: list[Any], edge: Any,
                      radius: float) -> bool:
    """Whether a concave fillet may run past its faces.

    Only where each face it leaves ends at a sharp outer edge, whose
    neighbouring face then trims it, as other CAD systems do.
    """
    middle = (edge.FirstParameter + edge.LastParameter) / 2
    try:
        found = _rolled(faces[0], faces[1], edge, middle, radius, None)
    except ValueError:
        return False
    if found is None or found[1]:
        return False
    station = found[0]
    tolerance = radius * FIT_TOLERANCE
    for face, contact in zip(faces, (station.contact1, station.contact2)):
        if face.distToShape(Part.Vertex(contact))[0] < tolerance:
            continue
        if not _sharp_outer_rim(shape, face, edge, contact):
            return False
    return True


def _first_station(faces: list[Any], edge: Any,
                   radius: float) -> tuple[Station, bool]:
    found = _rolled(faces[0], faces[1], edge, edge.FirstParameter,
                    radius, None)
    if found is None:
        raise ValueError("the faces meet tangentially")
    return found


def _straight(shape: Any, faces: list[Any], edge: Any,
              radius: float) -> tuple[Any, bool]:
    """Exact: the section extruded along a straight edge."""
    first = edge.FirstParameter
    tangent = edge.tangentAt(first).normalize()
    # Taken mid-edge, where an end face cannot lie in the cutting plane.
    middle = (first + edge.LastParameter) / 2
    back_to_start = edge.valueAt(first) - edge.valueAt(middle)
    try:
        face, convex, centre = _walked(shape, edge, middle, radius)
        face.translate(back_to_start)
        centre = centre + back_to_start
    except ValueError as exc:
        App.Console.PrintWarning("Nxt fillet: %s; using the edge's own "
                                 "faces only\n" % exc)
        station, convex = _first_station(faces, edge, radius)
        face, centre = Part.Face(_section(station, radius)), station.centre
    # Past an end when cutting into empty space, or when adding up to a
    # slanted or curved end face, which then trims it.
    ahead = tangent * (radius / 2)
    start, finish = edge.valueAt(first), edge.valueAt(edge.LastParameter)
    if convex:
        near = radius * WALK_TOLERANCE * 10
        back = radius if (_open_beyond(shape, centre - ahead)
                          or _mitre(shape, edge, start)
                          or _slanted_end(shape, edge, start, tangent)) \
            and not _joined(start, near) else 0.0
        end = centre + tangent * edge.Length + ahead
        forth = radius if (_open_beyond(shape, end)
                           or _mitre(shape, edge, finish)
                           or _slanted_end(shape, edge, finish, tangent)) \
            and not _joined(finish, near) else 0.0
    else:
        back = _end_reach(shape, faces, edge, start, radius)
        forth = _end_reach(shape, faces, edge, finish, radius)
    face.translate(tangent * -back)
    return face.extrude(tangent * (edge.Length + back + forth)), convex


def _slanted_end(shape: Any, edge: Any, at: App.Vector,
                 tangent: App.Vector) -> bool:
    """Whether a planar face met at the end slants across the edge.

    A cut stopped square there would leave a wedge of the corner; it
    runs on instead and the face caps it.
    """
    own = _faces_of(shape, edge)
    tolerance = max(edge.Length * 1e-6, 1e-7)
    vertex = Part.Vertex(at)
    for face in shape.Faces:
        if any(face.isSame(f) for f in own) or \
                not isinstance(face.Surface, Part.Plane) or \
                face.distToShape(vertex)[0] > tolerance:
            continue
        if 1 - abs(App.Vector(face.Surface.Axis).dot(tangent)) > MIN_TURN:
            return True
    return False


def _end_reach(shape: Any, faces: list[Any], edge: Any, at: App.Vector,
               radius: float) -> float:
    """How far an added blend runs past the edge's end at `at`.

    Only where one of its faces ends there at a sharp outer edge onto a
    face that can trim it: the blend then reaches that end face however
    it slants or curves, and the trim cuts it back to it.
    """
    tolerance = radius * WALK_TOLERANCE * 10
    if _joined(at, tolerance):
        return 0.0
    for face in faces:
        other = faces[1] if face.isSame(faces[0]) else faces[0]
        for rim in face.Edges:
            if rim.isSame(edge) or not any(
                    (v.Point - at).Length < tolerance for v in rim.Vertexes):
                continue
            beyond = [f for f in _faces_of(shape, rim)
                      if not f.isSame(face)]
            if len(beyond) != 1 or not _trimming(beyond[0]):
                continue
            # Where the end face runs on smoothly into the other face,
            # the corner closes to nothing there: the blend runs out.
            if 1 - abs(_normal(beyond[0], at).dot(_normal(other, at))) \
                    < MIN_TURN:
                return 0.0
            middle = _middle(rim)
            point = rim.valueAt(middle)
            tangent = rim.tangentAt(middle).normalize()
            n1, n2 = _normal(face, point), _normal(beyond[0], point)
            if 1 - abs(n1.dot(n2)) < MIN_TURN:
                continue
            _solid.append(shape)
            try:
                outward = _is_convex(face, point, tangent, n1, n2)
            finally:
                _solid.pop()
            if outward:
                return radius * END_REACH
    return 0.0


#: Vertices where a filleted edge runs on into another one, tangentially.
_joints: list[list[App.Vector]] = []


def _joined(at: App.Vector, tolerance: float) -> bool:
    """Whether a chain of filleted edges continues through `at`.

    No blend runs past such an end: the next edge's starts there.
    """
    return bool(_joints) and any((p - at).Length < tolerance
                                 for p in _joints[-1])


def _tangent_at(edge: Any, point: App.Vector) -> App.Vector:
    tangent = edge.tangentAt(edge.Curve.parameter(point))
    tangent.normalize()
    return tangent


def _sharp(shape: Any, edge: Any) -> bool:
    """Whether the edge is a crease, between two faces not tangent.

    All along it: a crease that fades out to tangent cannot be rounded.
    """
    faces = _faces_of(shape, edge)
    if len(faces) != 2:
        return False
    first, last = edge.FirstParameter, edge.LastParameter
    for t in (0.02, 0.5, 0.98):
        point = edge.valueAt(first + (last - first) * t)
        cosine = _normal(faces[0], point).dot(_normal(faces[1], point))
        if 1 - abs(cosine) < MIN_TURN:
            return False
    return True


def _runs_on(a: Any, b: Any, tolerance: float) -> App.Vector | None:
    """The vertex where `b` carries on from `a` tangentially, if any."""
    for v in a.Vertexes:
        for w in b.Vertexes:
            if (v.Point - w.Point).Length < tolerance:
                try:
                    if 1 - abs(_tangent_at(a, v.Point).dot(
                            _tangent_at(b, v.Point))) < TANGENT_TOLERANCE:
                        return v.Point
                except Exception:  # noqa: BLE001 - not tangent then
                    pass
    return None


def _faces_run_on(shape: Any, a: Any, b: Any, at: App.Vector) -> bool:
    """Whether `b`'s faces carry on smoothly from `a`'s at `at`.

    Each is one of `a`'s faces or tangent to one there, so the crease
    itself carries on rather than turning into another one.
    """
    old = _faces_of(shape, a)
    for face in _faces_of(shape, b):
        if any(face.isSame(f) for f in old):
            continue
        normal = _normal(face, at)
        if not any(1 - abs(normal.dot(_normal(f, at))) < TANGENT_TOLERANCE
                   for f in old):
            return False
    return True


#: Each crease's kind, by its shape's and its own hash: telling takes
#: points tried against the solid, and the same creases are asked about
#: from choosing them to rounding them.
_convex_seen: dict[tuple[int, int], bool | None] = {}


def _convex_edge(shape: Any, edge: Any) -> bool | None:
    """Whether the crease is an outer corner; None if it cannot tell."""
    key = (shape.hashCode(), edge.hashCode())
    if key not in _convex_seen:
        if len(_convex_seen) > 512:
            _convex_seen.clear()
        _convex_seen[key] = _told_convex(shape, edge)
    return _convex_seen[key]


def _told_convex(shape: Any, edge: Any) -> bool | None:
    faces = _faces_of(shape, edge)
    if len(faces) != 2:
        return None
    middle = _middle(edge)
    point = edge.valueAt(middle)
    n1, n2 = _normal(faces[0], point), _normal(faces[1], point)
    _solid.append(shape)
    try:
        found = _oriented(point, n1, n2)
        if found is not None:
            return bool(found[0])
        tangent = edge.tangentAt(middle).normalize()
        return bool(_is_convex(faces[0], point, tangent, n1, n2))
    except Exception:  # noqa: BLE001 - unknown
        return None
    finally:
        _solid.pop()


def tangent_chain(shape: Any, names: list[str],
                  fading: bool = True) -> list[str]:
    """`names`, then every crease running on tangentially from them.

    Only creases of the same kind: an outer corner never runs on into
    an inner one. With `fading`, also an outer crease that fades out to
    tangent at its far end, as where a plate's side runs on into a boss
    past the hollow round at its foot.
    """
    from . import fillet_fade as fade
    edges = shape.Edges
    tolerance = max(shape.BoundBox.DiagonalLength * 1e-7, 1e-7)
    chosen = [int(n[4:]) - 1 for n in names if n.startswith("Edge")]
    seen, waiting = set(chosen), list(chosen)
    kind = {i: _convex_edge(shape, edges[i]) for i in chosen}
    while waiting:
        index_from = waiting.pop()
        edge = edges[index_from]
        for index, other in enumerate(edges):
            if index in seen:
                continue
            at = _runs_on(edge, other, tolerance)
            if at is None or not _faces_run_on(shape, edge, other, at):
                continue
            if not _sharp(shape, other):
                end = fade.fading_end(shape, other) if fading else None
                if end is None or _near(end, at, tolerance):
                    continue
            kind[index] = _convex_edge(shape, other)
            if kind[index] != kind[index_from]:
                continue
            seen.add(index)
            waiting.append(index)
    return names + ["Edge%d" % (i + 1) for i in sorted(seen - set(chosen))]


def _chain_joints(shape: Any, edges: list[Any]) -> list[App.Vector]:
    tolerance = max(shape.BoundBox.DiagonalLength * 1e-7, 1e-7)
    joints = []
    for i, a in enumerate(edges):
        for b in edges[i + 1:]:
            at = _runs_on(a, b, tolerance)
            if at is not None:
                joints.append(at)
    return joints


def _parallel(a: App.Vector, b: App.Vector) -> bool:
    a, b = App.Vector(a), App.Vector(b)
    a.normalize()
    b.normalize()
    return abs(a.dot(b)) > 1 - AXIS_TOLERANCE


def _on_axis(point: App.Vector, circle: Any) -> bool:
    offset = point - circle.Center
    along = circle.Axis * offset.dot(circle.Axis)
    return (offset - along).Length < circle.Radius * AXIS_TOLERANCE


def _coaxial(face: Any, circle: Any) -> bool:
    """Whether the face is turned about the circle's axis.

    A plane across the axis, or a cylinder, cone, sphere or torus on it.
    """
    surface = face.Surface
    if isinstance(surface, Part.Plane):
        return _parallel(surface.Axis, circle.Axis)
    if isinstance(surface, Part.Sphere):
        return _on_axis(surface.Center, circle)
    if isinstance(surface, Part.Cone):
        return (_parallel(surface.Axis, circle.Axis)
                and _on_axis(surface.Apex, circle))
    if isinstance(surface, (Part.Cylinder, Part.Toroid)):
        return (_parallel(surface.Axis, circle.Axis)
                and _on_axis(surface.Center, circle))
    return False


def _revolved(shape: Any, faces: list[Any], edge: Any,
              radius: float) -> tuple[Any, bool]:
    """Exact: the section turned about a circular edge's axis."""
    circle = edge.Curve
    sweep = edge.LastParameter - edge.FirstParameter
    try:
        face, convex, centre = _walked(shape, edge,
                                       edge.FirstParameter + sweep / 2,
                                       radius)
        half = -math.degrees(sweep / 2)
        face.rotate(circle.Center, circle.Axis, half)
        spin = App.Rotation(circle.Axis, half)
        centre = circle.Center + spin.multVec(centre - circle.Center)
    except ValueError as exc:
        App.Console.PrintWarning("Nxt fillet: %s; using the edge's own "
                                 "faces only\n" % exc)
        station, convex = _first_station(faces, edge, radius)
        face, centre = Part.Face(_section(station, radius)), station.centre
    if edge.isClosed() or sweep >= FULL_TURN - AXIS_TOLERANCE:
        return face.revolve(circle.Center, circle.Axis, 360.0), convex

    def turned(angle: float) -> App.Vector:
        spin = App.Rotation(circle.Axis, math.degrees(angle))
        return circle.Center + spin.multVec(centre - circle.Center)

    reach = min(radius / circle.Radius, (FULL_TURN - sweep) / 2)
    ends = (edge.valueAt(edge.FirstParameter),
            edge.valueAt(edge.LastParameter))
    if convex:
        near = radius * WALK_TOLERANCE * 10
        back = reach if (_open_beyond(shape, turned(-reach / 2))
                         or _mitre(shape, edge, ends[0])) \
            and not _joined(ends[0], near) else 0.0
        forth = reach if (_open_beyond(shape, turned(sweep + reach / 2))
                          or _mitre(shape, edge, ends[1])) \
            and not _joined(ends[1], near) else 0.0
    else:
        most = (FULL_TURN - sweep) / 2
        back, forth = (min(_end_reach(shape, faces, edge, at, radius)
                           / circle.Radius, most) for at in ends)
    face.rotate(circle.Center, circle.Axis, -math.degrees(back))
    angle = math.degrees(sweep + back + forth)
    return face.revolve(circle.Center, circle.Axis, angle), convex


def _lofted(shape: Any, faces: list[Any], edge: Any,
            radius: float) -> tuple[Any, bool]:
    """Approximate: sections lofted along any other edge."""
    stations: list[Station] = []
    convex = None
    for u in _parameters(edge, radius):
        found = _station(faces[0], faces[1], edge, u, radius, convex)
        if found is None:
            raise ValueError("the faces meet tangentially")
        station, convex = found
        stations.append(station)
    closed = edge.isClosed()
    if not closed:
        first, last = stations[0], stations[-1]
        if convex:
            near = radius * WALK_TOLERANCE * 10
            # Only into empty space: past an end that meets more of the
            # part, the cut would gouge it.
            ahead = radius / 2
            back = radius if not _joined(first.point, near) and (
                _open_beyond(shape, first.centre - first.tangent * ahead)
                or _mitre(shape, edge, first.point)
                or _slanted_end(shape, edge, first.point, first.tangent)
            ) else 0.0
            forth = radius if not _joined(last.point, near) and (
                _open_beyond(shape, last.centre + last.tangent * ahead)
                or _mitre(shape, edge, last.point)
                or _slanted_end(shape, edge, last.point, last.tangent)
            ) else 0.0
        else:
            back = _end_reach(shape, faces, edge, first.point, radius)
            forth = _end_reach(shape, faces, edge, last.point, radius)
    else:
        back = forth = 0.0
    # A short run past an end goes into the loft, its surface carried on;
    # a long one is added straight after, as a section far out would bend
    # the loft's surface wildly between it and the last real one.
    if 0 < back <= radius:
        stations.insert(0, _shifted(stations[0],
                                    stations[0].tangent * -back))
        back = 0.0
    if 0 < forth <= radius:
        stations.append(_shifted(stations[-1], stations[-1].tangent * forth))
        forth = 0.0
    App.Console.PrintWarning("Nxt fillet: a %s edge is approximated\n"
                             % type(edge.Curve).__name__)
    # The sections' corners are pushed past the edge; round a tight bend
    # they would cross, and the loft fold through itself: less, then.
    bend = _bend(edge)
    for push in (radius, bend / 2, bend / 4, bend / 8):
        wires = [_wide_section(s, radius, push) for s in stations]
        tool = Part.makeLoft(wires, True, False, closed)
        if tool.Volume < 0:
            tool.reverse()
        if bend >= radius * 2 or not _crossed(tool):
            break
    for wire, station, length in ((wires[0], stations[0], -back),
                                  (wires[-1], stations[-1], forth)):
        if not length:
            continue
        end = Part.Face(wire).extrude(station.tangent * length)
        if end.Volume < 0:
            end.reverse()
        longer = tool.fuse(end)
        if len(longer.Solids) == 1 and longer.isValid():
            tool = longer.Solids[0].removeSplitter()
    return tool, bool(convex)


def edge_tool(shape: Any, edge: Any, radius: float) -> tuple[Any, bool]:
    """The material to remove (convex) or add (concave) for one edge."""
    _solid.append(shape)
    try:
        return _edge_tool(shape, edge, radius)
    finally:
        _solid.pop()


def _edge_tool(shape: Any, edge: Any, radius: float) -> tuple[Any, bool]:
    faces = _faces_of(shape, edge)
    if len(faces) != 2:
        raise ValueError("an edge needs exactly two faces")
    curve = edge.Curve
    if isinstance(curve, Part.Line) and all(
            _exact(f, edge.tangentAt(edge.FirstParameter)) for f in faces):
        return _straight(shape, faces, edge, radius)
    if isinstance(curve, Part.Circle) and all(
            _coaxial(f, curve) for f in faces):
        return _revolved(shape, faces, edge, radius)
    return _lofted(shape, faces, edge, radius)


def _outside(face: Any, size: float) -> Any:
    """A block standing on a planar face's plane, on its outer side."""
    point = face.CenterOfMass
    normal = _normal(face, point)
    if _solid and _inside(point + normal * _step()):
        normal = -normal
    helper = App.Vector(0, 0, 1)
    if abs(normal.dot(helper)) > 0.9:
        helper = App.Vector(1, 0, 0)
    across = normal.cross(helper)
    across.normalize()
    upward = normal.cross(across)
    corner = point - across * (size / 2) - upward * (size / 2)
    sheet = Part.makePlane(size, size, corner, normal, across)
    return sheet.extrude(normal * size)


def _clipped(shape: Any, edge: Any, tool: Any, say: Any = None,
             radius: float = 0.0) -> Any:
    _solid.append(shape)
    try:
        return _clipped_by(shape, edge, tool, say, radius)
    finally:
        _solid.pop()


def _clipped_by(shape: Any, edge: Any, tool: Any, say: Any = None,
                radius: float = 0.0) -> Any:
    """Added material kept behind the faces that bound the filleted ones.

    Where a filleted face ends at a sharp outer edge, the blend stops at
    the next face's surface, extended. At each end of the edge only the
    one of those surfaces that keeps the most applies: the blend runs on
    as long as either face still carries it, as other CAD systems do.
    """
    size = shape.BoundBox.DiagonalLength * 4
    ends = (edge.valueAt(edge.FirstParameter),
            edge.valueAt(edge.LastParameter))
    near = max(edge.Length * 1e-6, 1e-7)
    along: list[tuple[Any, App.Vector, Any]] = []
    at_end: tuple[list[Any], list[Any]] = ([], [])
    faces = _faces_of(shape, edge)
    reach = max(edge.Length * 1e-4, 1e-4)
    for face in faces:
        other = faces[1] if face.isSame(faces[0]) else faces[0]
        for rim in face.Edges:
            if rim.isSame(edge):
                continue
            beyond = [f for f in _faces_of(shape, rim)
                      if not f.isSame(face)]
            if len(beyond) != 1 or not _trimming(beyond[0]):
                continue
            # A rim the blend never reaches bounds none of it: extended,
            # its face could still cut the blend away elsewhere.
            if _apart(rim, tool, reach) or \
                    rim.distToShape(tool)[0] > reach:
                continue
            middle = (rim.FirstParameter + rim.LastParameter) / 2
            point = rim.valueAt(middle)
            tangent = rim.tangentAt(middle).normalize()
            n1, n2 = _normal(face, point), _normal(beyond[0], point)
            if 1 - abs(n1.dot(n2)) < MIN_TURN:
                continue
            if not _is_convex(face, point, tangent, n1, n2):
                continue
            touching = [k for k, end in enumerate(ends)
                        if any((v.Point - end).Length < near
                               for v in rim.Vertexes)]
            trim = (beyond[0], point, rim)
            if len(touching) == 1:
                if not isinstance(beyond[0].Surface, TRIMMING[:-1]):
                    # An earlier blend trims by its tangent plane: taken
                    # at the end it trims, where it matters.
                    trim = (beyond[0], ends[touching[0]], rim)
                at_end[touching[0]].append((trim, other))
            else:
                along.append(trim)

    def cut(tool: Any, trim: tuple[Any, App.Vector, Any]) -> Any:
        face, point, rim = trim
        if isinstance(face.Surface, Part.Plane):
            kept = tool.cut(_outside(face, size))
        elif isinstance(face.Surface, Part.BSplineSurface):
            kept = _past_rim(tool, face, rim, point, size)
        else:
            kept = _behind(tool, face, point, size)
        if say is not None:
            say("    trim at %s rim %s by %s: %.4g -> %.4g\n" % (
                type(rim.Curve).__name__, point,
                type(face.Surface).__name__, tool.Volume, kept.Volume))
        return kept

    # A face reached through several rims trims once; one met at an end
    # is that end's candidate only, never a side trim as well.
    ending = [t[0][0] for trims in at_end for t in trims]
    seen: list[Any] = []
    for trim in along:
        if any(trim[0].isSame(f) for f in ending + seen):
            continue
        seen.append(trim[0])
        tool = cut(tool, trim)
    tolerance = max(edge.Length * 1e-5, 1e-6)
    for trims in at_end:
        if not trims:
            continue
        # An end surface that, extended, slices through the other face
        # would cut away blend that face still carries.
        closing = [trim for trim, other in trims
                   if not _slices(trim[0], trim[1], other, size, tolerance)]
        if closing:
            for trim in closing:
                tool = cut(tool, trim)
            if say is not None:
                say("    end trims that close it leave %.4g\n"
                    % tool.Volume)
        else:
            tool = max((cut(tool, t) for t, _other in trims),
                       key=lambda kept: kept.Volume)
            if say is not None:
                say("    kept the end trim leaving %.4g\n" % tool.Volume)
    return tool


def _past_rim(tool: Any, face: Any, rim: Any, at: App.Vector,
              size: float) -> Any:
    """The tool less what lies past an earlier blend's rim.

    The sheet swept from the rim straight across the blend, both ways:
    it holds the rim exactly, so nothing of the face beside it is left.
    """
    from BOPTools import SplitAPI
    outward = _normal(face, at)
    if _solid and _inside(at + outward * _step()):
        outward = -outward
    along = rim.tangentAt(rim.Curve.parameter(at))
    across = outward.cross(along)
    across.normalize()
    start = Part.Edge(rim)
    start.translate(across * -size)
    sheet = start.extrude(across * (2 * size))
    pieces = SplitAPI.slice(tool, [sheet], "Split").Solids
    if len(pieces) < 2:
        return tool.cut(_half_space(at, outward, size))
    return Part.makeCompound([
        piece for piece in pieces
        if (piece.CenterOfMass - _foot(sheet, piece.CenterOfMass)[0])
        .dot(outward) <= 0])


def _extended(face: Any, near: App.Vector, size: float) -> Any:
    """The face's surface, planes included, extended well past the part."""
    surface = face.Surface
    if isinstance(surface, Part.Plane):
        u, v = surface.parameter(near)
        return surface.toShape(u - size, u + size, v - size, v + size)
    return _sheet(face, near, size)


def _slices(face: Any, near: App.Vector, other: Any, size: float,
            tolerance: float) -> bool:
    """Whether `face`'s extended surface runs through `other`'s inside.

    Meeting it only along its boundary does not count.
    """
    try:
        crossing = other.section(_extended(face, near, size))
    except Exception:  # noqa: BLE001 - cannot tell: let it trim
        return False
    surface, across_surface = face.Surface, other.Surface
    step = max(other.BoundBox.DiagonalLength * 1e-3, tolerance * 10)

    def side(point: App.Vector) -> float:
        u, v = surface.parameter(point)
        return (point - surface.value(u, v)).dot(surface.normal(u, v))

    for piece in crossing.Edges:
        if piece.Length < tolerance:
            continue
        at = piece.valueAt(_middle(piece))
        if min(rim.distToShape(Part.Vertex(at))[0] for rim in other.Edges) \
                <= tolerance:
            continue
        # Through, not merely touching: `other` lies on both sides.
        across = _normal(other, at).cross(piece.tangentAt(_middle(piece)))
        if across.Length < 1e-12:
            continue
        across.normalize()
        sides = []
        for sign in (1, -1):
            u, v = across_surface.parameter(at + across * (sign * step))
            sides.append(side(across_surface.value(u, v)))
        if sides[0] * sides[1] < 0:
            return True
    return False


#: Surfaces a blend can be trimmed by: a plane by its half-space, the
#: others by splitting along their whole, extended surface.
TRIMMING = (Part.Plane, Part.Cylinder, Part.Cone, Part.Sphere, Part.Toroid,
            Part.BSplineSurface)


def _trimming(face: Any) -> bool:
    return isinstance(face.Surface, TRIMMING)


def _sheet(face: Any, near: App.Vector, size: float) -> Any:
    """The face's surface, extended well past the part around `near`."""
    surface = face.Surface
    turn = 2 * math.pi
    if isinstance(surface, Part.Sphere):
        return surface.toShape(0, turn, -math.pi / 2, math.pi / 2)
    if isinstance(surface, Part.Toroid):
        return surface.toShape(0, turn, 0, turn)
    v = surface.parameter(near)[1]
    low, high = v - size, v + size
    if isinstance(surface, Part.Cone):
        # Not across the apex, where the cone turns back on itself.
        apex = surface.parameter(surface.Apex)[1]
        gap = size * 1e-6
        if apex < v:
            low = max(low, apex + gap)
        else:
            high = min(high, apex - gap)
    u0, u1 = face.ParameterRange[:2]
    smooth = [u1 - u0 < turn - 1e-6 and _runs_smoothly(face, u)
              for u in (u0, u1)]
    if not any(smooth):
        return surface.toShape(0, turn, low, high)
    # Where the face runs smoothly into the next, as a round into the
    # faces it blends, its surface carries on as the plane tangent there,
    # not on round; elsewhere it carries on round as itself.
    spare = (turn - (u1 - u0)) / 2 * 0.95
    first = u0 if smooth[0] else u0 - spare
    last = u1 if smooth[1] else u1 + spare
    return Part.makeShell([surface.toShape(first, last, low, high)]
                          + [_tangent_strip(surface, u, low, high, size,
                                            1.0 if u == u1 else -1.0)
                             for u, on in zip((u0, u1), smooth) if on])


def _runs_smoothly(face: Any, u: float) -> bool:
    """Whether the face meets the next one tangentially at its side `u`.

    `u` is an angle round the axis of the face's cylinder or cone.
    """
    if not _solid:
        return False
    surface = face.Surface
    turn = 2 * math.pi
    for edge in face.Edges:
        point = edge.valueAt((edge.FirstParameter + edge.LastParameter) / 2)
        at = surface.parameter(point)[0]
        if abs((at - u + math.pi) % turn - math.pi) > 1e-6:
            continue
        for other in _faces_of(_solid[-1], edge):
            if other.isSame(face):
                continue
            n1, n2 = _normal(face, point), _normal(other, point)
            if 1 - abs(n1.dot(n2)) < MIN_TURN:
                return True
    return False


def _tangent_strip(surface: Any, u: float, low: float, high: float,
                   size: float, onward: float) -> Any:
    """The plane tangent to `surface` along its line at `u`.

    Carried `size` onward from it, between `low` and `high` along it.
    """
    corners = []
    for v in (low, high):
        point = surface.value(u, v)
        du = surface.tangent(u, v)[0]
        du.normalize()
        corners.append((point, point + du * (size * onward)))
    (a, b), (c, d) = corners
    strip = Part.Face(Part.makePolygon([a, b, d, c, a]))
    along = surface.normal(u, (low + high) / 2)
    if strip.normalAt(0, 0).dot(along) < 0:
        strip.reverse()
    return strip


def _behind(tool: Any, face: Any, near: App.Vector, size: float) -> Any:
    """The tool less whatever lies outside a curved face's surface."""
    from BOPTools import SplitAPI
    surface = face.Surface
    if isinstance(surface, Part.BSplineSurface):
        # An earlier blend: its own surface, which runs a little past the
        # face, if that reaches across the tool; else its tangent plane.
        outward = _normal(face, near)
        if _solid and _inside(near + outward * _step()):
            outward = -outward
        sheet = surface.toShape(*surface.bounds())
        pieces = SplitAPI.slice(tool, [sheet], "Split").Solids
        if len(pieces) > 1:
            return Part.makeCompound([
                piece for piece in pieces
                if (piece.CenterOfMass - _foot(sheet, piece.CenterOfMass)[0])
                .dot(outward) <= 0])
        return tool.cut(_half_space(near, outward, size))
    outward = _normal(face, near)
    if _solid and _inside(near + outward * _step()):
        outward = -outward
    raw = surface.normal(*surface.parameter(near))
    sign = 1.0 if raw.dot(outward) > 0 else -1.0
    sheet = _sheet(face, near, size)
    pieces = SplitAPI.slice(tool, [sheet], "Split")
    kept = []
    for piece in pieces.Solids:
        centre = piece.CenterOfMass
        if not piece.isInside(centre, 1e-7, True):
            kept.append(piece)
            continue
        if (centre - _foot(sheet, centre)[0]).dot(
                _foot(sheet, centre)[1] * sign) <= 0:
            kept.append(piece)
    return Part.makeCompound(kept)


def _foot(sheet: Any, point: App.Vector) -> tuple[App.Vector, App.Vector]:
    """The nearest point of the sheet to `point`, and its normal there.

    Each face's normal is turned the way the curved one's runs.
    """
    best = min(sheet.Faces,
               key=lambda f: f.distToShape(Part.Vertex(point))[0])
    foot = best.distToShape(Part.Vertex(point))[1][0][0]
    u, v = best.Surface.parameter(foot)
    return foot, best.normalAt(u, v)


def _within(tool: Any, shape: Any) -> Any:
    """Added material kept inside the part's bounding box.

    A radius too big for the faces would otherwise carry their planes
    out past the part.
    """
    box = shape.BoundBox
    if min(box.XLength, box.YLength, box.ZLength) <= 0:
        return tool
    bounds = Part.makeBox(box.XLength, box.YLength, box.ZLength,
                          App.Vector(box.XMin, box.YMin, box.ZMin))
    return tool.common(bounds)


def _ball_for(shape: Any, edge: Any, distance: float) -> float:
    """The ball whose contacts lie `distance` from the edge on its faces.

    Its chord is then an equal-distance chamfer; exact between planes.
    """
    faces = _faces_of(shape, edge)
    if len(faces) != 2:
        raise ValueError("an edge needs exactly two faces")
    middle = edge.valueAt(_middle(edge))
    n1, n2 = _normal(faces[0], middle), _normal(faces[1], middle)
    _solid.append(shape)
    try:
        found = _oriented(middle, n1, n2)
    finally:
        _solid.pop()
    if found is not None:
        n1, n2 = found[1], found[2]
    cosine = max(-1.0, min(1.0, n1.dot(n2)))
    if 1 - abs(cosine) < MIN_TURN:
        raise ValueError("the faces meet tangentially")
    return distance / math.sqrt((1 - cosine) / (1 + cosine))


def fillet(shape: Any, edges: list[Any], radius: float | list[float],
           flat: bool = False, refine: bool = True,
           limits: dict[int, float] | None = None,
           mended: bool = True) -> tuple[Any, list[str]]:
    """The shape with every edge it can fillet rounded, and what failed.

    With `flat`, a chamfer instead, `radius` being its distance; one
    for all edges, or one per edge. Each edge that failed for want of
    room gets, in `limits`, the largest size that stays on its own
    faces, 0 where none does. Without `mended`, a quick preview: the
    finished faces' tolerances are not mended.
    """
    sizes = (list(radius) if isinstance(radius, (list, tuple))
             else [radius] * len(edges))
    from . import fillet_fade as fade
    fading = [i for i, e in enumerate(edges)
              if not flat and fade.fades(shape, e)]
    kept = [i for i in range(len(edges)) if i not in fading]
    if "occt_first" in SPEED and not fading:
        quick = _occt_made(shape, edges, sizes, flat, refine)
        if quick is not None:
            return quick, []
    _flat.append(flat)
    _held.append(not mended)
    _joints.append(_chain_joints(shape, edges))
    fade.begin(edges)
    _oriented_seen.clear()
    _faulty_seen.clear()
    reason, dropped = "", -1
    try:
        result, problems, failed = _joined_up(
            shape, [edges[i] for i in kept], [sizes[i] for i in kept], flat)
        for i in fading:
            try:
                with timed("fading round"):
                    result = fade.applied(shape, result, edges[i], sizes[i])
            except Exception as exc:  # noqa: BLE001 - without it then
                result, reason, dropped = None, str(exc), i
                break
    finally:
        _flat.pop()
        _held.pop()
        _joints.pop()
        fade.end()
    if result is None:
        # A fading crease's round would not go in: as if it had not run
        # on from the chosen ones, its lead's round run to its end.
        App.Console.PrintLog("Nxt fillet: fading rounds dropped: %s\n"
                             % reason)
        rest = [i for i in range(len(edges)) if i != dropped]
        found: dict[int, float] = {}
        result, problems = fillet(
            shape, [edges[i] for i in rest], [sizes[i] for i in rest],
            flat, refine, found if limits is not None else None, mended)
        if limits is not None:
            limits.update({rest[i]: v for i, v in found.items()})
        return result, [_renumbered(p, rest) for p in problems] + [
            "edge %d: %s (%s)" % (dropped + 1, NO_RUN_OUT, reason)]
    if fading:
        problems = [_renumbered(p, kept) for p in problems]
        failed = [kept[i] for i in failed]
    if limits is not None:
        for index in failed:
            limits[index] = largest(shape, edges[index], sizes[index],
                                    flat) or 0.0
    if flat and not (_point_corners and _point_corners[-1]):
        with timed("corners"):
            result = _corner_facets(shape, edges, sizes, result)
    # Only the faces this feature made or changed: the rest of the part
    # was checked by the features that made it, so a long tree is not
    # checked over again at every fillet in it.
    if refine and mended:
        # The refined part is checked anyway: the unrefined one only
        # when the refined one will not do.
        with timed("refined"):
            refined = _cones_joined(result.removeSplitter())
        with timed("edges joined"):
            refined, refined_sound = _tolerant_sound(
                _edges_joined(refined), kept=shape)
        if refined_sound and refined.isValid():
            return refined, problems
        with timed("checked"):
            result, sound = _tolerant_sound(result, kept=shape)
        if (refined.isValid() or not result.isValid()) and (
                refined_sound or not sound):
            result = refined
        return result, problems
    sound = True
    if mended:
        with timed("checked"):
            result, sound = _tolerant_sound(result, kept=shape)
    if refine:
        with timed("refined"):
            refined = _cones_joined(result.removeSplitter())
        with timed("edges joined"):
            refined, refined_sound = _tolerant_sound(
                _edges_joined(refined), kept=shape)
        # Refining can merge faces across a seam it then cannot close.
        if (refined.isValid() or not result.isValid()) and (
                refined_sound or not sound):
            result = refined
    return result, problems


def _occt_made(shape: Any, edges: list[Any], sizes: list[float],
               flat: bool, refine: bool) -> Any:
    """OCCT's own fillet or chamfer where likely to match ours; else None.

    Used only when it comes out sound. Likely: one size, no fades, and
    every edge of one kind (all outer or all inner), so no corner mixes
    the two.
    """
    if len(set(sizes)) != 1 or not edges:
        return None
    kinds = {_convex_edge(shape, e) for e in edges}
    if len(kinds) != 1 or None in kinds:
        return None
    try:
        made = (shape.makeChamfer(sizes[0], edges) if flat
                else shape.makeFillet(sizes[0], edges))
    except Exception:  # noqa: BLE001 - ours then
        return None
    if not made.isValid() or len(made.Solids) != len(shape.Solids):
        return None
    if refine:
        made = _edges_joined(_cones_joined(made.removeSplitter()))
    made, sound = _tolerant_sound(made, kept=shape)
    if not sound or not made.isValid():
        return None
    return made


def _renumbered(problem: str, kept: list[int]) -> str:
    """A problem about the n-th of `kept` edges, about its own number."""
    head, sep, rest = problem.partition(":")
    words = head.split()
    if sep and len(words) == 2 and words[0] == "edge" \
            and words[1].isdigit() and 0 < int(words[1]) <= len(kept):
        return "edge %d:%s" % (kept[int(words[1]) - 1] + 1, rest)
    return problem


#: A chamfer's corner styles: a triangular facet where three chamfered
#: outer edges meet, or the chamfers running to a point.
CORNERS = ("Triangle", "Point")
#: Whether the chamfer being solved runs its corners to a point.
_point_corners: list[bool] = []


def _corner_facets(shape: Any, edges: list[Any], sizes: list[float],
                   result: Any) -> Any:
    """Each corner of three chamfered edges closed by a triangle.

    Cut off at an outer corner, filled in at an inner one.

    Its points are where the chamfers cross on each face at the corner,
    as other CAD systems' chamfers have it.
    """
    tolerance = max(shape.BoundBox.DiagonalLength * 1e-7, 1e-7)
    for vertex in shape.Vertexes:
        meeting = [i for i, e in enumerate(edges)
                   if any((v.Point - vertex.Point).Length < tolerance
                          for v in e.Vertexes)]
        if len(meeting) != 3 or len(_edges_at(shape, vertex)) != 3:
            continue
        convex = {_convex_edge(shape, edges[i]) for i in meeting}
        if len(convex) != 1 or None in convex or not all(
                isinstance(edges[i].Curve, Part.Line) for i in meeting):
            continue
        outer = bool(convex.pop())
        # Where each pair's chamfers cross on the face the pair bounds.
        away = {i: _leaving(edges[i], vertex.Point) for i in meeting}
        points = [vertex.Point + away[j] * sizes[k] + away[k] * sizes[j]
                  for j, k in ((meeting[0], meeting[1]),
                               (meeting[1], meeting[2]),
                               (meeting[2], meeting[0]))]
        try:
            # Cut off an outer corner; fill an inner one.
            corner = _tetrahedron(vertex.Point, points)
            cut = _applied(result, corner, outer)
        except Exception:  # noqa: BLE001 - the corner stays pointed
            continue
        if cut is not None:
            result = cut
    return result


def _edges_at(shape: Any, vertex: Any) -> list[Any]:
    return [e for e in shape.Edges
            if any(v.isSame(vertex) for v in e.Vertexes)]


def _tetrahedron(apex: App.Vector, base: list[App.Vector]) -> Any:
    corners = [apex] + base
    faces = [Part.Face(Part.makePolygon([corners[a], corners[b],
                                         corners[c], corners[a]]))
             for a, b, c in ((0, 1, 2), (0, 2, 3), (0, 3, 1), (1, 2, 3))]
    solid = Part.Solid(Part.Shell(faces))
    if solid.Volume < 0:
        solid.reverse()
    return solid


#: Edge tolerances tried, in turn, on a face whose edges stray from it.
TOLERANCES = (1e-5, 1e-4, 1e-3, 1e-2)


#: Speed experiments switched on, by name: occt_first. Off by default.
SPEED: set[str] = set()

#: Faces already checked, by hash: the same face is not checked twice.
_faulty_seen: dict[tuple[int, float], list[tuple[Any, bool]]] = {}


def _faulty(face: Any) -> bool:
    # Mending widens edge tolerances in place: a mended face is new.
    key = (face.hashCode(), sum(e.Tolerance for e in face.Edges))
    for seen, faulty in _faulty_seen.get(key, ()):
        if seen.isSame(face):
            return faulty
    try:
        face.check(True)
        faulty = False
    except Exception:  # noqa: BLE001 - any fault the check reports
        faulty = True
    _faulty_seen.setdefault(key, []).append((face, faulty))
    return faulty


def _sound(shape: Any, whole: bool = False) -> bool:
    """Whether each face passes the boolean check.

    With `whole`, the shape too, faces against each other (slower).
    """
    if whole:
        return not _faulty(shape)
    return not any(_faulty(f) for f in shape.Faces)


#: Whether each shape rounds were applied to was sound, made tolerant, by
#: its hash: asked again for each tool that does not go in cleanly.
_sound_seen: dict[int, bool] = {}


def _sound_as_made(shape: Any) -> bool:
    key = shape.hashCode()
    if key not in _sound_seen:
        if len(_sound_seen) > 64:
            _sound_seen.clear()
        _sound_seen[key] = _sound(_tolerant(shape))
    return _sound_seen[key]


def _faces_by_hash(shape: Any) -> dict[int, list[Any]]:
    found: dict[int, list[Any]] = {}
    for face in shape.Faces:
        found.setdefault(face.hashCode(), []).append(face)
    return found


def _plain(face: Any) -> bool:
    """Whether no boolean can leave the face faulty.

    A plane or cylinder bounded only by lines and circles: its edges lie
    exactly on it.
    """
    if not isinstance(face.Surface, (Part.Plane, Part.Cylinder)):
        return False
    return all(isinstance(e.Curve, (Part.Line, Part.Circle))
               for e in face.Edges if not e.Degenerated)


def _tolerant(shape: Any, near: Any = None) -> Any:
    """The shape with each straying edge's tolerance widened to cover it.

    Edges cut across approximated rounds lie a little off the analytic
    faces they bound; boolean checks then fail later features. With
    `near`, a box, only faces reaching into it are looked at.
    """
    return _tolerant_sound(shape, near)[0]


def _tolerant_sound(shape: Any, near: Any = None,
                    kept: Any = None) -> tuple[Any, bool]:
    """_tolerant's shape, and whether its faces now pass the boolean check.

    As _sound after _tolerant would tell, but checking again only the
    faces mended and those whose edges they share. Faces of `kept`, a
    shape this one was made from, that came through untouched are not
    looked at: the feature that made them checked them.
    """
    untouched = _faces_by_hash(kept) if kept is not None else {}
    looked = [i for i, f in enumerate(shape.Faces)
              if (near is None or near.intersect(f.BoundBox))
              and not any(f.isSame(g) for g in
                          untouched.get(f.hashCode(), ()))]
    faces = shape.Faces
    looked = [i for i in looked if not _plain(faces[i])]
    faulty = [i for i in looked if _faulty(shape.Faces[i])]
    if not faulty:
        return shape, True
    shape = shape.copy()
    faces = shape.Faces
    for i in faulty:
        face = faces[i]
        for tolerance in TOLERANCES:
            for edge in face.Edges:
                if edge.Tolerance < tolerance:
                    edge.fixTolerance(tolerance)
            if not _faulty(face):
                break
    # Widened edges are shared: their other faces are checked again too.
    again = set(faulty)
    for i in faulty:
        for edge in faces[i].Edges:
            for other in shape.ancestorsOfType(edge, Part.Face):
                again.update(j for j in looked if faces[j].isSame(other))
    return shape, not any(_faulty(faces[i]) for i in sorted(again))
    shape = shape.copy()
    for i in faulty:
        face = shape.Faces[i]
        for tolerance in TOLERANCES:
            for edge in face.Edges:
                if edge.Tolerance < tolerance:
                    edge.fixTolerance(tolerance)
            if not _faulty(face):
                break
    return shape


def _same_cone(a: Any, b: Any) -> bool:
    s, t = a.Surface, b.Surface
    return (isinstance(s, Part.Cone) and isinstance(t, Part.Cone)
            and a.Orientation == b.Orientation
            and s.Apex.distanceToPoint(t.Apex) < 1e-7
            and abs(s.SemiAngle - t.SemiAngle) < 1e-9
            and abs(abs(s.Axis.dot(t.Axis)) - 1) < 1e-9)


def _joined_face(a: Any, b: Any) -> Any:
    """One face over a and b, or None if they don't share an edge."""
    inner = {e.hashCode() for e in b.Edges}
    shared = {e.hashCode() for e in a.Edges if e.hashCode() in inner}
    if not shared:
        return None
    edges = [e for e in a.Edges + b.Edges if e.hashCode() not in shared]
    outer = max((Part.Wire(g) for g in Part.sortEdges(edges)),
                key=lambda w: w.BoundBox.DiagonalLength)
    u0, u1, v0, v1 = a.ParameterRange
    p0, p1, q0, q1 = b.ParameterRange
    # The same angle may be counted in another turn on each face.
    turn = 2 * math.pi
    shift = turn * round(((u0 + u1) - (p0 + p1)) / 2 / turn)
    p0, p1 = p0 + shift, p1 + shift
    first, last = min(u0, p0), max(u1, p1)
    margin = min(0.1, (2 * math.pi - (last - first)) / 3)
    sheet = a.Surface.toShape(first - margin, last + margin,
                              min(v0, q0) - 1, max(v1, q1) + 1)
    area = a.Area + b.Area
    for piece in sheet.generalFuse([outer])[0].Faces:
        if abs(piece.Area - area) < 1e-4 * area:
            if piece.Orientation != a.Orientation:
                piece.reverse()
            return piece
    return None


def _cones_joined(shape: Any) -> Any:
    """Refine for cones, which removeSplitter leaves split."""
    tried: set[tuple[int, int]] = set()
    while True:
        for a, b in _cone_pairs(shape, tried):
            face = _joined_face(a, b)
            if face is None:
                continue
            joined = shape.replaceShape([(a, face)]).removeShape([b])
            if not joined.isValid():
                joined = _sewn_solid(joined.Faces)
            if (joined.isValid() and abs(joined.Volume - shape.Volume)
                    < 1e-6 * shape.Volume):
                shape = joined
                break
        else:
            return shape


def _edges_joined(shape: Any) -> Any:
    """The shape with edges split along one curve joined into one.

    Refining merges faces but leaves the vertices that split their edges;
    two edges meeting there between the same faces become one.
    """
    tolerance = max(shape.BoundBox.DiagonalLength * 1e-7, 1e-7)
    at: dict[int, list[Any]] = {}
    for edge in shape.Edges:
        for v in edge.Vertexes:
            at.setdefault(v.hashCode(), []).append(edge)
    sides: dict[int, set[int]] = {}
    for face in shape.Faces:
        for edge in face.Edges:
            sides.setdefault(edge.hashCode(), set()).add(face.hashCode())
    #: Each split edge's hash to the edge it is now part of.
    now: dict[int, Any] = {}
    for vertex in shape.Vertexes:
        pair = at.get(vertex.hashCode(), [])
        if len(pair) != 2 or pair[0].isSame(pair[1]) \
                or sides.get(pair[0].hashCode()) \
                != sides.get(pair[1].hashCode()):
            continue
        a, b = (now.get(e.hashCode(), e) for e in pair)
        merged = _joined_edge(a, b, vertex.Point, tolerance)
        if merged is None:
            continue
        for key, edge in list(now.items()):
            if edge is a or edge is b:
                now[key] = merged
        now[pair[0].hashCode()] = now[pair[1].hashCode()] = merged
    if not now:
        return shape
    faces = []
    for face in shape.Faces:
        if not any(e.hashCode() in now for e in face.Edges):
            faces.append(face)
            continue
        edges: list[Any] = []
        for e in face.Edges:
            edge = now.get(e.hashCode(), e)
            if not any(edge is x for x in edges):
                edges.append(edge)
        rebuilt = _rebuilt(face, edges)
        if rebuilt is None:
            return shape
        faces.append(rebuilt)
    try:
        joined = _sewn_solid(faces)
    except Exception:  # noqa: BLE001 - left split
        return shape
    if (joined.isValid() and len(joined.Faces) == len(shape.Faces)
            and abs(joined.Volume - shape.Volume) < 1e-6 * shape.Volume):
        return joined
    return shape


def _joined_edge(a: Any, b: Any, through: App.Vector,
                 tolerance: float) -> Any:
    """`a` and `b`, meeting at `through` along one curve, as one edge."""
    if type(a.Curve) is not type(b.Curve) or not isinstance(
            a.Curve, (Part.Line, Part.Circle, Part.Ellipse)):
        return None
    curve = a.Curve
    middle = b.valueAt((b.FirstParameter + b.LastParameter) / 2)
    if curve.value(curve.parameter(middle)).distanceToPoint(middle) \
            > tolerance * 10:
        return None
    near = [v.Point for v in a.Vertexes
            if (v.Point - through).Length > tolerance]
    far = [v.Point for v in b.Vertexes
           if (v.Point - through).Length > tolerance]
    if not near or not far:
        return None
    return _span(curve, near[0], through, far[0])


def _span(curve: Any, start: App.Vector, through: App.Vector,
          end: App.Vector) -> Any:
    """The edge along `curve` from `start` through `through` to `end`."""
    t0, tm, t1 = (curve.parameter(p) for p in (start, through, end))
    if curve.isPeriodic():
        period = curve.LastParameter - curve.FirstParameter
        # Unwrap so the middle lies between the ends.
        for t in (t1, t1 + period, t1 - period):
            for m in (tm, tm + period, tm - period):
                if min(t0, t) < m < max(t0, t) and abs(t - t0) < period:
                    return Part.Edge(curve, min(t0, t), max(t0, t))
        return None
    if not min(t0, t1) < tm < max(t0, t1):
        return None
    return Part.Edge(curve, min(t0, t1), max(t0, t1))


def _rebuilt(face: Any, edges: list[Any]) -> Any:
    """A face on `face`'s surface bounded by `edges`; None if not."""
    try:
        wires = [Part.Wire(g) for g in Part.sortEdges(edges)]
        if isinstance(face.Surface, Part.Plane):
            made = Part.makeFace(wires, "Part::FaceMakerBullseye")
            pieces = made.Faces
        else:
            u0, u1, v0, v1 = face.ParameterRange
            margin = (min(0.1, (2 * math.pi - (u1 - u0)) / 3)
                      if face.Surface.isUPeriodic() else 1.0)
            sheet = face.Surface.toShape(u0 - margin, u1 + margin,
                                         v0 - 1, v1 + 1)
            pieces = sheet.generalFuse(wires)[0].Faces
    except Exception:  # noqa: BLE001 - left as it was
        return None
    for piece in pieces:
        if abs(piece.Area - face.Area) < 1e-4 * face.Area:
            if (_normal(piece, piece.CenterOfMass)
                    .dot(_normal(face, face.CenterOfMass)) < 0):
                piece.reverse()
            return piece
    return None


def _sewn_solid(faces: list[Any]) -> Any:
    shell = Part.Shell(faces)
    shell.sewShape()
    solid = Part.Solid(Part.Shell(shell.Faces))
    if solid.Volume < 0:
        solid.reverse()
    return solid


def _cone_pairs(shape: Any, tried: set[tuple[int, int]]) -> Iterator[Any]:
    faces = shape.Faces
    for i, a in enumerate(faces):
        for b in faces[i + 1:]:
            key = (a.hashCode(), b.hashCode())
            if key not in tried and _same_cone(a, b):
                tried.add(key)
                yield a, b


#: For each edge's index, the planes its round stops at short of a
#: junction: a point on the plane and the side to drop.
_stops: list[dict[int, list[tuple[Any, Any]]]] = []


def _joined_up(shape: Any, edges: list[Any], sizes: list[float],
               flat: bool) -> tuple[Any, list[str], list[int]]:
    """The rounds, blended where they meet; plain rounds if that fails."""
    from . import fillet_junction as junction
    with timed("junctions planned"):
        plans = junction.plan(shape, edges, sizes)
        if flat:
            # Chamfers meet at corners by their own facets; only where an
            # outer one runs on into an inner one is a blend needed.
            plans = [p for p in plans if p.centre is None and len(
                {_convex_edge(shape, a.edge) for a in p.arms}) > 1]
    if not plans:
        with timed("rounds"):
            return _blended(shape, edges, sizes, flat)
    _stops.append(junction.trims(plans))
    try:
        with timed("rounds"):
            result, problems, failed = _blended(shape, edges, sizes, flat)
    finally:
        _stops.pop()
    try:
        for plan in plans:
            with timed("junction blended"):
                result = junction.applied(result, plan)
        if result.isValid() and len(result.Solids) == len(shape.Solids):
            result = _tolerant(result)
            if _sound(result):
                return result, problems, failed
            reason = "the blend fails the boolean check"
        else:
            reason = "the blended result is not a valid solid"
    except Exception as exc:  # noqa: BLE001 - fall back to plain rounds
        reason = str(exc)
    App.Console.PrintWarning("Nxt fillet: rounds left unblended where "
                             "they meet: %s\n" % reason)
    return _blended(shape, edges, sizes, flat)


def largest(shape: Any, edge: Any, size: float,
            flat: bool = False) -> float | None:
    """The largest size up to `size` that stays on the edge's own faces.

    None where nothing fits, or the edge cannot be judged.
    """
    faces = _faces_of(shape, edge)
    if len(faces) != 2:
        return None
    _solid.append(shape)
    try:
        ball = _ball_for(shape, edge, size) if flat else size
        found = _largest_fit(faces, edge, ball) * (size / ball)
    except Exception:  # noqa: BLE001 - no limit to offer
        return None
    finally:
        _solid.pop()
    return found if found > size * FIT_TOLERANCE else None


def _blended(shape: Any, edges: list[Any], sizes: list[float],
             flat: bool) -> tuple[Any, list[str], list[int]]:
    problems: list[str] = []
    failed: list[int] = []
    cuts: list[tuple[int, Any]] = []
    fuses: list[tuple[int, Any]] = []
    for index, edge in enumerate(edges):
        size = sizes[index]
        try:
            radius = _ball_for(shape, edge, size) if flat else size
        except Exception as exc:  # noqa: BLE001 - reported per edge
            problems.append("edge %d: %s" % (index + 1, exc))
            failed.append(index)
            continue
        (cuts if _convex_edge(shape, edge) is not False
         else fuses).append((index, radius))
    # One tool at a time, each checked: a boolean that goes wrong drops
    # its edge, rather than the whole part.
    _edges.append(edges)
    try:
        return _rounded_all(shape, edges, sizes, cuts + fuses, problems,
                            failed)
    finally:
        _edges.pop()


def _rounded_all(shape: Any, edges: list[Any], sizes: list[float],
                 order: list[tuple[int, float]], problems: list[str],
                 failed: list[int]) -> tuple[Any, list[str], list[int]]:
    """Every edge's tool applied: each chain of rounds as one tool.

    Rounds running on into each other meet face to face at their ends;
    cut one after another, those faces upset the booleans. Fused first,
    they go in as one. A chain that will not go in whole goes in edge by
    edge, and an edge that will not go in at all is skipped.
    """
    built: dict[int, tuple[Any, bool, list[str]]] = {}
    for index, radius in order:
        try:
            made = _finished_tool(shape, edges[index], sizes[index], radius)
        except Exception as exc:  # noqa: BLE001 - reported per edge
            problems.append("edge %d: %s" % (index + 1, exc))
            failed.append(index)
            continue
        if made is None:
            problems.append("edge %d: trimmed away to nothing" % (index + 1))
            failed.append(index)
            continue
        built[index] = made
    if _flat and _flat[-1]:
        _stopped_at_chamfers(shape, edges, built)
    result = shape
    for chain in _chains(edges, [i for i, _r in order if i in built],
                         built):
        convex = built[chain[0]][1]
        tools = [built[i][0] for i in chain]
        done = None
        if len(tools) > 1:
            try:
                whole = tools[0].fuse(tools[1:])
                if whole.isValid():
                    done = _applied(result, whole if convex
                                    else _within(whole, shape), convex)
            except Exception:  # noqa: BLE001 - edge by edge then
                done = None
        if done is not None:
            result = done
            for i in chain:
                problems += ["edge %d: %s" % (i + 1, n) for n in built[i][2]]
            continue
        for i in chain:
            tool = built[i][0]
            one = _applied(result, tool if convex
                           else _within(tool, shape), convex)
            if one is None:
                problems.append("edge %d: %s" % (i + 1, NO_JOIN))
                continue
            result = one
            problems += ["edge %d: %s" % (i + 1, n) for n in built[i][2]]
    return result, problems, failed


def _stopped_at_chamfers(shape: Any, edges: list[Any],
                         built: dict[int, tuple[Any, bool, list[str]]]
                         ) -> None:
    """Outer chamfers cut no further than the inner ones they run into.

    Solved together, an outer chamfer would run on to the face past its
    end and cut away what the inner chamfer's face then stands on; made
    one after the other, it stops at that face. So it stops there.
    """
    tolerance = max(shape.BoundBox.DiagonalLength * 1e-7, 1e-7)
    size = shape.BoundBox.DiagonalLength * 4
    for i, (tool, convex, notes) in list(built.items()):
        if not convex:
            continue
        ends = [v.Point for v in edges[i].Vertexes]
        middle = edges[i].valueAt(_middle(edges[i]))
        for j, (other, other_convex, _n) in built.items():
            shared = [p for p in ends for v in edges[j].Vertexes
                      if (v.Point - p).Length < tolerance]
            if other_convex or not shared:
                continue
            # Running on into each other tangentially, they are blended.
            turn = _leaving(edges[i], shared[0]).dot(
                _leaving(edges[j], shared[0]))
            if 1 - abs(turn) < MIN_TURN:
                continue
            face = _chamfer_face(shape, edges[j], other)
            if face is None:
                continue
            normal = App.Vector(face.Surface.Axis)
            point = face.CenterOfMass
            away = normal * (-1 if (middle - point).dot(normal) > 0 else 1)
            tool = tool.cut(_half_space(point, away, size))
        built[i] = (tool, convex, notes)


def _chamfer_face(shape: Any, edge: Any, tool: Any) -> Any:
    """The slanted face of an inner chamfer's tool; None if not flat."""
    own = _faces_of(shape, edge)
    best = None
    for face in tool.Faces:
        if not isinstance(face.Surface, Part.Plane):
            continue
        normal = App.Vector(face.Surface.Axis)
        if any(isinstance(f.Surface, Part.Plane) and 1 - abs(
                normal.dot(App.Vector(f.Surface.Axis))) < MIN_TURN
               for f in own):
            continue
        if best is None or face.Area > best.Area:
            best = face
    return best


def _chains(edges: list[Any], indices: list[int],
            built: dict[int, tuple[Any, bool, list[str]]]) -> list[list[int]]:
    """The indices grouped into runs of rounds joined end to end."""
    joints = _joints[-1] if _joints else []
    tolerance = max((e.Length for e in edges), default=1.0) * 1e-6
    groups: list[list[int]] = []
    for index in indices:
        ends = [v.Point for v in edges[index].Vertexes]
        joined = [g for g in groups
                  if built[g[0]][1] == built[index][1]
                  and any((p - q).Length < tolerance
                          for i in g for q in (v.Point for v in
                                               edges[i].Vertexes)
                          for p in ends
                          if any((p - j).Length < tolerance
                                 for j in joints))]
        merged = [index]
        for g in joined:
            merged = g + merged
            groups.remove(g)
        groups.append(merged)
    return groups


#: The edges being rounded, to find an edge's index from the edge.
_edges: list[list[Any]] = []


def _index_of(edge: Any) -> int:
    return next((i for i, e in enumerate(_edges[-1]) if e.isSame(edge)),
                -1) if _edges else -1


def _finished_tool(shape: Any, edge: Any, size: float,
                   radius: float) -> tuple[Any, bool, list[str]] | None:
    """The edge's tool, capped or trimmed; None when nothing is left."""
    notes: list[str] = []
    _scale.append(size / radius)
    try:
        tool, convex = edge_tool(shape, edge, radius)
    finally:
        _scale.pop()
    # A loft gone wrong (twisted, or inside out) reaches far from its
    # edge; added or cut, it would swallow the part.
    reach = edge.BoundBox
    reach.enlarge(radius * 6)
    if not reach.isInside(tool.BoundBox) or tool.Volume <= 0:
        raise ValueError("no blend could be built along it")
    if convex:
        try:
            tool = _capped(shape, edge, tool, radius)
        except Exception as exc:  # noqa: BLE001 - best effort
            notes.append("not capped: %s" % exc)
    else:
        try:
            tool = _clipped(shape, edge, tool, radius=radius)
        except Exception as exc:  # noqa: BLE001 - trim is best effort
            notes.append("not trimmed: %s" % exc)
        if not tool.Solids:
            return None
    if not (_flat and _flat[-1]):
        from . import fillet_fade as fade
        _solid.append(shape)
        try:
            tool = fade.handed_over(shape, edge, tool, radius)
        finally:
            _solid.pop()
        if not tool.Solids:
            return None
    if _stops:
        size_all = shape.BoundBox.DiagonalLength * 4
        for point, towards in _stops[-1].get(_index_of(edge), []):
            tool = tool.cut(_half_space(point, towards, size_all))
        if not tool.Solids:
            return None
    return tool, convex, notes


def _capped(shape: Any, edge: Any, tool: Any, radius: float) -> Any:
    """A cut kept on the edge's side of the faces that stop it.

    Those met at its ends, where the edge runs into more of the part.
    Walls rising nearby do not stop it: as in other CAD systems, the
    blend runs the edge's whole length, and what stands on its faces
    keeps its walls, carried straight down into the blend.
    """
    tolerance = max(edge.Length * 1e-6, 1e-7)
    middle = edge.valueAt(_middle(edge))
    own = _faces_of(shape, edge)
    size = shape.BoundBox.DiagonalLength * 4
    stops: list[tuple[Any, App.Vector]] = []

    def add(face: Any, near: App.Vector) -> None:
        if _trimming(face) and not any(face.isSame(f) for f in own) \
                and not any(face.isSame(f) for f, _p in stops):
            stops.append((face, near))

    mitres = []
    # Ends at a junction stop short of it (_stops) and the junction's
    # own blend fills the corner: a mitre there would cut the round back
    # further, leaving a wedge between it and the blend.
    stopped = _stops[-1].get(_index_of(edge), []) if _stops else []
    for vertex in edge.Vertexes:
        if _joined(vertex.Point, tolerance * 10):
            continue
        if any((vertex.Point - point).dot(towards) > 0
               for point, towards in stopped):
            continue
        plane = _mitre(shape, edge, vertex.Point)
        if plane is not None:
            # Two rounds meeting at an angle: each stops at the plane
            # halving it, whatever faces meet there.
            mitres.append(plane)
            continue
        for face in shape.Faces:
            if _far_from(face, vertex.Point, tolerance):
                continue
            if face.distToShape(vertex)[0] <= tolerance:
                add(face, vertex.Point)
    tool = _under_standing(shape, edge, own, tool, radius)
    # A curved edge can wrap round past a plane through its end, which
    # would then cut away its blend on the far side: such a plane cuts
    # only within a ball about that end, and sides are judged there.
    curved = not isinstance(edge.Curve, Part.Line)

    def keep_side(point: App.Vector) -> App.Vector:
        return _inside_near(edge, point, radius) if curved else middle

    def cap(tool: Any, point: App.Vector, away: App.Vector) -> Any:
        block = _half_space(point, away, size)
        if curved:
            block = block.common(Part.makeSphere(radius * CAP_REACH, point))
        return tool.cut(block)

    for point, normal, _faces in mitres:
        side = (keep_side(point) - point).dot(normal)
        away = normal * (-1 if side > 0 else 1)
        tool = cap(tool, point, away)
    for face, near in stops:
        if not isinstance(face.Surface, Part.Plane):
            tool = _on_side_of(tool, face, near, middle, size)
            continue
        normal = App.Vector(face.Surface.Axis)
        side = (keep_side(near) - near).dot(normal)
        if abs(side) < tolerance:
            continue
        away = normal * (-1 if side > 0 else 1)
        tool = cap(tool, near, away)
    return tool


#: How far, in radii, a cap across a curved edge's end reaches.
CAP_REACH = 2


def _inside_near(edge: Any, point: App.Vector, radius: float) -> App.Vector:
    """A point on the edge near `point`, a little in from it.

    Where a stop is met; the side of it the edge runs on.
    """
    at = edge.Curve.parameter(point)
    first, last = edge.FirstParameter, edge.LastParameter
    at = min(max(at, first), last)
    step = (last - first) * min(0.25, radius / max(edge.Length, 1e-9))
    inward = at + step if at - first < last - at else at - step
    return edge.valueAt(inward)


def _mitre(shape: Any, edge: Any, at: App.Vector
           ) -> tuple[App.Vector, App.Vector, list[Any]] | None:
    """The plane halving the corner where another round meets this one.

    Another selected outer edge ending at `at`, at an angle and sharing
    a face with this one: the plane through `at` holding that face's
    normal and the line halving the two edges. Returns its point, its
    normal and the other edge's faces; None if there is no such edge.
    """
    if not _edges:
        return None
    tolerance = max(edge.Length * 1e-6, 1e-7)
    if _joined(at, tolerance * 10) or _convex_edge(shape, edge) is False:
        return None
    own = _faces_of(shape, edge)
    for other in _edges[-1]:
        if other.isSame(edge) or not any(
                (v.Point - at).Length < tolerance for v in other.Vertexes):
            continue
        theirs = _faces_of(shape, other)
        shared = [f for f in own if any(f.isSame(g) for g in theirs)]
        if len(shared) != 1 or _convex_edge(shape, other) is False:
            continue
        mine = _leaving(edge, at)
        yours = _leaving(other, at)
        halfway = mine + yours
        if halfway.Length < 1e-9:
            continue
        normal = _normal(shared[0], at).cross(halfway)
        if normal.Length < 1e-9:
            continue
        normal.normalize()
        return at, normal, theirs
    return None


def _leaving(edge: Any, at: App.Vector) -> App.Vector:
    """The edge's direction away from its end at `at`."""
    first = edge.valueAt(edge.FirstParameter)
    if (first - at).Length < (edge.valueAt(edge.LastParameter) - at).Length:
        tangent = edge.tangentAt(edge.FirstParameter)
    else:
        tangent = -edge.tangentAt(edge.LastParameter)
    tangent.normalize()
    return tangent


def _rises_from(shape: Any, face: Any, rim: Any) -> bool | None:
    """Whether the face across `rim` rises from `face`: an inner corner."""
    beyond = [f for f in _faces_of(shape, rim) if not f.isSame(face)]
    if len(beyond) != 1:
        return None
    middle = _middle(rim)
    point = rim.valueAt(middle)
    tangent = rim.tangentAt(middle).normalize()
    n1, n2 = _normal(face, point), _normal(beyond[0], point)
    if 1 - abs(n1.dot(n2)) < MIN_TURN:
        return False
    _solid.append(shape)
    try:
        return not _is_convex(face, point, tangent, n1, n2)
    except Exception:  # noqa: BLE001 - cannot tell
        return None
    finally:
        _solid.pop()


def _under_standing(shape: Any, edge: Any, own: list[Any], tool: Any,
                    radius: float) -> Any:
    """The tool less what lies under anything standing on its faces.

    A post on one of the edge's flat faces keeps its walls, carried
    straight down into the blend, rather than being undercut by it.
    """
    size = shape.BoundBox.DiagonalLength * 4
    reach = tool.BoundBox
    reach.enlarge(radius)
    middle = edge.valueAt(_middle(edge))
    for face in own:
        if not isinstance(face.Surface, Part.Plane):
            continue
        if not any(reach.intersect(rim.BoundBox)
                   and _rises_from(shape, face, rim)
                   for rim in face.Edges):
            continue
        point = middle
        normal = _normal(face, point)
        step = max(shape.BoundBox.DiagonalLength * 1e-6, 1e-5)
        # Cut just above the face, where the standing part begins.
        level = normal.dot(point) + step * 100
        try:
            above = shape.common(_half_space(point + normal * step * 10,
                                             normal, size))
        except Exception:  # noqa: BLE001 - nothing to keep then
            continue
        for standing in above.Solids:
            if not reach.intersect(standing.BoundBox):
                continue
            try:
                wires = standing.slice(normal, level)
                footprint = Part.Face(wires) if len(wires) > 1 \
                    else Part.Face(wires[0])
                if not _stands_within(face, footprint, normal, level):
                    continue
                column = footprint.extrude(-normal * size)
                tool = tool.cut(column)
            except Exception:  # noqa: BLE001 - leave it undercut
                continue
    return tool


def _stands_within(face: Any, footprint: Any, normal: App.Vector,
                   level: float) -> bool:
    """Whether the footprint lies within the face's outline: on it."""
    outline = Part.Face(face.OuterWire)
    lowered = footprint.translated(
        -normal * (level - normal.dot(face.Vertexes[0].Point)))
    return outline.common(lowered).Area > lowered.Area * 0.999


def _on_side_of(tool: Any, face: Any, near: App.Vector, towards: App.Vector,
                size: float) -> Any:
    """The tool kept on `towards`' side of a curved face's surface."""
    from BOPTools import SplitAPI
    surface = face.Surface

    def side(point: App.Vector) -> float:
        u, v = surface.parameter(point)
        return (point - surface.value(u, v)).dot(surface.normal(u, v))

    wanted = side(towards)
    if abs(wanted) < 1e-9:
        return tool
    pieces = SplitAPI.slice(tool, [_sheet(face, near, size)], "Split")
    kept = [piece for piece in pieces.Solids
            if side(piece.CenterOfMass) * wanted > 0]
    if not kept:
        return tool
    return kept[0] if len(kept) == 1 else Part.makeCompound(kept)


def _half_space(point: App.Vector, outward: App.Vector, size: float) -> Any:
    """A block standing on the plane through `point`, towards `outward`."""
    helper = App.Vector(0, 0, 1)
    if abs(outward.dot(helper)) > 0.9:
        helper = App.Vector(1, 0, 0)
    across = outward.cross(helper)
    across.normalize()
    upward = outward.cross(across)
    corner = point - across * (size / 2) - upward * (size / 2)
    return Part.makePlane(size, size, corner, outward, across).extrude(
        outward * size)


#: How far a boolean's change of volume may stray from its tool's.
BOOLEAN_SLACK = 0.05


def _without_slivers(shape: Any, count: int, smallest: float) -> Any:
    """`shape` less the empty solids a boolean can leave at tangencies."""
    if len(shape.Solids) <= count:
        return shape
    kept = [solid for solid in shape.Solids if solid.Volume > smallest]
    return kept[0] if len(kept) == 1 else Part.makeCompound(kept)


def _applied(shape: Any, tool: Any, cutting: bool) -> Any:
    """`shape` with `tool` cut away or added; None if that is unsound.

    Sound: still solid and valid, and changed by no more than the tool.
    """
    slack = tool.Volume * BOOLEAN_SLACK + 1e-9
    # Plain first; then fuzzy, for faces that lie on one another.
    fuzz = max(shape.BoundBox.DiagonalLength * 1e-7, 1e-6)
    for tolerance in (0.0, fuzz):
        try:
            done = (shape.cut(tool, tolerance) if cutting
                    else shape.fuse(tool, tolerance))
            result = _without_slivers(done, len(shape.Solids),
                                      tool.Volume * 1e-4)
            change = (shape.Volume - result.Volume if cutting
                      else result.Volume - shape.Volume)
            if (len(result.Solids) == len(shape.Solids)
                    and result.isValid()
                    and -slack <= change <= tool.Volume + slack):
                if _held and _held[-1]:
                    return result
                # Only where the tool reached can a face have gone wrong;
                # the rest is the shape's as it was (and the whole is made
                # tolerant once the rounds are done).
                near = tool.BoundBox
                near.enlarge(fuzz * 10)
                result, sound = _tolerant_sound(result, near)
                # Valid but with faces running through each other: no.
                if sound or not _sound_as_made(shape):
                    return result
        except Exception:  # noqa: BLE001 - try the next way
            pass
    return None


def refine_by_default() -> bool:
    """Part Design's "Automatically refine model after operation"."""
    return App.ParamGet("User parameter:BaseApp/Preferences/Mod/"
                        "PartDesign").GetBool("RefineModel", True)


def _same_kind(feature: Any, like: Any) -> bool:
    """`feature` is an Nxt fillet, or chamfer, made as `like` is."""
    proxy = getattr(feature, "Proxy", None)
    mine = getattr(like, "Proxy", None)
    if mine is None or proxy is None or type(proxy) is not type(mine):
        return False
    size = mine.size(like)
    if abs(proxy.size(feature) - size) > size * 1e-6:
        return False
    return getattr(feature, "Corners", None) == getattr(like, "Corners", None)


def _on_earlier(edge: Any, earlier: Any) -> Any:
    """The edge of `earlier` that `edge` lies along, or None."""
    middle = edge.valueAt((edge.FirstParameter + edge.LastParameter) / 2)
    tangent = edge.tangentAt((edge.FirstParameter + edge.LastParameter) / 2)
    tolerance = max(earlier.BoundBox.DiagonalLength * 1e-6, 1e-6)
    for candidate in earlier.Edges:
        if candidate.distToShape(Part.Vertex(middle))[0] > tolerance:
            continue
        try:
            u = candidate.Curve.parameter(middle)
            if abs(abs(candidate.tangentAt(u).dot(tangent)) - 1) < 1e-4:
                return candidate
        except Exception:  # noqa: BLE001 - not this one
            continue
    return None


def _with_earlier(obj: Any, shape: Any, edges: list[Any]
                  ) -> tuple[Any, list[Any]]:
    """The shape and edges to round, an earlier feature taken in.

    Outer edges running into what the Nxt fillet (or chamfer) just
    before made, of the same size, are rounded together with that
    feature's own edges, on its base: the corner they share comes out as
    it would done at once, as in other CAD systems, whatever the order.
    Its other rounds come out as they were. Edges on what it made go
    with it.
    """
    # Outer edges only: a hollow round at the foot of an earlier outer one
    # runs out on it, in turn, as other CAD systems do too.
    if not edges or not all(_convex_edge(shape, e) for e in edges):
        return shape, edges
    size = obj.Proxy.size(obj)
    base = obj.BaseFeature
    first = shape, edges
    while _same_kind(base, obj):
        earlier_base = getattr(base, "BaseFeature", None)
        if earlier_base is None:
            break
        earlier = _usable(earlier_base.Shape)
        made = list(generated_faces(shape, earlier).Faces)
        ends = [v for e in edges for v in e.Vertexes]
        if not made or not any(f.distToShape(v)[0] <= size * 2
                               for f in made for v in ends):
            break
        try:
            theirs = [earlier.getElement(n)
                      for n in base.Proxy.names(base, earlier)]
        except Exception:  # noqa: BLE001 - as they are then
            break
        if not theirs or not all(_convex_edge(earlier, e) for e in theirs):
            break
        tolerance = max(shape.BoundBox.DiagonalLength * 1e-6, 1e-6)
        mine = []
        for edge in edges:
            middle = Part.Vertex(edge.valueAt(
                (edge.FirstParameter + edge.LastParameter) / 2))
            if any(m.distToShape(middle)[0] < tolerance for m in made):
                continue
            found = _on_earlier(edge, earlier)
            if found is None:
                return first
            mine.append(found)
        if not mine:
            # Nothing past what it made: nothing for this one to add.
            return first
        merged = list(mine)
        for edge in theirs:
            if not any(edge.isSame(e) for e in merged):
                merged.append(edge)
        shape, edges, base = earlier, merged, earlier_base
    return shape, edges


class BlendFillet:
    """Document object proxy for the Nxt fillet feature."""

    FLAT = False

    def size(self, obj: Any) -> float:
        return float(obj.Radius)

    GROUP = "Fillet"

    def __init__(self, obj: Any) -> None:
        obj.Proxy = self
        if not hasattr(obj, "Edges"):
            obj.addProperty("App::PropertyLinkSubList", "Edges", "Fillet",
                            "Edges of the base feature to round")
        if not hasattr(obj, "Radius"):
            obj.addProperty("App::PropertyLength", "Radius", "Fillet",
                            "Fillet radius")
            obj.Radius = DEFAULT_RADIUS
        self.complete(obj)

    def complete(self, obj: Any) -> None:
        """The properties added since the first release, on older files."""
        if not hasattr(obj, "UseAllEdges"):
            obj.addProperty("App::PropertyBool", "UseAllEdges", self.GROUP,
                            "Every edge of the base feature")
        if not hasattr(obj, "TangentEdges"):
            obj.addProperty("App::PropertyBool", "TangentEdges", self.GROUP,
                            "Also the edges running on tangentially from "
                            "the picked ones")
            obj.TangentEdges = True
        if not hasattr(obj, "Refine"):
            obj.addProperty("App::PropertyBool", "Refine", self.GROUP,
                            "Merge faces left split by the booleans")
            obj.Refine = refine_by_default()
        if hasattr(obj, "Operation"):
            # Set from the result: whether it adds or removes material.
            obj.setEditorMode("Operation", 2)

    def onDocumentRestored(self, obj: Any) -> None:  # noqa: N802
        self.complete(obj)
        _attach_view_provider(obj, self.FLAT)
        if obj.TypeId == OLD_FEATURE_TYPE:
            from . import fillet_upgrade
            fillet_upgrade.later(obj)

    def names(self, obj: Any, shape: Any) -> list[str]:
        """The edges this feature rounds, as "EdgeN" of its base."""
        if getattr(obj, "UseAllEdges", False):
            return ["Edge%d" % (i + 1) for i in range(len(shape.Edges))]
        names = [name for _owner, names in obj.Edges for name in names]
        if getattr(obj, "TangentEdges", False):
            return tangent_chain(shape, names, not self.FLAT)
        return names

    def execute(self, obj: Any) -> None:
        base = obj.BaseFeature
        if base is None:
            raise ValueError("Nxt fillet has no base feature")
        with timed("%s: edges gathered" % obj.Label):
            # Features apply in order, each on the one before, as in other
            # CAD systems: an earlier one is worked out again only where
            # this one meets it at a corner (_with_earlier).
            shape = _usable(obj.BaseFeature.Shape)
            names = self.names(obj, shape)
            edges = [shape.getElement(n) for n in names]
            own = shape
            shape, edges = _with_earlier(obj, shape, edges)
            sizes = [self.size(obj)] * len(edges)
        # While its task panel is open: no refining (on OK instead), and
        # the size limits the panel shows.
        # While a handle is held: no size limits, nor mending, until it
        # is let go.
        editing = getattr(self, "editing", False)
        dragging = editing and getattr(self, "dragging", False)
        found: dict[int, float] = {}
        with timed("%s: all" % obj.Label):
            result, problems = fillet(
                shape, edges, sizes, self.FLAT,
                getattr(obj, "Refine", True) and not editing,
                found if editing and not dragging and shape is own
                else None,
                mended=not dragging)
        self.problems = problems
        if not dragging:
            #: Edges left sharp: the largest size that fits each, 0 if none.
            self.limits = {names[i]: value for i, value in found.items()}
        for problem in problems:
            App.Console.PrintWarning("%s: skipped %s\n" % (obj.Label, problem))
        if not result.isValid():
            result.fix(1e-7, 1e-7, 1e-7)
        obj.Shape = result
        if not editing:
            self.transform_problem = set_tool(obj, own, result)
            if self.transform_problem and any(
                    o.isDerivedFrom("PartDesign::Transformed")
                    for o in obj.InList):
                App.Console.PrintWarning(
                    "%s cannot be mirrored or patterned: %s\n"
                    % (obj.Label, self.transform_problem))
        if editing and hasattr(obj, "PreviewShape"):
            # Part Design's own preview shows this, as for its dress-ups.
            with timed("preview faces"):
                obj.PreviewShape = generated_faces(result, own)

    def dumps(self) -> None:
        return None

    def loads(self, _state: Any) -> None:
        return None


class BlendChamfer(BlendFillet):
    """Document object proxy for the Nxt chamfer feature."""

    FLAT = True

    GROUP = "Chamfer"

    def __init__(self, obj: Any) -> None:
        obj.Proxy = self
        if not hasattr(obj, "Edges"):
            obj.addProperty("App::PropertyLinkSubList", "Edges", "Chamfer",
                            "Edges of the base feature to bevel")
        if not hasattr(obj, "Size"):
            obj.addProperty("App::PropertyLength", "Size", "Chamfer",
                            "Distance from the edge along each face")
            obj.Size = DEFAULT_RADIUS
        self.complete(obj)

    def size(self, obj: Any) -> float:
        return float(obj.Size)

    def complete(self, obj: Any) -> None:
        super().complete(obj)
        if not hasattr(obj, "Corners"):
            obj.addProperty("App::PropertyEnumeration", "Corners",
                            self.GROUP, "Where three chamfered edges meet "
                            "at an outer corner: a triangular facet, or "
                            "the chamfers running to a point")
            obj.Corners = list(CORNERS)
            obj.Corners = CORNERS[0]

    def execute(self, obj: Any) -> None:
        _point_corners.append(getattr(obj, "Corners", CORNERS[0])
                              == CORNERS[1])
        try:
            super().execute(obj)
        finally:
            _point_corners.pop()


class ViewProviderBlendFillet:
    """Hides the base feature, as PartDesign's own fillet does."""

    ICON = str(ICONS / "NxtFillet.svg")

    def __init__(self, vobj: Any) -> None:
        vobj.Proxy = self

    def attach(self, vobj: Any) -> None:
        self.Object = vobj.Object

    def updateData(self, obj: Any, prop: str) -> None:  # noqa: N802
        if prop == "Shape":
            from . import feature_colors
            feature_colors.carry_face_colors(obj)

    def claimChildren(self) -> list[Any]:  # noqa: N802 - FreeCAD API
        return []

    def getIcon(self) -> str:  # noqa: N802 - FreeCAD API
        return self.ICON

    def setEdit(self, vobj: Any, mode: int = 0) -> bool:  # noqa: N802
        if mode != 0:
            return False
        from . import fillet_task
        return fillet_task.open_for(vobj.Object, created=False)

    def unsetEdit(self, vobj: Any, mode: int = 0) -> bool:  # noqa: N802
        import FreeCADGui as Gui
        Gui.Control.closeDialog()
        return True

    def dumps(self) -> None:
        return None

    def loads(self, _state: Any) -> None:
        return None


class ViewProviderBlendChamfer(ViewProviderBlendFillet):
    ICON = str(ICONS / "NxtChamfer.svg")


#: Where the switch for timing reports lives.
TIMING = ("User parameter:BaseApp/Preferences/Mod/Nxt", "FilletTiming")


@contextmanager
def timed(label: str) -> Iterator[None]:
    """Report how long the step took, when FilletTiming is switched on."""
    if not App.ParamGet(TIMING[0]).GetBool(TIMING[1], False):
        yield
        return
    start = time.perf_counter()
    try:
        yield
    finally:
        App.Console.PrintMessage("Nxt fillet: %s %.3f s\n"
                                 % (label, time.perf_counter() - start))


def _body_of(obj: Any) -> Any:
    parent = obj.getParentGeoFeatureGroup()
    return parent if parent is not None and parent.isDerivedFrom(
        "PartDesign::Body") else None


def _point_on(face: Any, tolerance: float) -> App.Vector | None:
    """A point surely on the face itself, not in one of its holes.

    The middle of its parameter range can fall in a hole or outside a
    trimmed face; a tessellation triangle's centre cannot.
    """
    try:
        points, triangles = face.tessellate(max(tolerance * 100, 0.01))
    except Exception:  # noqa: BLE001 - nothing to sample
        return None
    if not triangles:
        return None
    a, b, c = (points[i] for i in triangles[len(triangles) // 2])
    centre = (a + b + c) * (1 / 3)
    # On a curved face the triangle cuts a chord inside the surface;
    # back onto it, or every curved face reads as new.
    try:
        u, v = face.Surface.parameter(centre)
        return face.Surface.value(u, v)
    except Exception:  # noqa: BLE001 - keep the chord point
        return centre


def generated_faces(result: Any, base: Any) -> Any:
    """The faces of `result` that `base` did not have, as a compound.

    What Part Design's dress-up preview highlights: the new rounds.
    """
    tolerance = max(base.BoundBox.DiagonalLength * 1e-6, 1e-6)
    boxes = []
    for old in base.Faces:
        box = old.BoundBox
        box.enlarge(tolerance)
        boxes.append((box, old))
    kept = _faces_by_hash(base)
    faces = []
    for face in result.Faces:
        if any(face.isSame(old) for old in kept.get(face.hashCode(), ())):
            continue
        # One point inside the face: a coarse mesh finds it as surely.
        point = _point_on(face, face.BoundBox.DiagonalLength * 1e-4)
        if point is None:
            continue
        inside = Part.Vertex(point)
        # The box test first: distToShape is the slow part.
        if not any(box.isInside(point) and old.distToShape(inside)[0]
                   < tolerance for box, old in boxes):
            faces.append(face)
    compound = Part.makeCompound(faces)
    compound.Placement = App.Placement()
    return compound


def _attach_view_provider(obj: Any, flat: bool) -> None:
    """Give a feature made without the GUI (as by a script) our view.

    Without it the feature cannot be edited: FreeCAD finds no dialog.
    """
    vobj = getattr(obj, "ViewObject", None)
    if vobj is None or isinstance(getattr(vobj, "Proxy", None),
                                  ViewProviderBlendFillet):
        return
    (ViewProviderBlendChamfer if flat else ViewProviderBlendFillet)(vobj)


def _usable(shape: Any) -> Any:
    """A copy of `shape` to round, repaired if it is not valid.

    A base feature can come out a little invalid (an edge's tolerance)
    yet still be rounded by FreeCAD's own fillet; booleans refuse it.
    """
    copy = shape.copy()
    if not copy.isValid():
        fixed = copy.copy()
        fixed.fix(1e-7, 1e-7, 1e-7)
        if fixed.isValid():
            return fixed
    return copy


#: Less material than this, per the base's volume, is none at all.
TOOL_SHARE = 1e-9


def set_tool(obj: Any, base: Any, result: Any) -> str:
    """Record the material this feature adds or removes, for patterns.

    Mirrored and the patterns copy a feature by its AddSubShape, fused
    or cut by Operation. Rounding convex edges removes material and
    concave ones adds it; a feature doing both at once cannot be copied
    that way, and is left without one. Returns why, if so.
    """
    if not hasattr(obj, "AddSubShape"):
        return ""
    plain = App.Placement()
    start, end = base.copy(), result.copy()
    start.Placement = end.Placement = plain
    try:
        removed, added = start.cut(end), end.cut(start)
    except Exception as exc:  # noqa: BLE001 - patterns go without it
        obj.AddSubShape = Part.Shape()
        return "its material could not be worked out (%s)" % exc
    least = max(abs(start.Volume), 1.0) * TOOL_SHARE
    removes, adds = removed.Volume > least, added.Volume > least
    if removes and adds:
        obj.AddSubShape = Part.Shape()
        return ("it both removes and adds material; mirror or pattern "
                "its convex and concave edges as separate features")
    if adds:
        obj.Operation = "Union"
        obj.AddSubShape = added
    else:
        obj.Operation = "Subtraction"
        obj.AddSubShape = removed
    return ""


def new_fillet(base: Any, names: list[str], size: float,
               flat: bool = False) -> Any:
    """An Nxt fillet, or with `flat` a chamfer, on `base`.

    Inside the caller's transaction.
    """
    body = _body_of(base)
    if body is None:
        raise ValueError("%s is not in a Part Design Body" % base.Label)
    obj = body.newObject(FEATURE_TYPE,
                         CHAMFER_NAME if flat else FEATURE_NAME)
    (BlendChamfer if flat else BlendFillet)(obj)
    _attach_view_provider(obj, flat)
    obj.BaseFeature = base
    from . import feature_colors
    feature_colors.copy_visuals(base, obj)
    obj.Edges = [(base, names)] if names else []
    setattr(obj, "Size" if flat else "Radius", size)
    return obj


def face_edges(shape: Any, face_name: str) -> list[str]:
    """The "EdgeN" names of a face's edges, in `shape`'s numbering."""
    face = shape.getElement(face_name)
    return ["Edge%d" % (index + 1) for index, edge in enumerate(shape.Edges)
            if any(edge.isSame(e) for e in face.Edges)]


def picked_edges() -> tuple[Any, list[str]]:
    """The feature owning the selected edges, and their "EdgeN" names.

    A selected face stands for its edges.
    """
    import FreeCADGui as Gui

    owners: dict[str, tuple[Any, list[str]]] = {}
    for sel in Gui.Selection.getSelectionEx("", 0):
        for sub in sel.SubElementNames:
            owner, _mapped, element = sel.Object.resolveSubElement(sub)
            element = (element or "").lstrip("?")
            if owner is None:
                continue
            if element.startswith("Edge"):
                found = [element]
            elif element.startswith("Face"):
                found = face_edges(owner.Shape, element)
            else:
                continue
            picked = owners.setdefault(owner.Name, (owner, []))[1]
            picked += [n for n in found if n not in picked]
    if not owners:
        raise ValueError("Select one or more edges or faces first")
    if len(owners) > 1:
        raise ValueError("The edges belong to %s; select edges of one "
                         "feature" % ", ".join(sorted(owners)))
    base, names = next(iter(owners.values()))
    body = _body_of(base)
    if body is None:
        raise ValueError("%s is not in a Part Design Body" % base.Label)
    if body.Tip != base:
        tip = body.Tip.Label if body.Tip is not None else "nothing"
        raise ValueError("%s is not the Body's tip (%s is); select edges "
                         "of the tip" % (base.Label, tip))
    return base, names


def explain(radius: float) -> None:
    """Print how the selected edge's fillet is built, step by step."""
    base, names = picked_edges()
    shape = base.Shape.copy()
    say = App.Console.PrintMessage
    for name in names:
        edge = shape.getElement(name)
        faces = _faces_of(shape, edge)
        say("%s: %s, faces %s\n" % (name, type(edge.Curve).__name__,
                                    [type(f.Surface).__name__
                                     for f in faces]))
        u = edge.FirstParameter
        point = edge.valueAt(u)
        for face in faces:
            say("  normal %s at %s\n" % (_normal(face, point), point))
        _solid.append(shape)
        try:
            found = _rolled(faces[0], faces[1], edge, u, radius, None)
        finally:
            _solid.pop()
        if found is None:
            say("  tangent faces\n")
            continue
        station, convex = found
        _solid.append(shape)
        n1, n2 = _normal(faces[0], point), _normal(faces[1], point)
        step = _step()
        for a in (1, -1):
            for b in (1, -1):
                at = point + (n1 * a + n2 * b) * step
                strict = _contains(shape, at, step / 10)
                exact = shape.Solids[0].isInside(at, 1e-7, True)
                say("  quadrant %+d %+d at %s: inside %s, strict %s, "
                    "solid %s\n" % (a, b, at, _inside(at), strict, exact))
        say("  step %.3g\n" % step)
        say("  solid test %s (%s, %d solids)\n" % (
            _material_says(point, _normal(faces[0], point),
                           _normal(faces[1], point)),
            shape.ShapeType, len(shape.Solids)))
        _solid.pop()
        say("  convex %s centre %s\n  contacts %s %s\n" % (
            convex, station.centre, station.contact1, station.contact2))
        _solid.append(shape)
        say("  fits %s, may overflow %s\n" % (
            _fits(faces, edge, radius),
            _trimmed_overflow(shape, faces, edge, radius)))
        _solid.pop()
        _solid.append(shape)
        try:
            _explain_ends(shape, faces, edge, radius, say)
        finally:
            _solid.pop()
        tool, convex = edge_tool(shape, edge, radius)
        say("  tool volume %.4g, inside the part %.4g\n" % (
            tool.Volume, tool.common(shape).Volume))
        if not convex:
            clipped = _clipped(shape, edge, tool, say, radius)
            say("  after trimming %.4g, inside the part %.4g\n" % (
                clipped.Volume, clipped.common(shape).Volume))


def _explain_ends(shape: Any, faces: list[Any], edge: Any, radius: float,
                  say: Any) -> None:
    """Print how each end of the edge decides whether to run on."""
    curve = edge.Curve
    exact = isinstance(curve, Part.Line) and all(
        _exact(f, edge.tangentAt(edge.FirstParameter)) for f in faces)
    turned = isinstance(curve, Part.Circle) and all(
        _coaxial(f, curve) for f in faces)
    path = "straight" if exact else "revolved" if turned else "lofted"
    say("  path: %s\n" % path)
    tolerance = radius * WALK_TOLERANCE * 10
    for name, u in (("start", edge.FirstParameter),
                    ("end", edge.LastParameter)):
        at = edge.valueAt(u)
        say("  %s %s: reach %.4g\n" % (
            name, at, _end_reach(shape, faces, edge, at, radius)))
        for index, face in enumerate(faces):
            for rim in face.Edges:
                if rim.isSame(edge):
                    continue
                gap = min((v.Point - at).Length for v in rim.Vertexes)
                if gap > radius:
                    continue
                beyond = [f for f in _faces_of(shape, rim)
                          if not f.isSame(face)]
                kinds = [type(f.Surface).__name__ for f in beyond]
                middle = _middle(rim)
                point = rim.valueAt(middle)
                verdict = "-"
                if len(beyond) == 1:
                    n1 = _normal(face, point)
                    n2 = _normal(beyond[0], point)
                    verdict = str(_is_convex(
                        face, point, rim.tangentAt(middle).normalize(),
                        n1, n2))
                say("    face %d rim %s gap %.3g (touches %s) beyond %s "
                    "convex %s\n" % (index, type(rim.Curve).__name__, gap,
                                     gap < tolerance, kinds, verdict))
