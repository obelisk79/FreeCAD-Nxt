"""Sketch diagnostics, read from the solver's cached results.

Two different sources of "something is wrong" meet here.

`obj.State` carries the document's own view: Touched, Invalid, Error. That
is what a failed recompute looks like. It is *not* what a redundant
constraint looks like - a sketch with redundant constraints solves fine and
recomputes fine, so its State is clean, which is why the Report view is the
only place that message appears.

The solver's own findings come from the Sketcher, through the `getLast*`
family. Those read the cache left by the most recent solve, which is free;
this module never calls `solve()`. Re-solving thirty sketches on every
snapshot rebuild is precisely the per-rebuild cost that made the tip drag
unsafe, and a cached answer is stale in exactly the same way the Report
view's message is stale - which is the thing the user is comparing it to.

Which accessors a given FreeCAD build exposes varies, so each is probed
rather than assumed and the panel shows whatever is there. `probe.run()`
prints which were found.
"""

from __future__ import annotations

from typing import Any

from ..i18n import QT_TRANSLATE_NOOP, translate

#: A FreeCAD document object; FreeCAD ships no usable type stubs.
DocObject = Any

NONE: int = 0
WARNING = 1
ERROR = 2


def failed_to_recompute() -> str:
    """The note for an object whose recompute failed, translated."""
    return translate("Nxt", "failed to recompute")


#: (attribute, severity, phrase). Report order, worst first.
#:
#: These are *properties* on Sketcher::SketchObject, not methods - which is
#: what two earlier guesses at a `getLast*` method family got wrong. Reading
#: a property is free and has no side effects, so the panel never re-solves;
#: the values are whatever the last solve left, which is the same thing the
#: solver panel and the Report view are showing.
CHECKS: tuple[tuple[str, int, str], ...] = (
    ("ConflictingConstraints", ERROR,
     QT_TRANSLATE_NOOP("Nxt", "conflicting constraints")),
    ("MalformedConstraints", ERROR,
     QT_TRANSLATE_NOOP("Nxt", "malformed constraints")),
    ("RedundantConstraints", WARNING,
     QT_TRANSLATE_NOOP("Nxt", "redundant constraints")),
    ("PartiallyRedundantConstraints", WARNING,
     QT_TRANSLATE_NOOP("Nxt", "partially redundant constraints")),
)

#: Names worth showing in a dump. Deliberately broad - this is for finding
#: out what a build offers, not for calling things.
_INTERESTING = ("redund", "conflict", "malform", "solver", "constrain",
                "dof", "status", "valid", "error")

#: Only these may actually be invoked. Everything else matching the words
#: above is listed by name and left alone: `autoRemoveRedundants` matches
#: "redund" and would silently edit the user's sketch.
_SAFE_PREFIXES = ("getLast",)
_SAFE_EXACT = (("getStatusString", "isValid", "isTouched", "isError") +
               tuple(name for name, _severity, _phrase in CHECKS))


_ABSENT: object = object()


def _finding(obj: DocObject, name: str) -> bool | list[int] | None:
    """What one attribute says, or None when this build does not have it.

    None means "no information" and must never be confused with "nothing
    wrong" - that conflation is what made an earlier version report a clean
    gutter on a document with a redundant constraint in it. Accepts either a
    property or a zero-argument getter, since which one a build offers has
    already changed once.
    """
    attribute: Any = getattr(obj, name, _ABSENT)
    if attribute is _ABSENT:
        return None
    if callable(attribute):
        try:
            attribute = attribute()
        except Exception:
            return None
    if attribute is None:
        return []
    if isinstance(attribute, bool):
        return attribute
    try:
        return [int(item) for item in attribute]
    except (TypeError, ValueError):
        return []


def status_lines(obj: DocObject) -> list[str]:
    """FreeCAD's own words for this object's state.

    `getStatusString()` is what the stock tree puts in its tooltip, so using
    it verbatim means the panel cannot drift from what the rest of the
    application says. Used as the fallback when the typed properties are
    absent - they give exact constraint indices, this gives prose.
    """
    getter = getattr(obj, "getStatusString", None)
    if not callable(getter):
        return []
    try:
        text = getter() or ""
    except Exception:
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]


def degrees_of_freedom(obj: DocObject) -> int | None:
    value = getattr(obj, "DoF", None)
    return value if isinstance(value, int) else None


def dump(obj: DocObject,
         everything: bool = False) -> list[tuple[str, str]]:
    """Everything this build might carry solver findings in, for one object.

    Read-only by construction: a name is only called if it is clearly a
    getter, because several of the names that match "redundant" are the ones
    that *remove* redundant constraints.

    `everything` appends the full attribute list. Verbose, but it ends the
    guessing - a keyword filter only finds names I thought of.
    """
    rows = [("State", repr(list(getattr(obj, "State", []) or []))),
            ("TypeId", repr(getattr(obj, "TypeId", "")))]

    for name in sorted(dir(obj)):
        if name.startswith("__"):
            continue
        low = name.lower()
        if not any(word in low for word in _INTERESTING):
            continue

        attribute = getattr(obj, name, None)
        if not callable(attribute):
            rows.append((name, repr(attribute)))
            continue

        callable_here = (name.startswith(_SAFE_PREFIXES) or
                         name in _SAFE_EXACT)
        if not callable_here:
            rows.append((name, "<method, not called>"))
            continue
        try:
            rows.append((name, repr(attribute())))
        except Exception as exc:
            rows.append((name, "<raised %s>" % type(exc).__name__))

    if everything:
        names = [n for n in sorted(dir(obj)) if not n.startswith("__")]
        rows.append(("--- every attribute (%d)" % len(names),
                     ", ".join(names)))

    return rows


def available(obj: DocObject) -> dict[str, bool]:
    """Which accessors this object actually offers. For the probe."""
    return {accessor: callable(getattr(obj, accessor, None))
            for accessor, _severity, _phrase in CHECKS}


def fully_constrained(obj: DocObject) -> bool | None:
    value = getattr(obj, "FullyConstrained", None)
    return bool(value) if isinstance(value, bool) else None


def answers(obj: DocObject) -> bool:
    """Whether any solver accessor on this build responds at all."""
    return any(_finding(obj, accessor) is not None
               for accessor, _severity, _phrase in CHECKS)


def inspect(obj: DocObject, in_error: bool = False,
            note_unavailable: bool = False) -> tuple[int, list[str]]:
    """(severity, notes) for one object. Findings only.

    Constraint *state* - degrees of freedom, fully-constrained - is not a
    finding and is not here; `degrees_of_freedom` and `fully_constrained`
    report it separately, and the card shows it on the line that already
    carries the container. In this user's document 18 of 30 sketches have
    degrees of freedom left, so treating that as a finding would mark the
    majority of the sketches and drown the one that needs attention - the
    same mistake the per-row staleness dot made.
    """
    severity = ERROR if in_error else NONE
    notes: list[str] = []

    reported: set[str] = set()
    answered = False
    for accessor, level, phrase in CHECKS:
        if phrase in reported:
            continue            # the other spelling of this finding answered
        result = _finding(obj, accessor)
        if result is None:
            continue            # this build does not have this accessor
        answered = True
        if result is False or result == []:
            continue
        reported.add(phrase)
        severity = max(severity, level)
        if result is True:
            notes.append(translate("Nxt", phrase))
        else:
            notes.append("%s: %s" % (translate("Nxt", phrase),
                                     ", ".join(str(i) for i in result)))

    # Silence is not health - but "this build exposes no solver accessors"
    # is one fact about the installation, not thirty facts about sketches.
    # Repeating it on every card buried the cards that had something to say.
    # The snapshot carries it once instead; see Snapshot.solver_findings.
    if not answered and note_unavailable:
        notes.insert(0, translate(
            "Nxt", "solver findings unavailable in this build"))

    # No typed findings? Fall back to FreeCAD's own prose, which at least
    # says the same thing the solver panel is saying - but only where the
    # typed accessors are absent or something is actually wrong. On a build
    # that answers them, a clean sketch has nothing to add, and calling
    # getStatusString() anyway meant formatting a status string for every
    # healthy sketch on every rebuild to produce text no row displays.
    if not notes and (not answered or severity > NONE or in_error):
        notes.extend(status_lines(obj))

    if in_error and not notes:
        notes.append(failed_to_recompute())

    return severity, notes
