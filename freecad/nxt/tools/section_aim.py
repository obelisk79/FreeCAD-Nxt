"""Where a section plane goes: an axis, the view, or the selection.

A selected planar face or datum plane gives its plane; three selected
points give the plane through them. Every plane is turned so the cut
faces the camera.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

Plane = tuple[Any, Any]          # (unit normal, a point on the plane)

#: Smaller than this, three points are taken to lie on one line.
COLLINEAR = 1e-9
DATUM_PLANES = ("App::Plane", "PartDesign::Plane", "Part::DatumPlane")
AXES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}


def facing(normal: Any, look: Any) -> Any:
    """The normal turned away from the camera, so the cut faces it."""
    return normal if normal.dot(look) >= 0 else normal * -1.0


def plane_through(points: Sequence[Any]) -> Plane | None:
    """The plane through three points, or None if they are in a line."""
    if len(points) != 3:
        return None
    a, b, c = points
    normal = (b - a).cross(c - a)
    if normal.Length < COLLINEAR:
        return None
    normal.normalize()
    return normal, (a + b + c) * (1.0 / 3.0)


def _face_plane(face: Any) -> Plane | None:
    """A planar face's plane, through its centre."""
    import Part
    if not isinstance(getattr(face, "Surface", None), Part.Plane):
        return None
    u0, u1, v0, v1 = face.ParameterRange
    normal = face.normalAt((u0 + u1) / 2, (v0 + v1) / 2)
    return normal, face.CenterOfMass


def _datum_plane(root: Any, sub: str) -> Plane | None:
    """An origin or datum plane's placement, in the root's frame."""
    try:
        obj, matrix = root.getSubObject(sub, retType=2)
    except Exception:
        return None
    if getattr(obj, "TypeId", "") not in DATUM_PLANES:
        return None
    origin = matrix.multVec(App.Vector())
    normal = matrix.multVec(App.Vector(0, 0, 1)) - origin
    normal.normalize()
    return normal, origin


def from_selection() -> Plane | None:
    """The plane the selection gives, in model coordinates, if any."""
    points: list[Any] = []
    for sel in Gui.Selection.getSelectionEx("", 0):
        root = sel.Object
        for sub in sel.SubElementNames or ("",):
            datum = _datum_plane(root, sub)
            if datum is not None:
                return datum
            try:
                shape = root.getSubObject(sub)
                # An empty sketch, or anything else with no geometry yet,
                # has a null shape: it says nothing about a plane.
                if shape is None or (hasattr(shape, "isNull")
                                     and shape.isNull()):
                    continue
                kind = getattr(shape, "ShapeType", "")
            except Exception:
                continue
            if kind == "Vertex":
                points.append(shape.Point)
            elif kind == "Face":
                plane = _face_plane(shape)
                if plane is not None:
                    return plane
            elif getattr(shape, "Faces", None) and len(shape.Faces) == 1:
                plane = _face_plane(shape.Faces[0])
                if plane is not None:
                    return plane
    return plane_through(points)


def axis(name: str) -> Any:
    return App.Vector(*AXES[name])
