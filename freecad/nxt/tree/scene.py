"""Pure-Python snapshot of a FreeCAD document, for the timeline panel.

No Qt imports, so it runs headlessly under `freecadcmd` and in tests.
"""

from __future__ import annotations

import contextlib
import re
import traceback
from collections.abc import Container, Iterable, Sequence
from dataclasses import InitVar, dataclass, field
from typing import Any

import FreeCAD as App

from . import health

#: A FreeCAD document object or document; FreeCAD ships no usable stubs.
DocObject = Any

#: {target name: [(property name, [sub-elements])]}, per holder.
LinkTable = dict[str, list[tuple[str, list[str]]]]

# -- what counts as a profile --

#: Always lifted out of its consumer and placed in the timeline.
PROFILE_BASES = ("Sketcher::SketchObject",)

#: Lifted only when `widen` is on (Draft wires, circles, b-splines).
PROFILE_BASES_WIDE = ("Part::Part2DObject",)

#: Body stack members; a BaseFeature property separates them from datums
#: and binders that merely live in the Body.
FEATURE_BASES = ("PartDesign::Feature",)

BODY_BASES = ("PartDesign::Body",)

#: Part operations own their operands (a Cut's Base and Tool), so those
#: stay nested; profiles are still lifted.
NESTING_PREFIX = "Part::"

#: Tree layouts. NESTED mirrors FreeCAD's tree; EXPRESSION puts sketches
#: beside Body features and lists a Part model's steps flat under its
#: latest operation, with a history bar.
NESTED, EXPRESSION = "nested", "expression"

#: Free datums are filed like sketches; Origins share the bases but stay.
DATUM_BASES = ("Part::Datum", "App::DatumElement",
               "App::LocalCoordinateSystem")
ORIGIN_BASES = ("App::Origin", "App::OriginFeature")

#: Outside a Body, binders are ordinary Part inputs (model steps).
BINDER_BASES = ("PartDesign::ShapeBinder", "PartDesign::SubShapeBinder")

#: Panel-only groups; the document is never restructured (moving a sketch
#: out of an App::Part moves it in space). "~" is never in object names.
VIRTUAL_PREFIX = "~"
COMPARTMENTS: tuple[tuple[str, str], ...] = (
    ("Sketches", "is_profile"), ("Datum Objects", "is_datum"))


def is_virtual(name: str) -> bool:
    return name.startswith(VIRTUAL_PREFIX)


def natural_key(text: str) -> list[int | str]:
    """Sketch2 before Sketch10."""
    return [int(part) if part.isdigit() else part.lower()
            for part in re.split(r"(\d+)", text)]


#: Only modelling workbenches' claims are lifted; others (e.g. a CAM Job's)
#: stay as FreeCAD's tree has them.
LIFTING_PREFIXES = ("PartDesign::", "Part::", "Sketcher::")

CONTAINER_BASES = (
    "PartDesign::Body",
    "App::Part",
    "App::DocumentObjectGroup",
)

#: Link properties that express containment rather than consumption.
CONTAINMENT_PROPS = frozenset({
    "Group", "Origin", "OriginFeatures", "_GroupTouched", "Tip", "BaseFeature",
})


def _derived(obj: DocObject, bases: Iterable[str]) -> bool:
    for base in bases:
        with contextlib.suppress(Exception):
            if obj.isDerivedFrom(base):
                return True
    return False


def is_joint(obj: DocObject) -> bool:
    """An Assembly joint; they carry no common type, only properties."""
    return any(hasattr(obj, prop) for prop in JOINT_PROPERTIES)


#: Joints have JointType; a grounding "joint" has ObjectToGround.
JOINT_PROPERTIES = ("JointType", "ObjectToGround")


COORDINATE_SYSTEM_BASES = ("App::LocalCoordinateSystem", "App::Origin")


def _in_coordinate_system(obj: DocObject) -> bool:
    """One of an Origin's or LCS's own point, axes or planes.

    From FreeCAD 26 these are plain datum elements; only the holder's
    OriginFeatures tells them from user datums.
    """
    for holder in getattr(obj, "InList", None) or ():
        if not _derived(holder, COORDINATE_SYSTEM_BASES):
            continue
        try:
            features = getattr(holder, "OriginFeatures", None) or ()
        except Exception:
            features = ()
        if any(getattr(f, "Name", None) == obj.Name for f in features):
            return True
    return False


def is_profile(obj: DocObject, widen: bool = False) -> bool:
    if _derived(obj, PROFILE_BASES):
        return True
    if widen and _derived(obj, PROFILE_BASES_WIDE):
        return True
    return False


def is_container(obj: DocObject) -> bool:
    return _derived(obj, CONTAINER_BASES)


def nests_operands(obj: DocObject) -> bool:
    return str(getattr(obj, "TypeId", "")).startswith(NESTING_PREFIX)


# -- hierarchy discovery --

def claim_children(obj: DocObject) -> list[DocObject]:
    """Best-effort ViewProvider::claimChildren(), falling back to Group."""
    vo = getattr(obj, "ViewObject", None)

    if vo is not None:
        fn = getattr(vo, "claimChildren", None)
        if callable(fn):
            with contextlib.suppress(Exception):
                return [c for c in (fn() or []) if c is not None]
        proxy = getattr(vo, "Proxy", None)
        fn = getattr(proxy, "claimChildren", None)
        if callable(fn):
            with contextlib.suppress(Exception):
                return [c for c in (fn() or []) if c is not None]

    group = getattr(obj, "Group", None)
    if group:
        return [c for c in group if c is not None]
    return []


def _is_object(value: object) -> bool:
    return hasattr(value, "Name") and hasattr(value, "isDerivedFrom")


def _subnames(value: object) -> list[str]:
    """The sub-element half of a LinkSub value."""
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, (list, tuple)):
        return [item for item in value if isinstance(item, str) and item]
    return []


def link_entries(value: Any) -> list[tuple[DocObject, list[str]]]:
    """Flatten any App::PropertyLink* value into (object, [sub-elements])."""
    if value is None:
        return []
    if _is_object(value):
        return [(value, [])]
    if isinstance(value, (list, tuple)):
        # A LinkSub is (obj, subs); a 2-item LinkList is (obj, obj).
        if (len(value) == 2 and _is_object(value[0]) and
                not _is_object(value[1])):
            return [(value[0], _subnames(value[1]))]
        out: list[tuple[DocObject, list[str]]] = []
        for item in value:
            out.extend(link_entries(item))
        return out
    return []


def feature_stack(body: DocObject) -> list[DocObject]:
    """The Body's solid features in history order.

    The BaseFeature chain through the Tip, not `Group`: the tip can only
    move along that chain. Without a tip, the longest chain wins.
    """
    group = getattr(body, "Group", None) or []
    features: list[DocObject] = []
    for obj in group:
        if not _derived(obj, FEATURE_BASES):
            continue
        try:
            if "BaseFeature" not in (obj.PropertiesList or []):
                continue
        except Exception:  # nosec B112  # an object FreeCAD can't describe
            continue
        features.append(obj)

    if len(features) < 2:
        return features

    known = {f.Name: f for f in features}

    def predecessor(feature: DocObject) -> DocObject | None:
        base = getattr(feature, "BaseFeature", None)
        if base is not None and base.Name in known:
            return known[base.Name]
        return None

    successor: dict[str, DocObject] = {}
    for feature in features:
        base = predecessor(feature)
        if base is not None:
            successor.setdefault(base.Name, feature)

    def walk_forward(feature: DocObject | None,
                     seen: set[str]) -> list[DocObject]:
        chain: list[DocObject] = []
        cursor = feature
        while cursor is not None and cursor.Name not in seen:
            seen.add(cursor.Name)
            chain.append(cursor)
            cursor = successor.get(cursor.Name)
        return chain

    tip = getattr(body, "Tip", None)
    anchor = known.get(tip.Name) if tip is not None else None

    if anchor is None:
        longest: list[DocObject] = []
        for feature in features:
            if predecessor(feature) is not None:
                continue
            candidate = walk_forward(feature, set())
            if len(candidate) > len(longest):
                longest = candidate
        return longest or features

    before: list[DocObject] = []
    seen: set[str] = set()
    cursor = anchor
    while cursor is not None and cursor.Name not in seen:
        seen.add(cursor.Name)
        before.append(cursor)
        cursor = predecessor(cursor)
    before.reverse()

    after = walk_forward(successor.get(anchor.Name), seen)
    return before + after


def _link_table(holder: DocObject) -> LinkTable:
    """Non-containment links of `holder`, keyed by target name."""
    table: LinkTable = {}
    try:
        properties = holder.PropertiesList
    except Exception:
        return table
    for prop in properties:
        if prop in CONTAINMENT_PROPS:
            continue
        try:
            if not holder.getTypeIdOfProperty(prop).startswith(
                    "App::PropertyLink"):
                continue
            value = getattr(holder, prop, None)
        except Exception:  # nosec B112  # an object FreeCAD can't describe
            continue
        for obj, subs in link_entries(value):
            entry = table.setdefault(obj.Name, [])
            entry.append((prop, list(subs)))
    return table


class _LinkCache(object):
    """`_link_table` results, kept per holder for one snapshot build."""

    __slots__ = ("_tables",)

    def __init__(self) -> None:
        self._tables: dict[str, LinkTable] = {}

    def of(self, name: str, holder: DocObject) -> LinkTable:
        table = self._tables.get(name)
        if table is None:
            table = self._tables[name] = _link_table(holder)
        return table


def linking_properties(holder: DocObject, target: DocObject) -> list[str]:
    """Names of properties on `holder` whose link value contains `target`."""
    return [prop for prop, _subs
            in _link_table(holder).get(target.Name, ())]


# -- snapshot --

#: Most rows a saved expansion may open before the tree opens collapsed.
OPENING_ROWS = 300


@dataclass(slots=True, eq=False)
class Node:
    """One document object, resolved for display; compared by identity."""

    name: str
    label: str = ""                 # defaults to the name
    type_id: str = ""
    children: list[str] = field(default_factory=list)
    parent: str | None = None
    visible: bool = True
    touched: bool = False
    in_error: bool = False
    is_profile: bool = False
    is_lifted: bool = False         # drawn in the timeline, not under a user
    is_container: bool = False
    nests_operands: bool = False    # a Part op: operands stay under it
    pinned: set[str] = field(default_factory=set)   # always-chipped refs
    is_model: bool = False          # heads a Part model's step list
    model: str | None = None        # the model header this step belongs to
    inputs: tuple[str, ...] = ()    # the model steps this one reads
    #: Models: every input in build order, filed sketches and datums too.
    sources: list[str] = field(default_factory=list)
    is_datum: bool = False
    #: An Origin or local coordinate system: holds a point, axes, planes.
    is_coordinate_system: bool = False
    is_joint: bool = False          # an Assembly joint, grounding too
    filed: bool = False             # lives in a Sketches/Datum compartment
    is_virtual: bool = False        # a panel-only group, not an object
    is_binder: bool = False
    #: What this reads: (name, label, severity, sub-elements).
    refs: list[tuple[str, str, int, str]] = field(default_factory=list)
    #: What reads this: (name, label, [properties]).
    consumers: list[tuple[str, str, list[str]]] = field(
        default_factory=list)
    container: str | None = None
    container_label: str = ""
    is_feature: bool = False        # member of a Body's solid feature stack
    after_tip: bool = False         # sits past the tip, so currently inert
    suppressed: bool = False        # Suppressed set: left out of the stack
    body: str | None = None         # owning Body, for stack members
    stack: list[str] = field(default_factory=list)  # Bodies: features
    tip: str | None = None          # Bodies: current tip feature name
    severity: int = health.NONE
    notes: list[str] = field(default_factory=list)  # the severity, in words
    dof: int | None = None          # remaining degrees of freedom, if known
    constrained: bool | None = None  # fully constrained? None when unknown
    timeline: int = -1              # position among siblings, by creation

    def __post_init__(self) -> None:
        self.label = self.label or self.name


@dataclass(eq=False)
class Snapshot:
    """View of one document at one moment; rebuilt, not mutated."""

    doc: InitVar[DocObject] = None
    widen: bool = False
    part_layout: str = EXPRESSION
    doc_name: str = ""
    nodes: dict[str, Node] = field(default_factory=dict)  # name -> Node
    roots: list[str] = field(default_factory=list)      # document order
    profiles: list[str] = field(default_factory=list)   # document order
    lifted: list[str] = field(default_factory=list)     # lifted from users
    #: (child, [parents]) for objects claimed twice.
    orphan_claims: list[tuple[str, list[str]]] = field(default_factory=list)
    #: Whether this FreeCAD build exposes solver findings at all.
    solver_findings: bool = False
    _group_owner: dict[str | None, str] = field(default_factory=dict,
                                                repr=False)

    def __post_init__(self, doc: DocObject) -> None:
        if doc is not None:
            self._build(doc)

    # -- construction --

    def _build(self, doc: DocObject) -> None:
        self.doc_name = doc.Name
        objects = list(doc.Objects)
        # Attribute reads cross into C++; read once and pass down.
        names = [obj.Name for obj in objects]
        by_name = dict(zip(names, objects))
        links = _LinkCache()

        bodies = self._create_nodes(names, objects)
        claims, claimed_by = self._read_claims(names, objects)
        self._lift_consumed(claims, by_name, links)
        self._rehome_lifted(objects)
        self._rehome_under_lifted()
        if self.part_layout == EXPRESSION:
            self._group_models(names, by_name, links)
        self._break_parent_cycles()
        self._order_all_children(names, by_name, claimed_by)
        self._order_models()
        self._collect_indexes(names, by_name)
        self._file_compartments(names)

        self._resolve_references(names, by_name, links)
        self._resolve_bodies(by_name, bodies)
        self._drop_self_children()

    def _create_nodes(self, names: list[str],
                      objects: list[DocObject]) -> list[str]:
        """One node per object. Returns the Bodies, typed here anyway."""
        bodies: list[str] = []
        for name, obj in zip(names, objects):
            node = Node(name)
            node.label = getattr(obj, "Label", name)
            node.type_id = getattr(obj, "TypeId", "")
            node.is_profile = is_profile(obj, self.widen)
            node.is_lifted = node.is_profile
            node.is_container = is_container(obj)
            node.nests_operands = nests_operands(obj)
            node.is_binder = _derived(obj, BINDER_BASES)
            node.is_coordinate_system = _derived(
                obj, COORDINATE_SYSTEM_BASES)
            node.is_joint = is_joint(obj)
            node.is_datum = (_derived(obj, DATUM_BASES)
                             and not _derived(obj, ORIGIN_BASES)
                             and not _in_coordinate_system(obj))
            if _derived(obj, BODY_BASES):
                bodies.append(name)

            view = getattr(obj, "ViewObject", None)
            if view is not None:
                node.visible = bool(getattr(view, "Visibility", True))

            state = getattr(obj, "State", None) or ()   # a fresh list per read
            node.touched = "Touched" in state
            node.in_error = "Invalid" in state or "Error" in state
            node.suppressed = bool(getattr(obj, "Suppressed", False))

            if node.is_profile:
                node.severity, node.notes = health.inspect(obj, node.in_error)
                node.dof = health.degrees_of_freedom(obj)
                node.constrained = health.fully_constrained(obj)
            elif node.in_error:
                node.severity = health.ERROR
                node.notes = [health.failed_to_recompute()]

            self.nodes[name] = node
        return bodies

    def _read_claims(self, names: list[str], objects: list[DocObject]
                     ) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
        """Who claims whom. First claimer wins; the rest are conflicts."""
        claims: dict[str, list[str]] = {}
        claimed_by: dict[str, list[str]] = {}
        for name, obj in zip(names, objects):
            children = [child.Name for child in claim_children(obj)
                        if child.Name in self.nodes]
            claimed_by[name] = children
            for child_name in children:
                claims.setdefault(child_name, []).append(name)

        for child_name, parents in claims.items():
            self.nodes[child_name].parent = parents[0]
            if len(parents) > 1:
                self.orphan_claims.append((child_name, parents))
        return claims, claimed_by

    def _lift_consumed(self, claims: dict[str, list[str]],
                       by_name: dict[str, DocObject],
                       links: _LinkCache) -> None:
        """Lift what a modelling step claims *and* links to (not folders)."""
        classic = self.part_layout == NESTED
        for child_name, parents in claims.items():
            node = self.nodes[child_name]
            claimer = by_name.get(parents[0])
            if claimer is None or is_container(claimer):
                continue        # holding something is not using it
            child = by_name.get(child_name)
            if child is not None and is_container(child):
                continue
            if not self.nodes[parents[0]].type_id.startswith(
                    LIFTING_PREFIXES):
                continue        # not a modelling step: FreeCAD's tree
            if classic and self.nodes[parents[0]].type_id.startswith(
                    "PartDesign::"):
                node.is_lifted = False
                continue
            if node.is_lifted:
                continue
            if (self.nodes[parents[0]].nests_operands and
                    self.part_layout == NESTED):
                continue        # a Part operation owns what it combines
            if links.of(parents[0], claimer).get(child_name):
                node.is_lifted = True

    def _rehome_lifted(self, objects: list[DocObject]) -> None:
        """Move each lifted object into the container it belongs to."""
        group_owner: dict[str | None, str]
        self._group_owner = group_owner = {}
        for obj in objects:
            if not is_container(obj):
                continue
            try:
                members = getattr(obj, "Group", None) or ()
            except Exception:  # nosec B112  # an object FreeCAD can't describe
                continue
            for member in members:
                group_owner.setdefault(getattr(member, "Name", None), obj.Name)

        for name, node in self.nodes.items():
            if node.is_lifted:
                node.parent = (group_owner.get(name) or
                               self._nearest_container(node))

    def _rehome_under_lifted(self) -> None:
        """Move what a lifted row claimed up to an unlifted ancestor."""
        for node in self.nodes.values():
            if node.is_lifted or not node.parent:
                continue
            seen = set()
            cursor: str | None = node.parent
            while cursor and cursor not in seen:
                seen.add(cursor)
                parent = self.nodes.get(cursor)
                if parent is None:
                    cursor = None
                    break
                if not parent.is_lifted:
                    break
                cursor = parent.parent
            node.parent = cursor or None

    def _free(self, name: str) -> bool:
        """Outside every Body, and not itself a container."""
        seen = set()
        cursor: str | None = name
        while cursor and cursor not in seen:
            seen.add(cursor)
            node = self.nodes.get(cursor)
            if node is None:
                return False
            if cursor != name and node.is_container:
                return not node.type_id.startswith("PartDesign::")
            pd_only = (node.type_id.startswith("PartDesign::")
                       and not node.is_binder)
            if node.is_container or pd_only:
                return False
            cursor = node.parent
        return True

    def _group_models(self, names: list[str],
                      by_name: dict[str, DocObject],
                      links: _LinkCache) -> None:
        """Gather each Part model's steps under its latest operation.

        A model is a Part operation nothing else reads, plus its inputs.
        A shared step stays with the model created first.
        """
        free = {name for name in names if self._free(name)}
        inputs: dict[str, tuple[str, ...]] = {}
        read: set[str] = set()
        for name in free:
            node = self.nodes[name]
            node.inputs = tuple(
                target for target in links.of(name, by_name[name])
                if target in free and target != name)
            inputs[name] = node.inputs
            read.update(node.inputs)

        for name in names:
            node = self.nodes[name]
            if (name not in free or name in read or not node.nests_operands or
                    not node.inputs):
                continue
            node.is_model = True
            pending = list(node.inputs)
            while pending:
                step_name = pending.pop()
                step = self.nodes[step_name]
                if step.model is not None or step.is_model:
                    continue
                step.model = name
                pending.extend(step.inputs)
                if not self._fileable(step_name):
                    step.parent = name
                    step.is_lifted = False

    def _order_models(self) -> None:
        """Steps oldest first, every input ahead of what reads it.

        Topological, with creation order breaking ties: a property can be
        repointed at something newer.
        """
        for node in self.nodes.values():
            if not node.is_model:
                continue
            members = [n for n, other in self.nodes.items()
                       if other.model == node.name]
            rank = {name: index for index, name in enumerate(self.nodes)}
            placed: set[str] = set()
            order: list[str] = []

            def place(name: str, trail: set[str]) -> None:
                if name in placed or name in trail:
                    return
                trail.add(name)
                for dep in sorted(self.nodes[name].inputs,
                                  key=lambda n: rank.get(n, 0)):
                    if dep in rank:
                        place(dep, trail)
                placed.add(name)
                order.append(name)

            for name in sorted(members,
                               key=rank.__getitem__):
                place(name, set())
            rows = [n for n in order if n in node.children]
            node.children = rows + [c for c in node.children
                                    if c not in placed]
            node.sources = order
            node.stack = rows
            node.tip = node.name        # the finished model
            for index, name in enumerate(node.children):
                self.nodes[name].timeline = index
                self.nodes[name].body = node.name

    def model_state(self, model_name: str, tip_name: str | None
                    ) -> dict[str, tuple[bool, bool]]:
        """(built, shown) per step with the model rolled back to `tip_name`.

        Part operations never alter their inputs, so rolling back only
        shows whatever in the prefix is not yet consumed.
        """
        model = self.nodes[model_name]
        steps = list(model.sources) + [model_name]
        end = (steps.index(tip_name) + 1 if tip_name in steps
               else len(steps))
        built = steps[:end]
        consumed = {dep for name in built for dep in self.nodes[name].inputs}
        return {name: (index < end, index < end and name not in consumed)
                for index, name in enumerate(steps)}

    def _fileable(self, name: str) -> bool:
        """A free sketch or datum at document or App::Part level."""
        node = self.nodes[name]
        if not (node.is_profile or node.is_datum) or not self._free(name):
            return False
        home = self._nearest_container(node)
        return home is None or self.nodes[home].type_id == "App::Part"

    def _file_compartments(self, names: list[str]) -> None:
        """Collect free sketches and datums into panel-only groups.

        One pair per App::Part, plus one at document level for the rest.
        """
        filed: dict[tuple[str | None, str], list[str]] = {}
        for name in names:
            if not self._fileable(name):
                continue
            node = self.nodes[name]
            scope = self._part_of(name)
            kind = next(title for title, flag in COMPARTMENTS
                        if getattr(node, flag))
            filed.setdefault((scope, kind), []).append(name)

        for title, _flag in COMPARTMENTS:
            for (scope, kind), members in filed.items():
                if kind != title:
                    continue
                group = self._virtual_group(title, scope)
                for name in members:
                    old = self.nodes.get(
                        self.nodes[name].parent)  # type: ignore[arg-type]
                    if old is not None and name in old.children:
                        old.children.remove(name)
                    self.nodes[name].parent = group.name
                    self.nodes[name].filed = True
                    if name in self.roots:
                        self.roots.remove(name)
                group.children = sorted(
                    members, key=lambda n: natural_key(self.nodes[n].label))
                for index, name in enumerate(group.children):
                    self.nodes[name].timeline = index
                if scope is None:
                    self.roots.append(group.name)
                else:
                    self.nodes[scope].children.append(group.name)

    def _virtual_group(self, title: str, scope: str | None) -> Node:
        name = VIRTUAL_PREFIX + title.replace(" ", "") + (
            VIRTUAL_PREFIX + scope if scope else "")
        node = Node(name)
        node.label = title
        node.type_id = "App::DocumentObjectGroup"
        node.is_container = node.is_virtual = True
        node.parent = scope
        self.nodes[name] = node
        return node

    def _part_of(self, name: str) -> str | None:
        """The nearest App::Part above `name`, or None."""
        seen = set()
        cursor = self.nodes[name].parent
        while cursor and cursor not in seen:
            seen.add(cursor)
            node = self.nodes.get(cursor)
            if node is None:
                return None
            if node.type_id == "App::Part":
                return cursor
            cursor = node.parent
        return None

    def _order_all_children(self, names: list[str],
                            by_name: dict[str, DocObject],
                            claimed_by: dict[str, list[str]]) -> None:
        doc_order = {name: index for index, name in enumerate(names)}
        by_parent: dict[str, list[str]] = {}
        for name in names:
            parent = self.nodes[name].parent
            if parent is not None:
                by_parent.setdefault(parent, []).append(name)

        for name, mine in by_parent.items():
            self.nodes[name].children = self._order_children(
                by_name[name], mine, doc_order, claimed_by.get(name, ()))

    def _collect_indexes(self, names: list[str],
                         by_name: dict[str, DocObject]) -> None:
        self.roots = [name for name in names
                      if self.nodes[name].parent is None]
        for index, name in enumerate(self.roots):
            self.nodes[name].timeline = index
        self.profiles = [name for name in names
                         if self.nodes[name].is_profile]
        self.lifted = [name for name in names
                       if self.nodes[name].is_lifted]

        for name in self.profiles:
            probe = by_name.get(name)
            if probe is not None:
                self.solver_findings = health.answers(probe)
                break

    def _resolve_references(self, names: list[str],
                            by_name: dict[str, DocObject],
                            links: _LinkCache) -> None:
        """Resolve what each object reads and what reads it."""
        for name in names:
            obj = by_name.get(name)
            if obj is None:
                continue
            node = self.nodes[name]

            for target, entries in links.of(name, obj).items():
                if target == name or target not in self.nodes:
                    continue
                # No chip for an enclosing container.
                if self.is_ancestor(name, target):
                    continue
                other = self.nodes[target]
                props = [prop for prop, _subs in entries]

                # A sketch is read whole; its edge indices are noise.
                subs: list[str] = []
                if not other.is_profile:
                    for _prop, sub_names in entries:
                        for sub_name in sub_names:
                            if sub_name not in subs:
                                subs.append(sub_name)

                # Severity rides on the chip, blaming the broken input.
                node.refs.append((target, other.label, other.severity,
                                  ", ".join(subs)))
                other.consumers.append((name, node.label, props))
                filed_kind = other.is_profile or other.is_datum
                in_model = node.model or node.is_model
                if node.nests_operands and (filed_kind or in_model):
                    node.pinned.add(target)

        for name in self.lifted:
            node = self.nodes[name]
            node.container = self._nearest_container(node)
            if node.container:
                node.container_label = self.nodes[node.container].label

    def _resolve_bodies(self, by_name: dict[str, DocObject],
                        bodies: list[str]) -> None:
        """Record each Body's feature stack and mark what the tip excludes."""
        for name in bodies:
            obj = by_name.get(name)
            if obj is None:
                continue
            body = self.nodes[name]
            stack = feature_stack(obj)
            body.stack = [f.Name for f in stack]

            tip = getattr(obj, "Tip", None)
            body.tip = tip.Name if tip is not None else None

            # The chain, not Group, decides which features follow the tip.
            past = body.tip is None
            for feature in stack:
                node = self.nodes.get(feature.Name)
                if node is None:
                    continue
                node.is_feature = True
                node.body = name
                node.after_tip = past
                if feature.Name == body.tip:
                    past = True

            # Profiles are off the chain: timeline position decides.
            tip_node = self.nodes.get(body.tip) if body.tip else None
            tip_pos = tip_node.timeline if tip_node is not None else None
            for child_name in body.children:
                child = self.nodes.get(child_name)
                if child is None or child.is_feature:
                    continue
                # All children need it, for the panel's continuous line.
                child.body = name
                if child.is_lifted:
                    child.after_tip = (tip_pos is None or
                                       child.timeline > tip_pos)

    def _order_children(self, container: DocObject, child_names: list[str],
                        doc_order: dict[str, int],
                        claim_order: Iterable[str]) -> list[str]:
        """Children in creation order, and each one's position recorded.

        `Group` is creation order; members it omits (a Body's Origin) lead
        in claim order.
        """
        rank: dict[str, int] = {}
        try:
            members = getattr(container, "Group", None) or ()
            rank = {member.Name: index for index, member in enumerate(members)}
        except Exception:
            rank = {}

        claim_rank: dict[str, int] = {}
        for index, name in enumerate(claim_order):
            claim_rank.setdefault(name, index)

        if rank:
            lead = [n for n in child_names if n not in rank]
            timed = [n for n in child_names if n in rank]
            lead.sort(key=lambda n: (claim_rank.get(n, len(claim_rank) + 1),
                                     doc_order.get(n, 0)))
            timed.sort(key=lambda n: rank[n])
            ordered = lead + timed
        else:
            ordered = self._order_without_group(child_names, doc_order,
                                                claim_rank)

        for index, name in enumerate(ordered):
            self.nodes[name].timeline = index
        return ordered

    @staticmethod
    def _order_without_group(child_names: list[str],
                             doc_order: dict[str, int],
                             claim_rank: dict[str, int]) -> list[str]:
        """Creation order with claim order as the backbone.

        An unclaimed child slots in just ahead of the first claimed sibling
        created after it.
        """
        by_age = sorted(child_names, key=lambda n: doc_order.get(n, 0))
        next_claimed: dict[str, int | None] = {}
        running: int | None = None
        for name in reversed(by_age):
            next_claimed[name] = running
            if name in claim_rank:
                rank = claim_rank[name]
                running = rank if running is None else min(running, rank)

        def key(name: str) -> tuple[int, int]:
            if name in claim_rank:
                return (claim_rank[name], 0)
            after = next_claimed.get(name)
            if after is not None:
                return (after - 1, 1)
            return (len(claim_rank), 1)

        return sorted(child_names, key=key)

    def retip(self, body_name: str,
              tip_name: str | None) -> Sequence[str]:
        """Move a Body's tip in this snapshot only; return changed names.

        Must mirror `_resolve_bodies` exactly.
        """
        body = self.nodes.get(body_name)
        if body is None:
            return ()

        body.tip = tip_name
        touched = [body_name]

        if body.is_model:
            for name, (built, shown) in self.model_state(
                    body_name, tip_name).items():
                node = self.nodes[name]
                node.after_tip = not built
                node.visible = shown
                touched.append(name)
            return touched

        past = tip_name is None
        for name in body.stack:
            node = self.nodes.get(name)  # type: ignore[assignment]
            if node is None:
                continue
            node.after_tip = past
            node.visible = (name == tip_name)
            touched.append(name)
            if name == tip_name:
                past = True

        tip_node = self.nodes.get(tip_name) if tip_name else None
        tip_pos = tip_node.timeline if tip_node is not None else None
        for child_name in body.children:
            child = self.nodes.get(child_name)
            if child is None or child.is_feature or not child.is_lifted:
                continue
            child.after_tip = (tip_pos is None or child.timeline > tip_pos)
            touched.append(child_name)
        return touched

    def is_ancestor(self, name: str, candidate: str) -> bool:
        """Is `candidate` somewhere above `name`?"""
        seen = set()
        node = self.nodes.get(name)
        cursor = node.parent if node is not None else None
        while cursor and cursor not in seen:
            if cursor == candidate:
                return True
            seen.add(cursor)
            node = self.nodes.get(cursor)
            cursor = node.parent if node is not None else None
        return False

    def _nearest_container(self, node: Node) -> str | None:
        seen = set()
        cur = node.parent
        while cur and cur not in seen:
            seen.add(cur)
            candidate = self.nodes.get(cur)
            if candidate is None:
                return None
            if candidate.is_container and not candidate.is_virtual:
                return cur
            cur = candidate.parent
        return None

    def _break_parent_cycles(self) -> None:
        for name, node in self.nodes.items():
            if node.parent == name:
                node.parent = None
        for name in self.nodes:
            cursor = name
            walked = set()
            while cursor:
                if cursor in walked:
                    self.nodes[cursor].parent = None
                    break
                walked.add(cursor)
                nxt = self.nodes[cursor].parent
                if nxt is None or nxt not in self.nodes:
                    break
                cursor = nxt

    def _drop_self_children(self) -> None:
        """Keep a node listed as its own child from hanging the flattener."""
        for node in self.nodes.values():
            node.children = [c for c in node.children if c != node.name]

    # -- queries --

    def flatten(self, expanded: Container[str]) -> list[tuple[str, int]]:
        """Visible (name, depth) rows, depth-first, given an expansion set."""
        rows: list[tuple[str, int]] = []
        stack = [(name, 0) for name in reversed(self.roots)]
        guard = set()
        while stack:
            name, depth = stack.pop()
            if name in guard:
                continue
            guard.add(name)
            rows.append((name, depth))
            node = self.nodes.get(name)
            if node is None or not node.children:
                continue
            if name not in expanded:
                continue
            for child in reversed(node.children):
                stack.append((child, depth + 1))
        return rows

    def path_of(self, name: str, limit: int = 2) -> list[str]:
        """Ancestor labels, nearest last."""
        labels: list[str] = []
        guard = set()
        node = self.nodes.get(name)
        cursor = node.parent if node else None
        while cursor and cursor not in guard and cursor in self.nodes:
            guard.add(cursor)
            labels.append(self.nodes[cursor].label)
            cursor = self.nodes[cursor].parent
        labels.reverse()
        return labels[-limit:] if limit else labels

    def search(self, text: str | None, limit: int = 25) -> list[Node]:
        """Ranked flat matches for the search box; not a filter.

        Label prefix, then label substring, then internal name.
        """
        text = (text or "").strip().lower()
        if not text:
            return []

        hits: list[tuple[int, int, str, str]] = []
        for name, node in self.nodes.items():
            label = node.label.lower()
            position = label.find(text)
            if position >= 0:
                rank = 0 if position == 0 else 1
            else:
                position = name.lower().find(text)
                if position < 0:
                    continue
                rank = 2
            hits.append((rank, position, label, name))

        hits.sort()
        return [self.nodes[name] for _r, _p, _l, name in hits[:limit]]

    def unconstrained_profiles(self) -> list[str]:
        """Profiles with degrees of freedom left. State, not a finding."""
        names: list[str] = []
        for name in self.profiles:
            node = self.nodes[name]
            if node.constrained is True:
                continue
            if (node.dof or 0) > 0 or node.constrained is False:
                names.append(name)
        return names

    def problem_profiles(self) -> list[str]:
        """Profiles carrying a finding, for stepping between them."""
        return [name for name in self.profiles
                if self.nodes[name].severity > health.NONE]

    def default_expansion(self) -> set[str]:
        """Containers open, features closed: how people actually work."""
        return {n for n, node in self.nodes.items() if node.is_container}

    def opening_expansion(self, saved: set[str] | None = None,
                          cap: int = OPENING_ROWS) -> set[str]:
        """What is open when a document is first shown.

        `saved` plus the panel's own folders, if that gives at most `cap`
        rows; otherwise everything closed.
        """
        if not saved:
            return set()
        chosen = ({n for n in saved if n in self.nodes}
                  | {n for n, node in self.nodes.items()
                     if node.is_virtual and node.is_container
                     and node.parent is not None})
        if len(self.flatten(chosen)) > cap:
            return set()
        return chosen


def capture(doc: DocObject = None, widen: bool = False,
            part_layout: str = EXPRESSION) -> Snapshot:
    """Snapshot the active document, or an empty snapshot if there is none."""
    if doc is None:
        doc = App.ActiveDocument
    if doc is None:
        return Snapshot(None, widen=widen)
    try:
        return Snapshot(doc, widen=widen, part_layout=part_layout)
    except Exception:
        App.Console.PrintError("Nxt: snapshot failed\n")
        App.Console.PrintError(traceback.format_exc())
        return Snapshot(None, widen=widen)
