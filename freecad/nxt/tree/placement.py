"""Where a floating field goes, beside the thing it belongs to.

Plain rectangles in, a position out; no FreeCAD and no Qt, so the rules
are tested on their own (tests/test_placement.py). Screen coordinates:
x to the right, y down, as Qt widgets have them.

The rules, in order:
  1. Beside the target, to its right, centred on it vertically, with a
     gap - never on top of it, so the handle stays grabbable.
  2. If that runs off the right edge, to its left instead.
  3. Kept inside the view.
  4. Clear of fields already placed: moved down, then up, one field's
     height (plus the gap) at a time, until it is clear. Placed in a
     fixed order, so the same targets always give the same layout.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

#: Space between the target and the field, and between fields.
GAP = 8


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def centre_y(self) -> float:
        return self.y + self.height / 2

    def overlaps(self, other: Rect) -> bool:
        return (self.x < other.right and other.x < self.right
                and self.y < other.bottom and other.y < self.bottom)

    def moved(self, dx: float = 0, dy: float = 0) -> Rect:
        return Rect(self.x + dx, self.y + dy, self.width, self.height)


def from_viewport(x: float, y: float, height: float,
                  ratio: float = 1.0) -> tuple[float, float]:
    """A point from FreeCAD's getPointOnViewport, in widget coordinates.

    FreeCAD answers as Coin does: device pixels, origin at the BOTTOM
    left, y up. Widgets have the origin at the top left, y down, in
    logical pixels. `height` is the viewport's height in device pixels.

    Reading y as top-down mirrored every placement about the middle of
    the view: right on the first try at the middle, and moving the wrong
    way up and down as the arrow was dragged.
    """
    ratio = ratio or 1.0
    return x / ratio, (height - y) / ratio


def bounding(points: Iterable[tuple[float, float]]) -> Rect | None:
    """The rectangle around some points: a 3D box's projected corners."""
    xs, ys = [], []
    for x, y in points:
        xs.append(x)
        ys.append(y)
    if not xs:
        return None
    return Rect(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def _inside(rect: Rect, bounds: Rect) -> Rect:
    x = min(max(rect.x, bounds.x), bounds.right - rect.width)
    y = min(max(rect.y, bounds.y), bounds.bottom - rect.height)
    return Rect(max(x, bounds.x), max(y, bounds.y), rect.width, rect.height)


def beside(target: Rect, width: float, height: float, bounds: Rect,
           taken: Sequence[Rect] = ()) -> Rect:
    """Where a field of this size goes, next to `target`."""
    y = target.centre_y - height / 2
    rect = Rect(target.right + GAP, y, width, height)
    if rect.right > bounds.right:
        rect = Rect(target.x - GAP - width, y, width, height)
    rect = _inside(rect, bounds)
    if not any(rect.overlaps(other) for other in taken):
        return rect
    step = height + GAP
    for n in range(1, 2 * len(taken) + 2):
        for sign in (1, -1):
            candidate = _inside(rect.moved(dy=sign * n * step), bounds)
            if not any(candidate.overlaps(o) for o in taken):
                return candidate
    return rect


def layout(targets: Sequence[Rect], sizes: Sequence[tuple[float, float]],
           bounds: Rect) -> list[Rect]:
    """Places several fields, each beside its target, none overlapping.

    Also clear of every target, so no field hides another's handle.
    """
    placed: list[Rect] = []
    for target, (width, height) in zip(targets, sizes):
        placed.append(beside(target, width, height, bounds,
                             list(placed) + list(targets)))
    return placed
