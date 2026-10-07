"""Pure-Python snapshot of a FreeCAD document, for the timeline panel.

No Qt imports, so it runs headlessly under `freecadcmd` and in the
tests. See DESIGN.md for what the timeline is and why.
"""

from __future__ import annotations

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

# --------------------------------------------------------------------------- #
# what counts as a profile
# --------------------------------------------------------------------------- #

#: Always lifted out of its consumer and placed in the timeline.
PROFILE_BASES = ("Sketcher::SketchObject",)

#: Lifted only when `widen` is on. Catches Draft wires/circles/b-splines,
#: which are Part::Part2DObject subclasses and are reused the same way.
PROFILE_BASES_WIDE = ("Part::Part2DObject",)

#: The solid feature stack inside a PartDesign Body. Membership also
#: requires a BaseFeature property, which is what separates real stack
#: entries from datums and shape binders that merely live in the Body.
FEATURE_BASES = ("PartDesign::Feature",)

BODY_BASES = ("PartDesign::Body",)

#: Part workbench operations own their operands outright: a Cut's Base and
#: Tool exist to be cut, so they stay nested under it (exclusive nesting)
#: rather than being lifted into the timeline. Profiles are still lifted,
#: and the operation carries a chip naming the profile it reads.
NESTING_PREFIX = "Part::"

#: How the tree is structured. NESTED is the classic tree: each Part
#: operation keeps its operands under it, and a Part Design feature keeps
#: what it claims - its sketch, most often - under it, as FreeCAD's own
#: tree does. EXPRESSION puts sketches in the Body's timeline beside the
#: features, and lists a Part model's steps flat, oldest first,
#: under its latest operation, with chips carrying the references and a
#: history bar to scrub through them.
NESTED, EXPRESSION = "nested", "expression"

#: Free-standing datums (outside any Body) are filed like sketches. The
#: Origin and its planes and axes derive from the same bases and stay put.
DATUM_BASES = ("Part::Datum", "App::DatumElement",
               "App::LocalCoordinateSystem")
ORIGIN_BASES = ("App::Origin", "App::OriginFeature")

#: Binders are PartDesign types, but outside a Body they are ordinary Part
#: inputs and nest as steps of the model that first reads them.
BINDER_BASES = ("PartDesign::ShapeBinder", "PartDesign::SubShapeBinder")

#: Panel-only groups. The document is never restructured: moving a sketch
#: out of an App::Part would change where it sits in space. The prefix
#: cannot occur in a FreeCAD object name, so these never collide.
VIRTUAL_PREFIX = "~"
COMPARTMENTS: tuple[tuple[str, str], ...] = (
    ("Sketches", "is_profile"), ("Datum Objects", "is_datum"))


def is_virtual(name: str) -> bool:
    return name.startswith(VIRTUAL_PREFIX)


def natural_key(text: str) -> list[int | str]:
    """Sketch2 before Sketch10."""
    return [int(part) if part.isdigit() else part.lower()
            for part in re.split(r"(\d+)", text)]


#: Container types we resolve a profile's "home" against.
CONTAINER_BASES = (
    "PartDesign::Body",
    "App::Part",
    "App::DocumentObjectGroup",
)

#: Link properties that express containment rather than consumption. A Body
#: links its sketches through Group; that is not a "use".
CONTAINMENT_PROPS = frozenset({
    "Group", "Origin", "OriginFeatures", "_GroupTouched", "Tip", "BaseFeature",
})


def _derived(obj: DocObject, bases: Iterable[str]) -> bool:
    for base in bases:
        try:
            if obj.isDerivedFrom(base):
                return True
        except Exception:
            pass
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


# --------------------------------------------------------------------------- #
# hierarchy discovery
# --------------------------------------------------------------------------- #

def claim_children(obj: DocObject) -> list[DocObject]:
    """Best-effort equivalent of the C++ tree's child query.

    FreeCAD builds the tree from ViewProvider::claimChildren(). Depending on
    build and object flavour that is reachable in three different places, so
    try them in order of fidelity and fall back to App-level containment.
    Returns a list of DocumentObjects, never None.
    """
    vo = getattr(obj, "ViewObject", None)

    if vo is not None:
        fn = getattr(vo, "claimChildren", None)
        if callable(fn):
            try:
                return [c for c in (fn() or []) if c is not None]
            except Exception:
                pass
        proxy = getattr(vo, "Proxy", None)
        fn = getattr(proxy, "claimChildren", None)
        if callable(fn):
            try:
                return [c for c in (fn() or []) if c is not None]
            except Exception:
                pass

    # App-level fallback: group containment only. Loses PartDesign's
    # feature->sketch nesting, which for our purposes is no loss at all.
    group = getattr(obj, "Group", None)
    if group:
        return [c for c in group if c is not None]
    return []


def _is_object(value: object) -> bool:
    return hasattr(value, "Name") and hasattr(value, "isDerivedFrom")


def _subnames(value: object) -> list[str]:
    """The sub-element half of a LinkSub value, as a list of strings."""
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, (list, tuple)):
        return [item for item in value if isinstance(item, str) and item]
    return []


def link_entries(value: Any) -> list[tuple[DocObject, list[str]]]:
    """Flatten any App::PropertyLink* value into (object, [sub-elements]).

    The five shapes FreeCAD uses:

        Link            obj
        LinkList        [obj, obj]
        LinkSub         (obj, "Face3")  or  (obj, ["Face3", "Face5"])
        LinkSubList     [(obj, [...]), (obj, [...])]
        empty           None

    The sub-elements used to be dropped on the floor - a pair flattened to
    its object and the strings were discarded as not-an-object. That lost
    the difference between "this pocket is built on that pad" and "this
    pocket is built on one face of that pad", which is most of what the
    reference was saying.
    """
    if value is None:
        return []
    if _is_object(value):
        return [(value, [])]
    if isinstance(value, (list, tuple)):
        # A LinkSub arrives as a 2-tuple whose head is the object and whose
        # tail is the sub-element name(s). A LinkList is a plain sequence of
        # objects, so the shape has to be checked rather than the length.
        if (len(value) == 2 and _is_object(value[0]) and
                not _is_object(value[1])):
            return [(value[0], _subnames(value[1]))]
        out: list[tuple[DocObject, list[str]]] = []
        for item in value:
            out.extend(link_entries(item))
        return out
    return []


def _link_targets(value: Any) -> list[DocObject]:
    """Just the objects, for callers that do not care which part."""
    return [obj for obj, _subs in link_entries(value)]


def feature_stack(body: DocObject) -> list[DocObject]:
    """The Body's solid features in history order.

    Defined as *the chain through the Tip*, not as the contents of `Group`.
    Every PartDesign feature points at its predecessor through BaseFeature,
    so walking back from the tip and forward from it recovers the linear
    history exactly. Anything in the Body that is not on that chain - a
    MultiTransform's sub-transformations, a stray left by a failed edit - is
    excluded rather than guessed at, because the tip can only ever be moved
    along the chain and offering any other row as a target is a lie.

    With no tip to anchor on (a Body mid-creation), the longest chain wins.
    """
    group = getattr(body, "Group", None) or []
    features: list[DocObject] = []
    for obj in group:
        if not _derived(obj, FEATURE_BASES):
            continue
        try:
            if "BaseFeature" not in (obj.PropertiesList or []):
                continue
        except Exception:
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
    """Everything `holder` points at, as {target name: [property names]}.

    One pass over the property table instead of one pass per target. Typing
    a property is a call into C++ and objects have dozens of them, so the
    difference between asking once per holder and once per (holder, target)
    pair is the difference between a few hundred calls per rebuild and tens
    of thousands.

    Containment links are dropped here rather than by the caller: a Body
    lists its sketches through `Group`, and that is not a use.
    """
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
        except Exception:
            continue
        for obj, subs in link_entries(value):
            entry = table.setdefault(obj.Name, [])
            entry.append((prop, list(subs)))
    return table


class _LinkCache(object):
    """`_link_table` results, kept per holder for one snapshot build.

    The expensive part of working out what points at what is typing every
    property a holder has - one call into C++ each. Asked per (holder,
    target) pair, one container answers it once per member it holds: a Body
    in the InList of thirty sketches retyped its whole property table thirty
    times, and every answer was then discarded because Group is containment
    rather than use.
    """

    __slots__ = ("_tables",)

    def __init__(self) -> None:
        self._tables: dict[str, LinkTable] = {}

    def of(self, name: str, holder: DocObject) -> LinkTable:
        table = self._tables.get(name)
        if table is None:
            table = self._tables[name] = _link_table(holder)
        return table


def linking_properties(holder: DocObject, target: DocObject) -> list[str]:
    """Names of properties on `holder` whose link value contains `target`.

    Kept for `probe.py` and the tests, which ask about one pair at a time.
    The snapshot walk uses `_link_table` instead, because it asks about
    every pair.
    """
    return [prop for prop, _subs
            in _link_table(holder).get(target.Name, ())]


# --------------------------------------------------------------------------- #
# snapshot
# --------------------------------------------------------------------------- #

@dataclass(slots=True, eq=False)
class Node:
    """One document object, resolved for display.

    Identity, not value, is what matters: nodes are looked up by name and
    compared by `is`, so dataclass equality is switched off.
    """

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
    """Immutable-ish view of one document at one moment.

    Rebuild rather than mutate: building is cheap (one pass over objects plus
    one link scan per profile) and correctness beats incrementalism here.
    Built from `doc` when one is given; `Snapshot()` is the empty snapshot.
    """

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
    #: Does this build expose solver findings at all? One fact about the
    #: installation, recorded once rather than repeated on every card.
    #: False means the gutter marks reflect document State only.
    solver_findings: bool = False
    _group_owner: dict[str | None, str] = field(default_factory=dict,
                                                repr=False)

    def __post_init__(self, doc: DocObject) -> None:
        if doc is not None:
            self._build(doc)

    # -- construction ------------------------------------------------------ #

    def _build(self, doc: DocObject) -> None:
        self.doc_name = doc.Name
        objects = list(doc.Objects)
        # Every attribute read here crosses into C++, and this walk runs on
        # every document signal. Read each one once and pass it down.
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
            # A profile is lifted whether or not anything uses it yet;
            # everything else earns it by being referenced.
            node.is_lifted = node.is_profile
            node.is_container = is_container(obj)
            node.nests_operands = nests_operands(obj)
            node.is_binder = _derived(obj, BINDER_BASES)
            node.is_datum = (_derived(obj, DATUM_BASES) and
                             not _derived(obj, ORIGIN_BASES))
            if _derived(obj, BODY_BASES):
                bodies.append(name)

            view = getattr(obj, "ViewObject", None)
            if view is not None:
                node.visible = bool(getattr(view, "Visibility", True))

            state = getattr(obj, "State", None) or ()   # a fresh list per read
            node.touched = "Touched" in state
            node.in_error = "Invalid" in state or "Error" in state

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
        """Who claims whom. First claimer wins; the rest are conflicts.

        The result is kept because claimChildren() allocates a fresh list of
        wrappers through the view provider - the most expensive call in this
        walk, and one that ordering children would otherwise repeat.
        """
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
        """Anything a non-container claims *and* links to is a reference."""
        classic = self.part_layout == NESTED
        for child_name, parents in claims.items():
            node = self.nodes[child_name]
            claimer = by_name.get(parents[0])
            if claimer is None or is_container(claimer):
                continue        # holding something is not using it
            if classic and self.nodes[parents[0]].type_id.startswith(
                    "PartDesign::"):
                # The classic tree: what a Part Design feature claims
                # stays under it.
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
            except Exception:
                continue
            for member in members:
                group_owner.setdefault(getattr(member, "Name", None), obj.Name)

        for name, node in self.nodes.items():
            if node.is_lifted:
                node.parent = (group_owner.get(name) or
                               self._nearest_container(node))

    def _rehome_under_lifted(self) -> None:
        """Move what a lifted row claimed up to an unlifted ancestor.

        A lifted row is a leaf, so what it claimed moves up to its
        nearest unlifted ancestor rather than disappearing with it.
        """
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

        A model is a Part operation nothing else reads, plus everything it
        was built from. The steps are listed flat beneath it rather than
        nested, because the chips on each step already say what it reads.
        A step two models share stays with the model created first.
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

        Creation order is the backbone, but a property can be repointed at
        something newer, so the order is a topological sort with creation
        order breaking ties. Scrubbing then never shows an operation whose
        input has not been made yet.
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
        """Which steps are built and shown with the model rolled back.

        Which steps are built and which show, with the model rolled back
        to `tip_name` (None for the finished model).

        Part operations never alter their inputs, so every intermediate
        result already exists. Rolling back is only a matter of showing
        what was newest at that step: whatever in the prefix nothing else
        in the prefix has consumed yet.
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
        """A free sketch or datum whose home is the document or an App::Part.

        One the user put in a group of their own stays where they put
        it.
        """
        node = self.nodes[name]
        if not (node.is_profile or node.is_datum) or not self._free(name):
            return False
        home = self._nearest_container(node)
        return home is None or self.nodes[home].type_id == "App::Part"

    def _file_compartments(self, names: list[str]) -> None:
        """Collect free sketches and datums into panel-only groups.

        One pair per App::Part, at the bottom of it, and one pair at the
        bottom of the document for everything outside any App::Part - a
        sketch shown away from the part it belongs to would be misleading.
        Sorted by label, number-aware. Empty groups are not created.
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
        """Resolve what each object reads and what reads it.

        Fill in what each object reads, what reads it, and where a
        lifted object belongs.

        Read forwards, from each object's own link table, rather than
        backwards from a target's `InList`. Backwards only ever answered
        the question for things the timeline had lifted, so a feature built
        on a *face of an earlier feature* had nothing to show: the face's
        owner is a solid in the Body, claimed by a container, and so never
        lifted. Forwards, every reference is found the same way and the
        consumer list falls out as the inverse for free.
        """
        for name in names:
            obj = by_name.get(name)
            if obj is None:
                continue
            node = self.nodes[name]

            for target, entries in links.of(name, obj).items():
                if target == name or target not in self.nodes:
                    continue
                # A feature attached to a face of the Body it lives in is
                # not telling you anything: you can see which Body it is
                # in, because the row is inside it. Chipping the container
                # you are already standing in put a reference on almost
                # every row and said nothing on any of them.
                if self.is_ancestor(name, target):
                    continue
                other = self.nodes[target]
                props = [prop for prop, _subs in entries]

                # Which part of it - except for a sketch, where the answer
                # is noise. A feature reads a sketch, whole; the edge index
                # that the attachment happens to name is an internal detail
                # of how it is attached, not a thing the user chose.
                subs: list[str] = []
                if not other.is_profile:
                    for _prop, sub_names in entries:
                        for sub_name in sub_names:
                            if sub_name not in subs:
                                subs.append(sub_name)

                # The severity travels with the reference, so a feature
                # that failed because its sketch is broken says so on the
                # chip that names the sketch rather than by reddening its
                # own label - which would blame it for something it did
                # not do.
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
        """Record each Body's feature stack and mark what the tip excludes.

        `bodies` is collected during the first pass, where every object is
        being typed anyway. Rediscovering them here meant a getObject and an
        isDerivedFrom for every object in the document to find the two or
        three that are Bodies.
        """
        for name in bodies:
            obj = by_name.get(name)
            if obj is None:
                continue
            body = self.nodes[name]
            stack = feature_stack(obj)
            body.stack = [f.Name for f in stack]

            tip = getattr(obj, "Tip", None)
            body.tip = tip.Name if tip is not None else None

            # Everything strictly after the tip is still in the document but
            # contributes nothing to what the Body currently shows. For solid
            # features that is decided by the chain, which is authoritative
            # about order even when Group disagrees with it.
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

            # Profiles are not on the chain, so their side of the bar is
            # decided by where they sit in the timeline. A sketch drawn after
            # the rollback point had not been drawn yet at that moment, and
            # showing it as live would misrepresent the state the bar claims
            # to be showing. Only profiles are judged this way: an Origin is
            # never rolled back, whatever its position.
            tip_node = self.nodes.get(body.tip) if body.tip else None
            tip_pos = tip_node.timeline if tip_node is not None else None
            for child_name in body.children:
                child = self.nodes.get(child_name)
                if child is None or child.is_feature:
                    continue
                # Every child records its Body, not just the ones that can
                # be rolled back: the panel draws a continuous line down a
                # Body's timeline, and a row that does not know it is in a
                # Body leaves a gap in it that reads as a rendering fault.
                child.body = name
                if child.is_lifted:
                    child.after_tip = (tip_pos is None or
                                       child.timeline > tip_pos)

    def _order_children(self, container: DocObject, child_names: list[str],
                        doc_order: dict[str, int],
                        claim_order: Iterable[str]) -> list[str]:
        """Children in creation order, and each one's position recorded.

        `Group` is the record of when things were added to a container, and
        it is the only one that survives a feature being renamed, re-tipped
        or reordered - which is why the timeline reads from it rather than
        from claimChildren(). Members it does not mention (a Body's Origin)
        have no timeline position of their own, so they keep claim order and
        lead; anything in Group follows, in Group order.

        Verified against a real model with `probe.timeline()` rather than
        assumed, after a Body's Group turned out to be exactly this. A build
        where it is not falls back to document order, which is also creation
        order - just coarser, since it cannot tell one container from
        another.
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

        No `Group` to read, so claim order is what the container itself says
        about its children, and throwing that away would reorder trees that
        were fine before. A lifted profile has no place in it, so it slots
        in just ahead of the first sibling created after it - which puts it
        where it was drawn rather than at the end.

        "The first sibling created after me" is resolved for every child in
        one backwards pass. Asking it per child, by rescanning the siblings,
        was quadratic in a container's child count for no gain.
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

    def tip_at_or_before(self, body_name: str,
                         names_newest_first: Iterable[str]) -> str | None:
        """Which feature the timeline bar sets where it was dropped.

        Only a solid feature can be a tip, so a bar dropped just under a
        sketch does not set the sketch - it sets the last feature above it,
        and the bar stays where the user put it. Above the first feature
        there is nothing to set, and `None` says so.

        Takes the rows above the drop, nearest first, rather than a
        position: the panel's rows are what the user is aiming at, and a
        collapsed branch means the rows on screen and the timeline no
        longer agree about what "before" means. The iterable is consumed
        lazily, so this stops at the first feature it meets.
        """
        body = self.nodes.get(body_name)
        if body is None or not body.stack:
            return None
        stack = set(body.stack)
        for name in names_newest_first:
            if name in stack:
                return name
        return None

    def retip(self, body_name: str,
              tip_name: str | None) -> Sequence[str]:
        """Move a Body's tip within this snapshot only.

        Move a Body's tip within this snapshot, without touching the
        document. Returns the names whose displayed state changed.

        The document walk is far too expensive to repeat while the bar is
        being dragged, and it is not needed: moving a tip changes which
        features are built, which are visible, and which sketches had not
        been drawn yet - all of it derivable from what the snapshot already
        holds. This is that derivation, and it mirrors `_resolve_bodies`
        exactly; the two must agree, or the panel would show one thing
        during a drag and another the moment it ended.
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
        """Defensive.

        a node listed as its own child must not hang the flattener.
        Named for what it does - it was called `_break_cycles`, which
        is what the pass above it does, and having both names in the
        same class read as one job done twice.
        """
        for node in self.nodes.values():
            node.children = [c for c in node.children if c != node.name]

    # -- queries ----------------------------------------------------------- #

    def flatten(self, expanded: Container[str]) -> list[tuple[str, int]]:
        """Depth-first walk of the tree half, honouring an expansion set.

        Returns a list of (name, depth) for the rows that should be visible.
        """
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
        """Ancestor labels, nearest last.

        Search results need somewhere to say *which* Pad this is when a
        document has four of them.
        """
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
        """Ranked flat matches for the search box.

        Deliberately not a filter. Hiding rows to show a match costs the
        context that makes the match meaningful, and leaves the user to
        undo the search before they can carry on working. Searching returns
        somewhere to *go* and leaves the tree alone.

        Labels rank ahead of internal names, and a prefix hit ahead of a hit
        in the middle, because typing "pad" should reach Pad before
        HolePadded and before an object merely named Pad001 internally.
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
