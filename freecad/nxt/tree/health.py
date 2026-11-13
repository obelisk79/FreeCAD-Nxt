"""Sketch diagnostics, read from the solver's cached results.

Redundant constraints leave `State` clean, so solver results are read
too. Never calls `solve()`; accessors vary by build, so each is probed.
"""

from __future__ import annotations

from typing import Any

from ..app.i18n import QT_TRANSLATE_NOOP, translate

#: A FreeCAD document object; FreeCAD ships no usable type stubs.
DocObject = Any

NONE: int = 0
WARNING = 1
ERROR = 2


def failed_to_recompute() -> str:
    """The note for an object whose recompute failed, translated."""
    return translate("Nxt", "failed to recompute")


#: (attribute, severity, phrase), worst first. Properties on
#: Sketcher::SketchObject holding the last solve's results.
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

#: Names worth showing in a dump.
_INTERESTING = ("redund", "conflict", "malform", "solver", "constrain",
                "dof", "status", "valid", "error")

#: Only these may be called: `autoRemoveRedundants` also matches "redund"
#: and would edit the sketch.
_SAFE_PREFIXES = ("getLast",)
_SAFE_EXACT = (("getStatusString", "isValid", "isTouched", "isError") +
               tuple(name for name, _severity, _phrase in CHECKS))


_ABSENT: object = object()


def _finding(obj: DocObject, name: str) -> bool | list[int] | None:
    """What one attribute says, or None when this build lacks it.

    None means "no information", not "nothing wrong". Accepts a property
    or a zero-argument getter.
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


def findings(obj: DocObject) -> list[tuple[str, int, list[int]]]:
    """(accessor, severity, constraint numbers) of each list not empty."""
    found = []
    for accessor, level, _phrase in CHECKS:
        result = _finding(obj, accessor)
        if isinstance(result, list) and result:
            found.append((accessor, level, result))
    return found


def status_lines(obj: DocObject) -> list[str]:
    """FreeCAD's own status text (`getStatusString()`), as lines."""
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
    """Attributes that might carry solver findings; only getters called.

    `everything` appends the full attribute list.
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
    """Which accessors this object offers."""
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
    """(severity, notes) for one object.

    Remaining degrees of freedom are not a finding: most sketches have them.
    """
    severity = ERROR if in_error else NONE
    notes: list[str] = []

    reported: set[str] = set()
    answered = False
    for accessor, level, phrase in CHECKS:
        if phrase in reported:
            continue
        result = _finding(obj, accessor)
        if result is None:
            continue
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

    # Normally reported once via Snapshot.solver_findings, not per card.
    if not answered and note_unavailable:
        notes.insert(0, translate(
            "Nxt", "solver findings unavailable in this build"))

    # Fall back to FreeCAD's prose; skip it for healthy sketches (cost).
    if not notes and (not answered or severity > NONE or in_error):
        notes.extend(status_lines(obj))

    if in_error and not notes:
        notes.append(failed_to_recompute())

    return severity, notes
