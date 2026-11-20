"""Selected and preselected edges and vertices, kept clear of the AO.

The occlusion is blended over the finished picture, so it darkens the
highlight of a picked edge or vertex too, just when it should stand out.
This keeps, per document, a group of Coin lines and points where those
edges and vertices are, in world space; a pass of the effect draws it
into a mask that the composite leaves undarkened (ao_pipeline.py).

Only edges and vertices: a face, or a whole object picked in the tree,
keeps its occlusion. The group changes with the selection only, never
per frame.
"""

from __future__ import annotations

import contextlib
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

#: Sub-element names the mask covers; faces are left to the occlusion.
EDGE, VERTEX = "Edge", "Vertex"
#: FreeCAD's own line width and point size, in pixels, and the margin the
#: mask adds so a highlight's antialiased rim stays clear too.
VIEW_PARAMS = "User parameter:BaseApp/Preferences/View"
LINE_WIDTH = ("DefaultShapeLineWidth", 2)
POINT_SIZE = ("DefaultShapePointSize", 2)
MARGIN_PX = 1
#: Chord deviation of a curved edge's polyline, as a fraction of its
#: length: closer than a pixel at any sensible zoom.
DEVIATION = 1e-3


def element_kind(subname: str) -> str | None:
    """EDGE or VERTEX for a sub-element's (dotted) name; None otherwise."""
    element = subname.rsplit(".", 1)[-1]
    for kind in (EDGE, VERTEX):
        if element.startswith(kind) and element[len(kind):].isdigit():
            return kind
    return None


def widths() -> tuple[float, float]:
    """The mask's line width and point size, in pixels."""
    params = App.ParamGet(VIEW_PARAMS)
    line = params.GetInt(*LINE_WIDTH)
    point = params.GetInt(*POINT_SIZE)
    return float(max(line, 1) + MARGIN_PX), float(max(point, 1) + MARGIN_PX)


def polylines(picks: list[tuple[Any, str]]) -> tuple[
        list[list[tuple[float, float, float]]],
        list[tuple[float, float, float]]]:
    """The world-space polylines of the picked edges, and their vertices.

    `picks` are (root object, full subname); links and bodies are
    resolved by Part.getShape.
    """
    import Part
    lines: list[list[tuple[float, float, float]]] = []
    points: list[tuple[float, float, float]] = []
    for obj, subname in picks:
        kind = element_kind(subname)
        if kind is None:
            continue
        with contextlib.suppress(Exception):   # a pick of a deleted object
            shape: Any = Part.getShape(obj, subname, needSubElement=True)
            if kind == VERTEX:
                point = shape.Vertexes[0].Point
                points.append((point.x, point.y, point.z))
                continue
            for edge in shape.Edges:
                along = edge.discretize(
                    Deflection=max(edge.Length * DEVIATION, 1e-9))
                lines.append([(p.x, p.y, p.z) for p in along])
    return lines, points


class Highlights:
    """The picked edges and vertices of every document, as Coin groups."""

    def __init__(self) -> None:
        self.groups: dict[str, Any] = {}
        self.preselected: tuple[str, str, str] | None = None
        self.installed = False

    def group(self, doc_name: str) -> Any:
        """The mask geometry of `doc_name`: kept, and filled, on demand."""
        group = self.groups.get(doc_name)
        if group is None:
            from pivy import coin
            group = self.groups[doc_name] = coin.SoSeparator()
            group.ref()
            self._fill(doc_name)
        return group

    def install(self) -> None:
        Gui.Selection.addObserver(self)
        self.installed = True

    def remove(self) -> None:
        if self.installed:
            with contextlib.suppress(Exception):
                Gui.Selection.removeObserver(self)
            self.installed = False
        for group in self.groups.values():
            group.removeAllChildren()
            group.unref()
        self.groups.clear()

    def forget(self, doc_name: str) -> None:
        group = self.groups.pop(doc_name, None)
        if group is not None:
            group.removeAllChildren()
            group.unref()

    # -- Gui.Selection's observer, called by name -- #

    def addSelection(self, doc: str, obj: str, sub: str,  # noqa: N802
                     _pnt: Any) -> None:
        self._refill(doc)

    def removeSelection(self, doc: str, obj: str,  # noqa: N802
                        sub: str) -> None:
        self._refill(doc)

    def setSelection(self, doc: str) -> None:  # noqa: N802
        self._refill(doc)

    def clearSelection(self, doc: str) -> None:  # noqa: N802
        for name in list(self.groups) if not doc else [doc]:
            self._refill(name)

    def setPreselection(self, doc: str, obj: str,  # noqa: N802
                        sub: str) -> None:
        self.preselected = (doc, obj, sub)
        self._refill(doc)

    def removePreselection(self, doc: str, obj: str,  # noqa: N802
                           sub: str) -> None:
        self.preselected = None
        self._refill(doc)

    # -- filling -- #

    def _picks(self, doc_name: str) -> list[tuple[Any, str]]:
        doc = App.getDocument(doc_name)
        picks = [(chosen.Object, sub)
                 for chosen in Gui.Selection.getSelectionEx(doc_name, 0)
                 for sub in chosen.SubElementNames]
        if self.preselected is not None and self.preselected[0] == doc_name:
            obj = doc.getObject(self.preselected[1])
            if obj is not None:
                picks.append((obj, self.preselected[2]))
        return picks

    def _refill(self, doc_name: str) -> None:
        # a new group's children notify the mask, which then draws again
        if doc_name in self.groups:
            self._fill(doc_name)

    def _fill(self, doc_name: str) -> None:
        from pivy import coin
        group = self.groups[doc_name]
        group.removeAllChildren()
        try:
            lines, points = polylines(self._picks(doc_name))
        except Exception:  # noqa: BLE001 - called from the selection
            return
        if lines:
            coords = coin.SoCoordinate3()
            coords.point.setValues(0, sum(len(line) for line in lines),
                                   [p for line in lines for p in line])
            strips = coin.SoLineSet()
            strips.numVertices.setValues(0, len(lines),
                                         [len(line) for line in lines])
            group.addChild(coords)
            group.addChild(strips)
        if points:
            coords = coin.SoCoordinate3()
            coords.point.setValues(0, len(points), points)
            dots = coin.SoPointSet()
            group.addChild(coords)
            group.addChild(dots)
