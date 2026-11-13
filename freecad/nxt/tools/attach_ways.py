"""Ways to attach: FreeCAD's attachment modes, grouped by what they do.

FreeCAD lists every mode of an attach engine, several of them one idea
with the axes in another order. A way is one idea (Along path); its
variants are the modes it chooses between (the three Frenet planes).
A mode no way names (a datum line's or point's) is a way of its own,
under FreeCAD's name for it. Pure Python: no FreeCAD, no Qt.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, NamedTuple

from ..app.i18n import QT_TRANSLATE_NOOP

DETACHED = "Deactivated"
#: Most references an attachment takes.
MOST_REFERENCES = 4


class Way(NamedTuple):
    """One way to attach, and the modes it chooses between."""

    key: str
    label: str
    #: Mode -> its variant's label, in the order offered.
    modes: dict[str, str]
    #: What the variants choose ("Plane"); empty with one mode.
    choice: str = ""
    #: Its modes read MapPathParameter.
    along_path: bool = False


PLANE = QT_TRANSLATE_NOOP("Nxt", "Plane")

#: Names follow commercial CAD where it has the idea (Midplane, Along
#: path, Normal to edge); the rest place a whole coordinate system.
WAYS: tuple[Way, ...] = (
    Way("face", QT_TRANSLATE_NOOP("Nxt", "On face"), {"FlatFace": ""}),
    Way("tangent", QT_TRANSLATE_NOOP("Nxt", "Tangent to surface"),
        {"TangentPlane": ""}),
    Way("midplane", QT_TRANSLATE_NOOP("Nxt", "Midplane"),
        {"MidPlane": ""}),
    Way("three", QT_TRANSLATE_NOOP("Nxt", "Through 3 points"),
        {"ThreePointsPlane": "XY", "ThreePointsNormal": "XZ"}, PLANE),
    Way("normal", QT_TRANSLATE_NOOP("Nxt", "Normal to edge"),
        {"NormalToEdge": ""}, along_path=True),
    Way("path", QT_TRANSLATE_NOOP("Nxt", "Along path"),
        {"FrenetNB": QT_TRANSLATE_NOOP("Nxt", "Across"),
         "FrenetTN": QT_TRANSLATE_NOOP("Nxt", "In bend"),
         "FrenetTB": QT_TRANSLATE_NOOP("Nxt", "Beside")},
        PLANE, along_path=True),
    Way("concentric", QT_TRANSLATE_NOOP("Nxt", "Concentric"),
        {"Concentric": QT_TRANSLATE_NOOP("Nxt", "Circle"),
         "SectionOfRevolution": QT_TRANSLATE_NOOP("Nxt", "Section")},
        PLANE, along_path=True),
    Way("parallel", QT_TRANSLATE_NOOP("Nxt", "Parallel plane"),
        {"ParallelPlane": ""}),
    Way("object", QT_TRANSLATE_NOOP("Nxt", "Same as object"),
        {"ObjectXY": "XY", "ObjectXZ": "XZ", "ObjectYZ": "YZ"}, PLANE),
    Way("inertia", QT_TRANSLATE_NOOP("Nxt", "Inertia axes"),
        {"InertialCS": ""}),
    Way("align", QT_TRANSLATE_NOOP("Nxt", "Align to points"),
        {"OZX": "Z, X", "OZY": "Z, Y", "OXY": "X, Y", "OXZ": "X, Z",
         "OYZ": "Y, Z", "OYX": "Y, X"},
        QT_TRANSLATE_NOOP("Nxt", "Axes")),
    Way("translate", QT_TRANSLATE_NOOP("Nxt", "Move origin only"),
        {"Translate": ""}),
    Way("folding", QT_TRANSLATE_NOOP("Nxt", "Folding"), {"Folding": ""}),
)

#: FreeCAD's reference types -> the word a pick is shown with.
PICKS: dict[str, str] = {
    "Vertex": QT_TRANSLATE_NOOP("Nxt", "Point"),
    "Edge": QT_TRANSLATE_NOOP("Nxt", "Edge"),
    "Line": QT_TRANSLATE_NOOP("Nxt", "Line"),
    "Curve": QT_TRANSLATE_NOOP("Nxt", "Curve"),
    "Circle": QT_TRANSLATE_NOOP("Nxt", "Circle"),
    "Conic": QT_TRANSLATE_NOOP("Nxt", "Curve"),
    "Ellipse": QT_TRANSLATE_NOOP("Nxt", "Curve"),
    "Parabola": QT_TRANSLATE_NOOP("Nxt", "Curve"),
    "Hyperbola": QT_TRANSLATE_NOOP("Nxt", "Curve"),
    "Face": QT_TRANSLATE_NOOP("Nxt", "Face"),
    "Plane": PLANE,
    "Sphere": QT_TRANSLATE_NOOP("Nxt", "Face"),
    "Revolve": QT_TRANSLATE_NOOP("Nxt", "Face"),
    "Cylinder": QT_TRANSLATE_NOOP("Nxt", "Face"),
    "Torus": QT_TRANSLATE_NOOP("Nxt", "Face"),
    "Cone": QT_TRANSLATE_NOOP("Nxt", "Face"),
}
OBJECT = QT_TRANSLATE_NOOP("Nxt", "Object")
#: Reference types -> the glyph a pick is drawn with.
SHAPES: dict[str, str] = {
    "Vertex": "point", "Edge": "edge", "Line": "edge", "Curve": "curve",
    "Circle": "curve", "Conic": "curve", "Ellipse": "curve",
    "Parabola": "curve", "Hyperbola": "curve"}

#: FreeCAD's message (a fragment, lower case) -> what went wrong in plain
#: words, and what to do about it.
PROBLEMS: tuple[tuple[str, str, str], ...] = (
    ("collinear",
     QT_TRANSLATE_NOOP("Nxt", "These points are in a line, so no plane "
                              "fits."),
     QT_TRANSLATE_NOOP("Nxt", "Pick a point off the line.")),
    ("coincident",
     QT_TRANSLATE_NOOP("Nxt", "Two picks are at the same place."),
     QT_TRANSLATE_NOOP("Nxt", "Pick another one.")),
    ("parallel",
     QT_TRANSLATE_NOOP("Nxt", "The picks are parallel, so they do not "
                              "meet."),
     QT_TRANSLATE_NOOP("Nxt", "Pick one at an angle to the other.")),
)

_BY_MODE: dict[str, Way] = {mode: way for way in WAYS for mode in way.modes}
_KEYS = frozenset(way.key for way in WAYS)


def way_of(mode: str) -> Way:
    """The way `mode` belongs to; a way of its own if none names it."""
    return _BY_MODE.get(mode) or Way(mode, mode, {mode: ""})


def pick_word(ref_type: str) -> str:
    """The word a pick of FreeCAD's reference type is shown with."""
    return PICKS.get(ref_type, OBJECT)


def pick_shape(ref_type: str) -> str:
    """The glyph for a pick: point, edge, curve, face or object."""
    if ref_type in SHAPES:
        return SHAPES[ref_type]
    return "face" if ref_type in PICKS else "object"


def problem(message: str) -> tuple[str, str]:
    """FreeCAD's error as (what went wrong, what to do), untranslated."""
    lowered = message.lower()
    for fragment, what, fix in PROBLEMS:
        if fragment in lowered:
            return what, fix
    return message, ""


def ways(implemented: Iterable[str], suggestion: dict[str, Any],
         current: str) -> list[dict[str, Any]]:
    """The ways offered for the picks so far, those that fit first.

    With picks, a way is offered if it fits them or more picks would
    make it fit (`needs`: FreeCAD's reference types to add); with none,
    every way the engine has.
    """
    applicable = set(suggestion.get("allApplicableModes") or ())
    reachable: dict[str, list[list[str]]] = \
        suggestion.get("reachableModes") or {}
    picked = bool(suggestion.get("references_Types"))
    have = [mode for mode in implemented if mode != DETACHED]
    seen = {way_of(mode).key: way_of(mode) for mode in have}
    ordered = [way for way in WAYS if way.key in seen] + [
        way for key, way in seen.items() if key not in _KEYS]
    fits, later = [], []
    for way in ordered:
        modes = [mode for mode in way.modes if mode in have]
        fit = any(mode in applicable for mode in modes)
        needs = next((reachable[mode][0] for mode in modes
                      if reachable.get(mode)), None)
        if picked and not fit and needs is None:
            continue
        row = {"key": way.key, "label": way.label, "fits": fit,
               "needs": [] if fit or needs is None else list(needs),
               "current": current in way.modes}
        (fits if fit else later).append(row)
    return fits + later


def variants(way: Way, implemented: Iterable[str]) -> list[dict[str, str]]:
    """The way's modes this engine has, as {value, label}."""
    have = set(implemented)
    return [{"value": mode, "label": label}
            for mode, label in way.modes.items() if mode in have]


def mode_after_picks(current: str, wanted: str,
                     suggestion: dict[str, Any]) -> str:
    """The mode once the picks change.

    One asked for before its picks were made, once they are; else the
    current one while it still fits; else FreeCAD's best fit; else
    detached.
    """
    applicable = suggestion.get("allApplicableModes") or ()
    for mode in (wanted, current):
        if mode and mode != DETACHED and mode in applicable:
            return mode
    if suggestion.get("message") == "OK":
        return str(suggestion.get("bestFitMode") or DETACHED)
    return DETACHED


def mode_for_way(way: Way, current: str,
                 applicable: Iterable[str]) -> str:
    """Which of the way's modes a choice of it means.

    The current mode if it is one; else the first that fits the picks;
    else the first.
    """
    if current in way.modes:
        return current
    fitting = [mode for mode in way.modes if mode in set(applicable)]
    return fitting[0] if fitting else next(iter(way.modes))


def needs_text(needs: list[str], word: Callable[[str], str]) -> str:
    """'a point + a face' from FreeCAD's reference types."""
    return " + ".join(word(pick_word(ref)).lower() for ref in needs)
