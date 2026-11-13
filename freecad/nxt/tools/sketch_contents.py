"""A sketch's elements and constraints, as the Contents card lists them.

No Qt. `read` takes one snapshot of the sketch per change; `rows` lays
that snapshot out for one view (a tab, a search, filters, folded groups,
the selection) without reading the sketch again, so a selection change
or a keystroke in the search costs no FreeCAD calls. A dimension's text
is not in the snapshot: the model formats it only for rows on screen.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import Any

from ..app.i18n import QT_TRANSLATE_NOOP, translate
from ..tree import health
from .sketch_state import (
    CONSTRAINT_LABELS,
    DIMENSIONAL,
    ELEMENT,
    ELEMENT_LABELS,
)

ELEMENTS, CONSTRAINTS = "elements", "constraints"
#: Element filters, then constraint filters.
FREE, CONSTRUCTION, EXTERNAL = "free", "construction", "external"
FLAGGED, REFERENCE, INACTIVE = "flagged", "reference", "inactive"
FILTERS = {ELEMENTS: (FREE, CONSTRUCTION, EXTERNAL),
           CONSTRAINTS: (FLAGGED, REFERENCE, INACTIVE)}

#: A geometric group longer than this starts folded.
FOLD_ABOVE = 12
#: Constraint chips shown on an element's strip before "+n".
CHIP_CAP = 6
#: A constraint's geometry index where it names none (GeoEnum::GeoUndef).
UNSET = -2000
#: External geometry's indices count down from this one (GeoEnum::RefExt).
FIRST_EXTERNAL = -3
#: ExternalGeo holds the two axes first, then the external geometry.
AXES_IN_EXTERNAL_GEO = 2

#: The status marks, as SeverityMark.qml draws them.
MARK_NONE, MARK_FREE = 0, 1

DIMENSIONS_GROUP = "dimensions"
EXTERNAL_LABEL = QT_TRANSLATE_NOOP("Nxt", "External")
DIMENSIONS_LABEL = QT_TRANSLATE_NOOP("Nxt", "Dimensions")
CONSTRUCTION_LABEL = QT_TRANSLATE_NOOP("Nxt", "construction")
#: What part of an element is still free, by Sketcher's PointPos.
PARTS: dict[int, str] = {
    0: QT_TRANSLATE_NOOP("Nxt", "edge"),
    1: QT_TRANSLATE_NOOP("Nxt", "start"),
    2: QT_TRANSLATE_NOOP("Nxt", "end"),
    3: QT_TRANSLATE_NOOP("Nxt", "centre"),
}
#: Axes, by geometry index, as a constraint's chips name them.
AXES: dict[int, tuple[str, str]] = {
    -1: ("H_Axis", QT_TRANSLATE_NOOP("Nxt", "Horizontal axis")),
    -2: ("V_Axis", QT_TRANSLATE_NOOP("Nxt", "Vertical axis")),
}


@dataclass(frozen=True)
class Element:
    geo: int
    title: str
    construction: bool
    free: tuple[int, ...]


@dataclass(frozen=True)
class Constraint:
    index: int
    kind: str
    label: str
    name: str
    geometry: tuple[int, ...]
    driving: bool
    active: bool
    raw: float
    mark: int

    @property
    def dimensional(self) -> bool:
        return self.kind in DIMENSIONAL


@dataclass
class Snapshot:
    """One reading of the sketch; nothing in it calls FreeCAD again."""

    elements: list[Element] = field(default_factory=list)
    externals: list[str] = field(default_factory=list)
    constraints: list[Constraint] = field(default_factory=list)
    #: Element geometry index -> indices of the constraints on it.
    on: dict[int, list[int]] = field(default_factory=dict)

    def element_title(self, geo: int) -> str:
        if 0 <= geo < len(self.elements):
            return self.elements[geo].title
        if geo in AXES:
            return translate("Nxt", AXES[geo][1])
        number = FIRST_EXTERNAL - geo + 1
        return "%s %d" % (translate("Nxt", EXTERNAL_LABEL), number)


def element_name(geo: int) -> str:
    """Sketcher's selection name for a geometry index."""
    if geo in AXES:
        return AXES[geo][0]
    if geo <= FIRST_EXTERNAL:
        return "ExternalEdge%d" % (FIRST_EXTERNAL - geo + 1)
    return "Edge%d" % (geo + 1)


def _title(geometry: Any, number: int) -> str:
    label = ELEMENT_LABELS.get(type(geometry).__name__, ELEMENT)
    return "%s %d" % (translate("Nxt", label), number)


def _free_parts(sketch: Any) -> dict[int, list[int]]:
    """Each element's parts the solver says can still move."""
    found: dict[int, list[int]] = {}
    with contextlib.suppress(Exception):  # a build without the call
        for geo, part in sketch.getGeometryWithDependentParameters():
            found.setdefault(int(geo), []).append(int(part))
    return found


def _marks(sketch: Any) -> dict[int, int]:
    """Constraint index -> the mark of the worst finding naming it."""
    marks: dict[int, int] = {}
    for _accessor, severity, numbers in reversed(health.findings(sketch)):
        for number in numbers:
            marks[number - 1] = severity + MARK_FREE
    return marks


def read(sketch: Any) -> Snapshot:
    """The sketch's contents, read once."""
    snap = Snapshot()
    free = _free_parts(sketch)
    for geo, geometry in enumerate(sketch.Geometry):
        snap.elements.append(Element(
            geo, _title(geometry, geo + 1),
            bool(sketch.getConstruction(geo)),
            tuple(sorted(free.get(geo, ())))))
    external = list(getattr(sketch, "ExternalGeo", []) or [])
    snap.externals = [
        "%s %d" % (translate("Nxt", EXTERNAL_LABEL), number)
        for number, _geometry in enumerate(
            external[AXES_IN_EXTERNAL_GEO:], start=1)]
    marks = _marks(sketch)
    for index, constraint in enumerate(sketch.Constraints):
        kind = str(constraint.Type)
        geometry = tuple(dict.fromkeys(
            geo for geo in (constraint.First, constraint.Second,
                            constraint.Third) if geo != UNSET))
        snap.constraints.append(Constraint(
            index, kind, translate("Nxt", CONSTRAINT_LABELS.get(kind, kind)),
            str(constraint.Name or ""), geometry,
            bool(constraint.Driving),
            bool(getattr(constraint, "IsActive", True)),
            float(constraint.Value), marks.get(index, MARK_NONE)))
        for geo in geometry:
            snap.on.setdefault(geo, []).append(index)
    return snap


@dataclass
class View:
    """How the card is looked at: none of it is in the sketch."""

    tab: str = ELEMENTS
    query: str = ""
    filters: frozenset[str] = frozenset()
    #: Group key -> folded, where the user chose; else by FOLD_ABOVE.
    folds: dict[str, bool] = field(default_factory=dict)
    #: Selection names inside the sketch ("Edge3", "Constraint2").
    selected: tuple[str, ...] = ()
    #: Selection name -> geometry index, for points ("Vertex4").
    vertex_geo: dict[str, int] = field(default_factory=dict)


def _keys(view: View) -> tuple[set[int], set[int], set[int]]:
    """Selected elements, external numbers and constraint indices."""
    elements: set[int] = set()
    externals: set[int] = set()
    constraints: set[int] = set()
    for name in view.selected:
        for prefix, into in (("ExternalEdge", externals),
                             ("Constraint", constraints),
                             ("Edge", elements)):
            number = name[len(prefix):]
            if name.startswith(prefix) and number.isdigit():
                into.add(int(number) - 1)
                break
        else:
            if name in view.vertex_geo:
                elements.add(view.vertex_geo[name])
    return elements, externals, constraints


def _matches(query: str, *texts: str) -> bool:
    return not query or any(query in text.lower() for text in texts)


def _row(key: str, kind: str, **fields: Any) -> dict[str, Any]:
    base = {"key": key, "kind": kind, "title": "", "detail": "",
            "number": 0, "mark": MARK_NONE, "dashed": False,
            "selected": False, "folded": False, "count": 0, "index": -1,
            "name": "", "editable": False, "driving": False,
            "active": True, "chips": [], "more": 0, "fixes": False,
            "raw": 0.0}
    base.update(fields)
    return base


def _chips(snap: Snapshot, indices: list[int]) -> tuple[list[Any], int]:
    """A strip's constraint chips, dimensions first, and how many more."""
    ordered = sorted(indices, key=lambda i: (
        not snap.constraints[i].dimensional, i))
    chips = []
    for index in ordered[:CHIP_CAP]:
        c = snap.constraints[index]
        said = c.name or c.label
        chips.append({"title": "%d  %s" % (index + 1, said),
                      "name": "Constraint%d" % (index + 1),
                      "index": index, "dimensional": c.dimensional})
    return chips, max(0, len(ordered) - CHIP_CAP)


def _element_rows(snap: Snapshot, view: View, query: str) -> list[Any]:
    chosen, chosen_ext, chosen_constraints = _keys(view)
    lone = len(chosen) == 1 and not chosen_ext and not chosen_constraints
    out: list[Any] = []
    for e in snap.elements:
        wanted = view.filters & {FREE, CONSTRUCTION, EXTERNAL}
        if wanted and not ((FREE in wanted and e.free)
                           or (CONSTRUCTION in wanted and e.construction)):
            continue
        detail = ""
        if FREE in view.filters and e.free:
            detail = ", ".join(translate("Nxt", PARTS.get(p, ""))
                               for p in e.free)
        elif e.construction:
            detail = translate("Nxt", CONSTRUCTION_LABEL)
        if not _matches(query, e.title, "#%d" % (e.geo + 1)):
            continue
        selected = e.geo in chosen
        out.append(_row("e%d" % e.geo, "element", title=e.title,
                        detail=detail, index=e.geo,
                        name=element_name(e.geo),
                        mark=MARK_FREE if e.free else MARK_NONE,
                        dashed=e.construction, selected=selected))
        if selected and lone:
            chips, more = _chips(snap, snap.on.get(e.geo, []))
            out.append(_row("s%d" % e.geo, "elementStrip", index=e.geo,
                            dashed=e.construction, chips=chips, more=more,
                            detail="%d DoF" % len(e.free) if e.free
                            else ""))
    wanted = view.filters & {FREE, CONSTRUCTION, EXTERNAL}
    if not wanted or EXTERNAL in wanted:
        for number, title in enumerate(snap.externals, start=1):
            if _matches(query, title):
                out.append(_row("x%d" % number, "element", title=title,
                                index=FIRST_EXTERNAL - number + 1,
                                name="ExternalEdge%d" % number,
                                selected=number - 1 in chosen_ext))
    return out


def _constraint_row(c: Constraint, selected: bool) -> dict[str, Any]:
    return _row("c%d" % c.index, "constraint", number=c.index + 1,
                title=c.name or c.label,
                detail=c.label if c.name else "", index=c.index,
                name="Constraint%d" % (c.index + 1), mark=c.mark,
                dashed=not c.driving, selected=selected,
                editable=c.dimensional and c.driving, driving=c.driving,
                active=c.active, fixes=c.mark > MARK_FREE, raw=c.raw)


def _constraint_strip(snap: Snapshot, c: Constraint) -> dict[str, Any]:
    chips = [{"title": snap.element_title(geo), "name": element_name(geo),
              "index": geo, "dimensional": False} for geo in c.geometry]
    return _row("t%d" % c.index, "constraintStrip", index=c.index,
                title=c.name, chips=chips, driving=c.driving,
                active=c.active, editable=c.dimensional)


def _wanted(c: Constraint, filters: frozenset[str]) -> bool:
    wanted = filters & {FLAGGED, REFERENCE, INACTIVE}
    return not wanted or ((FLAGGED in wanted and c.mark > MARK_FREE)
                          or (REFERENCE in wanted and not c.driving)
                          or (INACTIVE in wanted and not c.active))


def _constraint_rows(snap: Snapshot, view: View, query: str,
                     texts: dict[int, str]) -> list[Any]:
    elements, externals, chosen = _keys(view)
    lone = len(chosen) == 1 and not elements and not externals
    groups: dict[str, list[Constraint]] = {}
    for c in snap.constraints:
        if not _wanted(c, view.filters) or not _matches(
                query, c.name, c.label, "#%d" % (c.index + 1),
                texts.get(c.index, "")):
            continue
        groups.setdefault(DIMENSIONS_GROUP if c.dimensional else c.kind,
                          []).append(c)
    out: list[Any] = []
    order = sorted(groups, key=lambda g: (g != DIMENSIONS_GROUP,
                                          groups[g][0].label))
    for group in order:
        members = sorted(groups[group], key=lambda c: (
            c.mark <= MARK_FREE,
            group == DIMENSIONS_GROUP and not c.name, c.index))
        flagged = any(c.mark > MARK_FREE for c in members)
        folded = view.folds.get(group, group != DIMENSIONS_GROUP
                                and len(members) > FOLD_ABOVE)
        # A search, a selection or a problem inside opens the group.
        folded = folded and not query and not flagged and not any(
            c.index in chosen for c in members)
        title = translate("Nxt", DIMENSIONS_LABEL) \
            if group == DIMENSIONS_GROUP else members[0].label
        out.append(_row("g:" + group, "group", title=title,
                        count=len(members), folded=folded,
                        mark=max(c.mark for c in members)))
        if folded:
            continue
        for c in members:
            selected = c.index in chosen
            out.append(_constraint_row(c, selected))
            if selected and lone:
                out.append(_constraint_strip(snap, c))
    return out


def summary(snap: Snapshot, view: View) -> dict[str, int]:
    """What a selection of several things holds, by kind."""
    elements, externals, constraints = _keys(view)
    return {"elements": len(elements), "externals": len(externals),
            "constraints": len(constraints)}


def counts(snap: Snapshot) -> dict[str, int]:
    """Totals for the tabs and the filter chips."""
    return {
        ELEMENTS: len(snap.elements) + len(snap.externals),
        CONSTRAINTS: len(snap.constraints),
        FREE: sum(1 for e in snap.elements if e.free),
        CONSTRUCTION: sum(1 for e in snap.elements if e.construction),
        EXTERNAL: len(snap.externals),
        FLAGGED: sum(1 for c in snap.constraints if c.mark > MARK_FREE),
        REFERENCE: sum(1 for c in snap.constraints if not c.driving),
        INACTIVE: sum(1 for c in snap.constraints if not c.active),
    }


def rows(snap: Snapshot, view: View,
         texts: dict[int, str] | None = None) -> list[dict[str, Any]]:
    """The rows one view shows, in order; `texts` are dimension values."""
    query = view.query.strip().lower()
    out: list[Any] = []
    held = summary(snap, view)
    if sum(held.values()) > 1:
        out.append(_row("summary", "summary", count=sum(held.values()),
                        number=held["elements"], index=held["constraints"]))
    if view.tab == ELEMENTS:
        out += _element_rows(snap, view, query)
    else:
        out += _constraint_rows(snap, view, query, texts or {})
    return out
