"""Which feature made the thing picked in the 3D view.

A Part Design Body shows one solid: its tip's. Pick a face on it and
FreeCAD's selection names the tip, whichever feature actually made that
face - so revealing the selected object always lands on the last feature
in the Body. The answer is in the shape's element map (FreeCAD 1.0's
toponaming): every face, edge and vertex carries the tag of the object
that generated it, and a face a later feature left untouched keeps its
original tag. `origin` reads that tag and finds the object it belongs to.

The tag is read from the mapped element name the pick carries, e.g.
";#134:46b;:H16,F": ";:H16" is object ID 0x16. FreeCAD's
getElementHistory is asked first; on the files tried it answered None
for the indexed name ("Face23"), so the mapped name is read directly.

This only decides which row to show. The selection itself is FreeCAD's
and stays on what FreeCAD selected.
"""

from __future__ import annotations

import re
from typing import Any

#: A tag in a mapped element name: ";:H16" is the object with ID 0x16.
#: The name is built outward, one postfix per operation, so the last tag
#: is the object that generated the element.
_TAG = re.compile(r";:H(-?[0-9a-fA-F]+)")


def element_of(subname: str) -> str:
    """The indexed element at the end of a subname: "Pad.Face6" -> "Face6".

    Empty when the subname names an object rather than an element.
    """
    leaf = subname.rsplit(".", 1)[-1] if subname else ""
    return "" if leaf.startswith(";") else leaf


def mapped_of(subname: str) -> str:
    """The mapped element name in a subname, without its ";" marker.

    A pick in the 3D view names the element both ways -
    "Pocket002.;#134:46b;:H16,F.Face23" - and the mapped name, which
    records where the element came from, is the one that says who made
    it. Empty when there is none.
    """
    for part in subname.split("."):
        if part.startswith(";"):
            return part[1:]
    return ""


#: Most steps a trace takes: a chain longer than this is a loop.
_MAX_STEPS = 32


def _history(obj: Any, name: str) -> tuple[int, str]:
    """One step back: (owner ID, the name the owner made it from).

    FreeCAD's getElementHistory is asked with the name as given and with
    and without its ";" marker. The ID comes back negative for an element
    generated from other geometry; the object is the same either way.
    (0, "") when FreeCAD knows nothing more.
    """
    names = [name]
    if name.startswith(";"):
        names.append(name[1:])
    else:
        names.insert(0, ";" + name)
    for candidate in names:
        try:
            history = obj.Shape.getElementHistory(candidate)
        except Exception:
            continue
        if history and isinstance(history[0], int) and history[0] != 0:
            return abs(history[0]), str(history[1] or "")
    return 0, ""


def _tag_in(name: str) -> int:
    """The outermost object tag written into a mapped name, or 0."""
    tags = _TAG.findall(name)
    try:
        return abs(int(tags[-1], 16)) if tags else 0
    except ValueError:
        return 0


def _by_id(doc: Any, ident: int) -> Any:
    for candidate in getattr(doc, "Objects", []):
        if getattr(candidate, "ID", None) == ident:
            return candidate
    return None


def _is_feature(obj: Any) -> bool:
    """A solid feature: something whose shape a face can belong to."""
    try:
        return bool(obj.isDerivedFrom("PartDesign::Feature")
                    or obj.isDerivedFrom("Part::Feature")
                    and not obj.isDerivedFrom("Part::Part2DObject"))
    except Exception:
        return False


def origin(obj: Any, subname: str) -> Any:
    """The feature that first made the picked element of `obj`, or None.

    Walks the element map back one owner at a time. Each step gives the
    object that last produced the element and the name it had in that
    object's input. ";:G" marks one generated there, and the walk ends at
    that owner. Anything else - ";:M", an element that existed before and
    was only changed (a face a later Pocket cut a hole in), or a bare tag,
    one carried through untouched - keeps going back, into the earlier
    feature's own shape. A step whose earlier owner is not a solid feature
    (a sketch, whose edges were extruded) also ends the walk.

    The part of a mapped name before its last tag is often hashed
    ("#ac:1123"), which hides the markers inside it; those come to light
    at the next step, when the earlier feature is asked in turn.

    From FreeCAD 26.3, for a face Pocket made and Pocket001 then cut:
    (22, "#b8:1127;:M;CUT;:H13:7,F") - Pocket001 changed it, and before
    that it was ";:H13", the Pocket (ID 0x13) - which is the answer.

    None when the pick has no element map, or when `obj` itself made it.
    """
    mapped = mapped_of(subname)
    name = ";" + mapped if mapped else element_of(subname)
    if not name:
        return None
    doc = obj.Document
    current = obj
    found = None
    seen: set[int] = set()
    for _step in range(_MAX_STEPS):
        owner_id, before = _history(current, name)
        if not owner_id and current is obj:
            owner_id = _tag_in(mapped)      # FreeCAD had nothing to say
        owner = _by_id(doc, owner_id) if owner_id else None
        if owner is None or not _is_feature(owner) or owner_id in seen:
            break
        seen.add(owner_id)
        found = owner
        earlier = _by_id(doc, _tag_in(before)) if before else None
        if (";:G" in before or earlier is None
                or not _is_feature(earlier) or earlier is owner):
            break
        # Changed (";:M") or only carried through here: ask the earlier
        # feature's own shape.
        current, name, found = earlier, before, earlier
    if found is None or found is obj or found.Name == obj.Name:
        return None
    return found


def full_pick(top_name: str, subname: str,
              selection: Any) -> tuple[str, str]:
    """The pick as the selection holds it: (top object, full subname).

    The observer is told the picked object and its element -
    ("Pocket002", "Face23") - while the selection keeps the path from the
    top-level object with the mapped name in it -
    ("Body", "Pocket002.;#134:46b;:H16,F.Face23") - and only that one says
    who made the face. `selection` is Gui.Selection.getSelectionEx(doc, 0);
    the most recent matching entry wins. Unchanged when nothing matches.
    """
    wanted = element_of(subname)
    for entry in reversed(list(selection or [])):
        entry_top = getattr(entry.Object, "Name", None)
        for candidate in reversed(list(entry.SubElementNames or [])):
            if not mapped_of(candidate) or element_of(candidate) != wanted:
                continue
            path = candidate.split(".")[:-2]
            if entry_top == top_name or top_name in path:
                return str(entry_top), candidate
    return top_name, subname


def target(doc: Any, top_name: str, subname: str) -> str | None:
    """The name of the row to reveal for one pick, or None.

    `top_name` and `subname` are what the selection observer is given: the
    top-level object and the path below it, "Pad001.Face6" under a Body.
    The picked object is the one the path leads to; when its element was
    made by an earlier feature, that feature is the answer.
    """
    top = doc.getObject(top_name) if doc is not None else None
    if top is None:
        return None
    picked = top
    if subname:
        try:
            leaf = top.getSubObject(subname, retType=1)
        except Exception:
            leaf = None
        if leaf is not None:
            picked = leaf
    made_by = origin(picked, subname)
    return (made_by or picked).Name
