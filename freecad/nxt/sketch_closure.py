"""Why a sketch's profile is not closed, worked out from its edges alone.

No FreeCAD here: sketch_repair.py reads the edges out of a sketch and
applies what this finds, so the reasoning can be tested without one.

A profile closes when every edge end meets exactly one other. Three
things stop that and can be told apart with no doubt about intent:

    a gap        two loose ends that all but touch;
    a duplicate  an edge drawn again over the same two ends;
    a stub       an edge of no length.

What is left is the user's to deal with, and is reported, not touched:
loose ends (a profile not finished, a stray edge), points where the
profile forks, and edges lying over part of one another. An overlap is
found between straight lines and between circular arcs; where deleting
one side of every overlap would leave a closed profile, those edges are
named, for a repair the user asks for.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field, replace
from itertools import combinations
from math import atan2, hypot, tau

Point = tuple[float, float]
#: An edge's end: (edge index, START or END), as a constraint names it.
End = tuple[int, int]

#: Sketcher's point positions.
START, END = 1, 2

#: Ends closer than this already meet: OpenCASCADE's own tolerance, which
#: is what decides whether FreeCAD finds the wire closed.
JOINED = 1e-7
#: Loose ends this near each other, as a fraction of the sketch's
#: diagonal, are a gap: they look joined with the whole sketch in view.
GAP_FRACTION = 0.01
#: An edge this near another's line or circle, by the same measure, lies
#: on it. Far tighter than a gap: the two sides of a thin slot are close
#: and parallel, and are not an overlap.
OVERLAP_FRACTION = 1e-4


@dataclass(frozen=True)
class Edge:
    """One open curve that is not construction geometry."""

    index: int
    start: Point
    end: Point
    mid: Point
    length: float
    #: A straight line, or (with a centre) a circular arc: the two shapes
    #: an overlap can be found between.
    straight: bool = False
    centre: Point | None = None


@dataclass(frozen=True)
class Findings:
    #: Pairs of loose ends to join.
    gaps: list[tuple[End, End]] = field(default_factory=list)
    #: Indices of duplicates and stubs, to delete.
    surplus: list[int] = field(default_factory=list)
    #: Loose ends that joining the gaps will leave.
    open_ends: int = 0
    #: Points where three or more edges meet.
    forks: int = 0
    #: Pairs of edges lying over part of one another, by index.
    overlaps: list[tuple[int, int]] = field(default_factory=list)
    #: Overlapping edges whose deletion would leave a closed profile.
    removable: list[int] = field(default_factory=list)

    def repairable(self) -> bool:
        """Whether there is anything to mend without asking."""
        return bool(self.gaps or self.surplus)

    def closed(self) -> bool:
        return not (self.repairable() or self.open_ends or self.forks
                    or self.overlaps)


def _distance(a: Point, b: Point) -> float:
    return hypot(a[0] - b[0], a[1] - b[1])


def _near(points: Sequence[Point],
          radius: float) -> Iterator[tuple[float, int, int]]:
    """(distance, i, j) for each pair of points within `radius`.

    Swept in x order, so only points in the same narrow band are ever
    compared.
    """
    order = sorted(range(len(points)), key=points.__getitem__)
    for at, i in enumerate(order):
        for j in order[at + 1:]:
            if points[j][0] - points[i][0] > radius:
                break
            distance = _distance(points[i], points[j])
            if distance <= radius:
                yield distance, i, j


def _vertices(points: Sequence[Point]) -> list[int]:
    """A vertex id for each point: points that already meet share one."""
    vertex = list(range(len(points)))

    def root(i: int) -> int:
        while vertex[i] != i:
            vertex[i] = i = vertex[vertex[i]]
        return i

    for _distance_apart, i, j in _near(points, JOINED):
        vertex[root(i)] = root(j)
    return [root(i) for i in range(len(points))]


def _diagonal(edges: Sequence[Edge]) -> float:
    xs, ys = zip(*(p for e in edges for p in (e.start, e.end, e.mid)))
    return hypot(max(xs) - min(xs), max(ys) - min(ys))


def _places(on: Edge, other: Edge, slack: float) -> list[float] | None:
    """How far along `on` each of `other`'s three points lies.

    Measured from `on`'s start, past its end or before its start if the
    point is beyond it. None if `other` is not on `on`'s line or circle.
    """
    points = (other.start, other.mid, other.end)
    if on.straight:
        dx, dy = on.end[0] - on.start[0], on.end[1] - on.start[1]
        places = []
        for x, y in points:
            px, py = x - on.start[0], y - on.start[1]
            if abs(px * dy - py * dx) > slack * on.length:
                return None
            places.append((px * dx + py * dy) / on.length)
        return places
    if on.centre is None:
        return None
    cx, cy = on.centre
    radius = _distance(on.centre, on.start)
    if any(abs(_distance(on.centre, p) - radius) > slack for p in points):
        return None

    def angle(point: Point) -> float:
        return atan2(point[1] - cy, point[0] - cx)

    # Counter-clockwise from `begin`: an arc drawn the other way begins
    # at its end.
    begin, sweep = angle(on.start), (angle(on.end) - angle(on.start)) % tau
    if (angle(on.mid) - begin) % tau > sweep:
        begin, sweep = angle(on.end), tau - sweep
    places = [((angle(p) - begin) % tau) * radius for p in points]
    # Just short of where the arc begins is before it, not a lap past it.
    beyond = (sweep + tau) / 2 * radius
    return [at - tau * radius if at > beyond else at for at in places]


def _lies_on(on: Edge, other: Edge, slack: float) -> tuple[bool, bool]:
    """(part of `other` is inside `on`, all of `other` is on `on`)."""
    places = _places(on, other, slack)
    if places is None:
        return False, False
    return (any(slack < at < on.length - slack for at in places),
            all(-slack <= at <= on.length + slack for at in places))


def _overlaps(edges: Sequence[Edge], slack: float
              ) -> tuple[list[tuple[int, int]], set[int], set[int]]:
    """(overlapping pairs, edges inside another, edges with one inside)."""
    pairs: list[tuple[int, int]] = []
    inner: set[int] = set()
    outer: set[int] = set()
    shaped = [e for e in edges if e.straight or e.centre is not None]
    for a, b in combinations(shaped, 2):
        (b_in_a, b_on_a), (a_in_b, a_on_b) = (
            _lies_on(a, b, slack), _lies_on(b, a, slack))
        if not (b_in_a or a_in_b):
            continue
        pairs.append((a.index, b.index))
        if b_on_a or a_on_b:
            inside, around = (b, a) if b_on_a else (a, b)
            inner.add(inside.index)
            outer.add(around.index)
    return pairs, inner, outer


def inspect(edges: Sequence[Edge],
            fraction: float = GAP_FRACTION) -> Findings:
    """What keeps these edges from closing, and what would mend it."""
    found, inner, outer = _inspect(edges, fraction)
    # The fewer edges first: the short one drawn over a long one, before
    # the long one drawn over several.
    for extra in sorted((inner, outer), key=len):
        rest = [e for e in edges if e.index not in extra]
        if extra and _inspect(rest, fraction)[0].closed():
            return replace(found, removable=sorted(extra))
    return found


def _inspect(edges: Sequence[Edge], fraction: float
             ) -> tuple[Findings, set[int], set[int]]:
    """The findings, and the edges inside and around an overlap."""
    surplus = [e.index for e in edges if e.length <= JOINED]
    edges = [e for e in edges if e.length > JOINED]
    if not edges:
        return Findings(surplus=surplus), set(), set()
    diagonal = _diagonal(edges)
    tolerance = fraction * diagonal

    # Each edge's two ends sit side by side: edge k has points 2k, 2k + 1.
    points = [p for e in edges for p in (e.start, e.end)]
    vertex = _vertices(points)

    kept: dict[frozenset[int], list[Edge]] = {}
    duplicate: set[int] = set()
    for k, edge in enumerate(edges):
        twins = kept.setdefault(
            frozenset((vertex[2 * k], vertex[2 * k + 1])), [])
        if any(_distance(edge.mid, twin.mid) <= JOINED for twin in twins):
            duplicate.add(k)
        else:
            twins.append(edge)
    surplus += [edges[k].index for k in sorted(duplicate)]

    live = [i for i in range(len(points)) if i // 2 not in duplicate]
    degree = Counter(vertex[i] for i in live)
    loose = [i for i in live if degree[vertex[i]] == 1]
    forks = sum(1 for meeting in degree.values() if meeting > 2)

    gaps: list[tuple[End, End]] = []
    joined: set[int] = set()
    for _distance_apart, a, b in sorted(
            _near([points[i] for i in loose], tolerance)):
        i, j = loose[a], loose[b]
        if i // 2 == j // 2 or i in joined or j in joined:
            continue    # an edge's own two ends, or an end already paired
        joined.update((i, j))
        gaps.append(((edges[i // 2].index, START + i % 2),
                     (edges[j // 2].index, START + j % 2)))

    # An overlap always leaves a loose end or a fork: without either
    # there is none to look for.
    pairs: list[tuple[int, int]] = []
    inner: set[int] = set()
    outer: set[int] = set()
    if loose or forks:
        pairs, inner, outer = _overlaps(
            [e for k, e in enumerate(edges) if k not in duplicate],
            OVERLAP_FRACTION * diagonal)
    return (Findings(gaps, surplus, len(loose) - len(joined), forks, pairs),
            inner, outer)
