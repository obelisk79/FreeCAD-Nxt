"""Reordering a Part Design Body by drag and drop.

FreeCAD's tree drops a dragged object *into* the row it lands on, which
inside a Body means asking a Pad to take a Pocket as a child: it refuses,
and the drag fails. Part Design's own "Move Feature After" command
(PartDesign_MoveFeatureInTree) reorders instead, by taking each feature out
of the Body and inserting it after a target - which also rewires each solid
feature's BaseFeature to the one now before it. This does the same thing
directly, for a drag: dropping a Body's member on another member of the
same Body puts it just after that one, and dropping it on the Body itself
puts it first.

The command asks for the target in a dialog and checks afterwards whether
the new order is legal, undoing the move if not. A drag has to know before
the drop - the row should refuse the drop while the pointer is over it - so
the check here runs on the planned order, before anything moves, and the
same plan is what gets applied.

`plan` is plain data in and out, so it is tested without FreeCAD.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import FreeCAD as App


@dataclass(frozen=True)
class Plan:
    """A reorder, worked out: the new order, or why there is none."""

    order: tuple[str, ...] = ()
    #: What moves, in its new order: a run of consecutive names in `order`.
    moving: tuple[str, ...] = ()
    #: Empty when the plan is legal; otherwise, in words, why not.
    problem: str = ""

    @property
    def ok(self) -> bool:
        return not self.problem and bool(self.order)


def plan(members: Sequence[str], moving: Sequence[str], after: str | None,
         depends_on: Mapping[str, set[str]], base: str | None = None
         ) -> Plan:
    """The Body's order with `moving` placed after `after` (None: first).

    `members` is the Body's Group in order; `depends_on` maps each member
    to everything it reads, directly or not. The plan is refused if it
    would put anything before something it depends on; which dependencies
    count is `dependencies()`'s business.
    """
    moving = [m for m in members if m in set(moving)]   # keep Body order
    if not moving:
        return Plan(problem="nothing to move")
    if base is not None and base in moving:
        return Plan(problem="the Body's base feature cannot be moved")
    if after is not None and after not in members:
        return Plan(problem="%s is not in this Body" % after)
    if after in moving:
        return Plan(problem="cannot drop onto what is being moved")

    rest = [m for m in members if m not in moving]
    at = rest.index(after) + 1 if after is not None else 0
    order = rest[:at] + moving + rest[at:]
    if order == list(members):
        return Plan(problem="already there")

    position = {name: index for index, name in enumerate(order)}
    for name in order:
        for dependency in depends_on.get(name, ()):
            if position.get(dependency, -1) > position[name]:
                return Plan(problem="%s would come before %s, which it "
                                    "depends on" % (name, dependency))
    return Plan(order=tuple(order), moving=tuple(moving))


# ---------------------------------------------------------------------------
# FreeCAD
# ---------------------------------------------------------------------------

def body_of(obj: Any) -> Any:
    """The Part Design Body holding `obj`, or None."""
    try:
        parent = obj.getParentGeoFeatureGroup()
    except Exception:
        return None
    if parent is not None and parent.TypeId == "PartDesign::Body":
        return parent
    return None


def plan_drop(sources: Sequence[Any], target: Any) -> tuple[Any, Plan]:
    """The Body and the plan, when this drop is a reorder within a Body.

    It is one when every source is a member of the same Body and the target
    is another member of it (place after it) or the Body itself (place
    first). Otherwise the Body is None, and the drop is an ordinary one.
    """
    # Compared by name: FreeCAD may hand back a new Python wrapper for the
    # same object, so `is` is not a test of sameness.
    body = body_of(sources[0]) if sources else None
    if body is None or any(_name(body_of(s)) != body.Name for s in sources):
        return None, Plan()
    if target.Name == body.Name:
        after = None
    elif _name(body_of(target)) == body.Name:
        after = target.Name
    else:
        return None, Plan()

    members = [m.Name for m in body.Group]
    base = body.BaseFeature.Name if body.BaseFeature is not None else None
    return body, plan(members, [s.Name for s in sources], after,
                      dependencies(body), base)


def dependencies(body: Any) -> dict[str, set[str]]:
    """What must stay before each feature: FreeCAD's own rule, exactly.

    Part Design's command allows any order in which no solid feature
    reads - through a sketch, a datum or a binder - a solid feature that
    comes after it. Its direct links to other solid features are left out
    on purpose: the chain of BaseFeature links is rewired by the Body on
    every move, so it never constrains one. Sketches and datums have no
    rule of their own; they are only constrained through the features that
    read them.

    The first version of this constrained every member by everything it
    read, BaseFeature links included, and refused moves the command
    allows.
    """
    solids = {m.Name for m in body.Group
              if _is(m, "PartDesign::Feature")}
    out: dict[str, set[str]] = {}
    for member in body.Group:
        if member.Name not in solids:
            continue
        reads: set[str] = set()
        for obj in member.OutList:
            if _is(obj, "PartDesign::Feature"):
                continue
            try:
                chain = [obj] + list(obj.OutListRecursive)
            except Exception:
                chain = [obj] + list(obj.OutList)
            reads |= {o.Name for o in chain if o.Name in solids}
        reads.discard(member.Name)
        out[member.Name] = reads
    return out


def _name(obj: Any) -> str | None:
    return None if obj is None else str(obj.Name)


def _is(obj: Any, type_name: str) -> bool:
    try:
        return bool(obj.isDerivedFrom(type_name))
    except Exception:
        return False


def apply(body: Any, the_plan: Plan) -> None:
    """Move the Body's members into the planned order, as one undo step.

    The same calls Part Design's command makes - take each moved member
    out, insert it after the one before it - so each solid feature's
    BaseFeature is rewired by the Body, as it is there. The tip is kept
    where it was, except that a feature dropped straight after the tip
    becomes the tip: dropped at the end of the history, it is meant to be
    part of it.
    """
    doc = body.Document
    tip = body.Tip
    moving = list(the_plan.moving)
    doc.openTransaction("Move feature in Body")
    try:
        new_order = list(the_plan.order)
        for name in moving:
            index = new_order.index(name)
            before = doc.getObject(new_order[index - 1]) if index else None
            feature = doc.getObject(name)
            body.removeObject(feature)
            body.insertObject(feature, before, True)
        last = doc.getObject(moving[-1]) if moving else None
        tip_name = tip.Name if tip is not None else None
        dropped_after_tip = (
            last is not None and tip_name is not None
            and tip_name not in moving
            and new_order.index(moving[0]) == new_order.index(tip_name) + 1)
        if (dropped_after_tip and last is not None
                and last.isDerivedFrom("PartDesign::Feature")):
            body.Tip = last
        elif tip is not None and _name(body.Tip) != tip.Name:
            body.Tip = tip
        doc.commitTransaction()
    except Exception:
        doc.abortTransaction()
        raise
    doc.recompute()


def report(problem: str) -> None:
    App.Console.PrintWarning("Nxt: cannot move there - %s\n" % problem)
