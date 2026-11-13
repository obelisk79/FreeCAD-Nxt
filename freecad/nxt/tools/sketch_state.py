"""A sketch being edited, read into plain data for sketch_panel.py.

No Qt and no FreeCADGui: the solver's findings, one constraint, one
element and what is selected, as dicts QML can show. A constraint's
`number` counts from 1, as FreeCAD shows it; its `index` counts from 0,
as the sketch's methods take it.
"""

from __future__ import annotations

import contextlib
from typing import Any

from ..app.i18n import QT_TRANSLATE_NOOP, translate
from ..tree import health

#: Constraint types that hold a value, and so can drive or be driven.
DIMENSIONAL = frozenset({"Distance", "DistanceX", "DistanceY", "Radius",
                         "Diameter", "Angle", "Weight", "SnellsLaw"})

#: Sketcher's constraint types whose name is not already a plain word.
CONSTRAINT_LABELS: dict[str, str] = {
    "PointOnObject": QT_TRANSLATE_NOOP("Nxt", "Point on object"),
    "DistanceX": QT_TRANSLATE_NOOP("Nxt", "Horizontal distance"),
    "DistanceY": QT_TRANSLATE_NOOP("Nxt", "Vertical distance"),
    "InternalAlignment": QT_TRANSLATE_NOOP("Nxt", "Internal alignment"),
    "SnellsLaw": QT_TRANSLATE_NOOP("Nxt", "Refraction"),
}

#: Part's geometry classes, by the name a sketch's element goes by.
ELEMENT_LABELS: dict[str, str] = {
    "LineSegment": QT_TRANSLATE_NOOP("Nxt", "Line"),
    "ArcOfCircle": QT_TRANSLATE_NOOP("Nxt", "Arc"),
    "Circle": QT_TRANSLATE_NOOP("Nxt", "Circle"),
    "Ellipse": QT_TRANSLATE_NOOP("Nxt", "Ellipse"),
    "ArcOfEllipse": QT_TRANSLATE_NOOP("Nxt", "Elliptical arc"),
    "ArcOfHyperbola": QT_TRANSLATE_NOOP("Nxt", "Hyperbolic arc"),
    "ArcOfParabola": QT_TRANSLATE_NOOP("Nxt", "Parabolic arc"),
    "BSplineCurve": QT_TRANSLATE_NOOP("Nxt", "B-spline"),
    "Point": QT_TRANSLATE_NOOP("Nxt", "Point"),
}
#: A geometry class not named above.
ELEMENT = QT_TRANSLATE_NOOP("Nxt", "Element")
#: The sketch's axes, by their geometry index.
AXES: dict[int, tuple[str, str]] = {
    -1: ("H_Axis", QT_TRANSLATE_NOOP("Nxt", "Horizontal axis")),
    -2: ("V_Axis", QT_TRANSLATE_NOOP("Nxt", "Vertical axis")),
}
#: External geometry's indices count down from this one (GeoEnum::RefExt).
FIRST_EXTERNAL = -3
EXTERNAL = QT_TRANSLATE_NOOP("Nxt", "External")

#: A solver finding's heading, by the sketch attribute that lists it.
FINDING_TITLES: dict[str, str] = {
    "ConflictingConstraints": QT_TRANSLATE_NOOP("Nxt", "Over-constrained"),
    "MalformedConstraints":
        QT_TRANSLATE_NOOP("Nxt", "Malformed constraints"),
    "RedundantConstraints":
        QT_TRANSLATE_NOOP("Nxt", "Redundant constraints"),
    "PartiallyRedundantConstraints":
        QT_TRANSLATE_NOOP("Nxt", "Partially redundant"),
}

#: The status mark's shapes (SeverityMark.qml): none, ring, triangle, disc.
MARK_NONE, MARK_FREE = 0, 1
#: A finding's mark is its health severity, past the ring.
MARK_ABOVE_SEVERITY = 1

#: A constraint's geometry index where it names none (GeoEnum::GeoUndef).
UNSET = -2000

#: The status link that selects what is still free to move.
FREE = "dof"

#: Selection names inside a sketch, and what each picks.
_PICKS = (("Constraint", "constraint"), ("Edge", "element"),
          ("Vertex", "vertex"))


def _value(sketch: Any, constraint: Any, index: int) -> str:
    with contextlib.suppress(Exception):  # no datum, or a build without it
        return str(sketch.getDatum(index).UserString)
    return "%g" % constraint.Value


def constraint_row(sketch: Any, constraints: Any, index: int
                   ) -> dict[str, Any]:
    """One constraint as a row or a card shows it."""
    constraint = constraints[index]
    kind = str(constraint.Type)
    dimensional = kind in DIMENSIONAL
    return {
        "index": index,
        "number": index + 1,
        "label": translate("Nxt", CONSTRAINT_LABELS.get(kind, kind)),
        "value": _value(sketch, constraint, index) if dimensional else "",
        "name": str(constraint.Name or ""),
        "dimensional": dimensional,
        "driving": bool(constraint.Driving),
        "active": bool(getattr(constraint, "IsActive", True)),
    }


def issues(sketch: Any) -> list[dict[str, Any]]:
    """Each solver finding with its constraints, worst first."""
    found = health.findings(sketch)
    if not found:
        return []
    constraints = sketch.Constraints
    return [{
        "key": accessor,
        "title": translate("Nxt", FINDING_TITLES[accessor]),
        "mark": severity + MARK_ABOVE_SEVERITY,
        "rows": [constraint_row(sketch, constraints, number - 1)
                 for number in numbers if 0 < number <= len(constraints)],
    } for accessor, severity, numbers in found]


def status(sketch: Any) -> dict[str, Any]:
    """The one line FreeCAD's solver message gives, in parts.

    `link` is the part that selects what the line is about, by `action`:
    a finding's sketch attribute, or FREE.
    """
    plain = {"mark": MARK_NONE, "text": "", "link": "", "action": ""}
    if not getattr(sketch, "GeometryCount", 0):
        return {**plain, "text": translate("Nxt", "Empty sketch")}
    found = health.findings(sketch)
    if found:
        accessor, severity, numbers = found[0]
        return {"mark": severity + MARK_ABOVE_SEVERITY,
                "text": translate("Nxt", FINDING_TITLES[accessor]),
                "link": ", ".join(str(number) for number in numbers),
                "action": accessor}
    free = health.degrees_of_freedom(sketch)
    if free is None:
        return plain
    if free == 0:
        return {**plain, "text": translate("Nxt", "Fully constrained")}
    return {**plain, "mark": MARK_FREE, "action": FREE,
            "link": translate("Nxt", "%d DoF") % free}


def geometry_ref(sketch: Any, geo: int) -> dict[str, str]:
    """A constraint's geometry as a chip names and selects it."""
    if geo in AXES:
        name, label = AXES[geo]
        return {"title": translate("Nxt", label), "name": name}
    if geo <= FIRST_EXTERNAL:
        number = FIRST_EXTERNAL - geo + 1
        return {"title": "%s %d" % (translate("Nxt", EXTERNAL), number),
                "name": "ExternalEdge%d" % number}
    geometry = sketch.Geometry
    label = ELEMENT_LABELS.get(type(geometry[geo]).__name__, ELEMENT) \
        if geo < len(geometry) else ELEMENT
    return {"title": "%s %d" % (translate("Nxt", label), geo + 1),
            "name": "Edge%d" % (geo + 1)}


def _geometry_of(sketch: Any, constraint: Any) -> list[dict[str, str]]:
    """Each geometry a constraint names, once, in its order."""
    refs: list[dict[str, str]] = []
    for geo in (constraint.First, constraint.Second, constraint.Third):
        ref = geometry_ref(sketch, geo) if geo != UNSET else None
        if ref is not None and ref not in refs:
            refs.append(ref)
    return refs


def element(sketch: Any, geo: int) -> dict[str, Any]:
    """One element and the constraints on it; empty if there is none."""
    if not 0 <= geo < len(sketch.Geometry):
        return {}
    constraints = sketch.Constraints
    return {
        "geo": geo,
        "title": geometry_ref(sketch, geo)["title"],
        "construction": bool(sketch.getConstruction(geo)),
        "rows": [constraint_row(sketch, constraints, index)
                 for index, constraint in enumerate(constraints)
                 if geo in (constraint.First, constraint.Second,
                            constraint.Third)],
    }


def _picked(names: list[str]) -> tuple[str, int]:
    """(kind, index from 0) of a lone selection the panel has a card for."""
    if len(names) != 1:
        return "", -1
    name = names[0].rsplit(".", 1)[-1]
    for prefix, kind in _PICKS:
        number = name[len(prefix):]
        if name.startswith(prefix) and number.isdigit() and int(number) > 0:
            return kind, int(number) - 1
    return "", -1


def selection(sketch: Any, names: list[str]) -> dict[str, Any]:
    """The card for what is selected: `kind` is "" when there is none.

    One element or one constraint has a card; a point shows the element
    it belongs to. Axes, external geometry and several things do not.
    """
    kind, index = _picked(names)
    if kind == "constraint":
        constraints = sketch.Constraints
        if index < len(constraints):
            return {"kind": kind,
                    "geometry": _geometry_of(sketch, constraints[index]),
                    **constraint_row(sketch, constraints, index)}
    if kind == "vertex":
        kind = "element"
        index = int(sketch.getGeoVertexIndex(index)[0])
    if kind == "element":
        found = element(sketch, index)
        if found:
            return {"kind": kind, **found}
    return {"kind": ""}
