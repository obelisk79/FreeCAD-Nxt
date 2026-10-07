"""Headless tests for the partition logic.

scene.py is the only module with real algorithmic content, and it is the one
that decides what you see, so it is worth being able to test without
launching FreeCAD. A stub `FreeCAD` module plus fake document objects is
enough: scene.py imports App only for the console and ActiveDocument.

    python3 tests/test_scene.py
"""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# --- stub FreeCAD before importing the module under test ------------------- #

_stub = types.ModuleType("FreeCAD")
_stub.ActiveDocument = None
_stub.Console = types.SimpleNamespace(
    PrintError=lambda *a, **k: None,
    PrintMessage=lambda *a, **k: None,
)
sys.modules.setdefault("FreeCAD", _stub)

from freecad.nxt.tree import health, scene  # noqa: E402

# --- fakes ----------------------------------------------------------------- #


class FakeViewObject(object):
    def __init__(self, owner):
        self._owner = owner
        self.Visibility = True

    def claimChildren(self):
        return list(self._owner._claims)


class FakeObject(object):
    def __init__(self, name, type_id, bases=()):
        self.Name = name
        self.Label = name
        self.TypeId = type_id
        self._bases = set(bases) | {type_id}
        self._claims = []
        self.State = []
        self.InList = []
        self.PropertiesList = []
        self._props = {}
        self.ViewObject = FakeViewObject(self)

    def isDerivedFrom(self, base):
        return base in self._bases

    def claims(self, *objects):
        self._claims.extend(objects)
        return self

    def link(self, prop, value):
        self.PropertiesList.append(prop)
        self._props[prop] = value
        setattr(self, prop, value)
        targets = value if isinstance(value, (list, tuple)) else [value]
        for target in targets:
            if hasattr(target, "InList") and self not in target.InList:
                target.InList.append(self)
        return self

    def getTypeIdOfProperty(self, prop):
        if prop in self._props:
            return "App::PropertyLink"
        return "App::PropertyString"


class FakeDocument(object):
    def __init__(self, name, objects):
        self.Name = name
        self.Label = name
        self.Objects = objects

    def getObject(self, name):
        for obj in self.Objects:
            if obj.Name == name:
                return obj
        return None


def sketch(name):
    return FakeObject(name, "Sketcher::SketchObject",
                      ["Part::Part2DObject", "Sketcher::SketchObject"])


def body(name):
    return FakeObject(name, "PartDesign::Body", ["PartDesign::Body"])


def feature(name):
    return FakeObject(name, "PartDesign::Pad", ["PartDesign::Feature"])


def group(name):
    return FakeObject(name, "App::DocumentObjectGroup",
                      ["App::DocumentObjectGroup"])


# --- tests ----------------------------------------------------------------- #

class PartitionTests(unittest.TestCase):

    def _partdesign(self):
        """Body { Sketch, Pad(<- Sketch), Pocket(<- Sketch) } - one reused."""
        b = body("Body")
        pad = feature("Pad")
        pocket = feature("Pocket")
        sk = sketch("Sketch")

        b.claims(pad, pocket)
        b.Group = [sk, pad, pocket]   # creation order, as FreeCAD records it
        pad.claims(sk)            # stock tree nests the sketch under the Pad
        pad.link("Profile", sk)
        pocket.link("Profile", sk)
        return FakeDocument("Doc", [b, sk, pad, pocket])

    def test_sketch_is_lifted_into_the_timeline(self):
        snap = scene.Snapshot(self._partdesign())
        self.assertEqual(snap.profiles, ["Sketch"])
        flat = [name for name, _d in snap.flatten(set(snap.nodes))]
        # not nested under the Pad that claims it, and not at the end
        self.assertEqual(flat, ["Body", "Sketch", "Pad", "Pocket"])
        self.assertEqual(snap.nodes["Sketch"].parent, "Body")
        self.assertEqual([snap.nodes[n].timeline
                          for n in ("Sketch", "Pad", "Pocket")], [0, 1, 2])

    def test_the_classic_tree_keeps_the_sketch_under_its_feature(self):
        snap = scene.Snapshot(self._partdesign(), part_layout=scene.NESTED)
        flat = [name for name, _d in snap.flatten(set(snap.nodes))]
        self.assertEqual(flat, ["Body", "Pad", "Sketch", "Pocket"])
        self.assertEqual(snap.nodes["Sketch"].parent, "Pad")
        self.assertFalse(snap.nodes["Sketch"].is_lifted)
        self.assertEqual(snap.nodes["Pad"].parent, "Body")

    def test_sketch_sits_at_one_depth_with_the_features(self):
        snap = scene.Snapshot(self._partdesign())
        depths = dict(snap.flatten(set(snap.nodes)))
        self.assertEqual(depths["Sketch"], depths["Pad"])

    def test_group_order_beats_claim_order_for_the_timeline(self):
        b = body("Body")
        pad = feature("Pad")
        pocket = feature("Pocket")
        sk = sketch("Sketch")
        b.claims(pocket, pad)          # claim order disagrees on purpose
        b.Group = [sk, pad, pocket]
        pad.link("Profile", sk)
        snap = scene.Snapshot(FakeDocument("Doc", [b, sk, pad, pocket]))
        self.assertEqual(snap.nodes["Body"].children,
                         ["Sketch", "Pad", "Pocket"])

    def test_lifted_sketch_lands_where_it_was_drawn_without_group(self):
        """No Group to read.

        claim order is the backbone, the sketch slots in ahead of the
        first sibling created after it.
        """
        b = body("Body")
        pad = feature("Pad")
        pocket = feature("Pocket")
        sk = sketch("Sketch")
        b.claims(pad, pocket)
        pad.claims(sk)
        pad.link("Profile", sk)
        snap = scene.Snapshot(FakeDocument("Doc", [b, sk, pad, pocket]))
        self.assertEqual(snap.nodes["Body"].children,
                         ["Sketch", "Pad", "Pocket"])

    def test_consumers_are_found_on_both_features(self):
        snap = scene.Snapshot(self._partdesign())
        consumers = {name for name, _l, _p in snap.nodes["Sketch"].consumers}
        self.assertEqual(consumers, {"Pad", "Pocket"})

    def test_back_references_land_on_every_consumer(self):
        snap = scene.Snapshot(self._partdesign())
        self.assertEqual(snap.nodes["Pad"].refs, [("Sketch", "Sketch", 0, "")])
        self.assertEqual(snap.nodes["Pocket"].refs,
                         [("Sketch", "Sketch", 0, "")])

    def test_a_consumer_linking_twice_counts_once(self):
        """A consumer linking twice counts once.

        InList carries one entry per link; a Pad that reaches its sketch
        through two properties must still be a single user of it.
        """
        pad = feature("Pad")
        sk = sketch("Sketch")
        pad.link("Profile", sk)
        pad.link("Section", sk)
        snap = scene.Snapshot(FakeDocument("Doc", [pad, sk]))
        self.assertEqual(len(snap.nodes["Sketch"].consumers), 1)
        self.assertEqual(snap.nodes["Sketch"].consumers[0][0], "Pad")
        self.assertEqual(snap.nodes["Sketch"].consumers[0][2],
                         ["Profile", "Section"])
        self.assertEqual(snap.nodes["Pad"].refs, [("Sketch", "Sketch", 0, "")])

    def test_sketch_referencing_a_sketch_is_a_consumer(self):
        """A sketch referencing a sketch is a consumer.

        External geometry makes one profile a user of another, which is
        why a shelf entry's count can exceed the features that use it.
        """
        pad = feature("Pad")
        base = sketch("Sketch")
        derived = sketch("Sketch001")
        pad.link("Profile", base)
        derived.link("ExternalGeometry", base)
        snap = scene.Snapshot(FakeDocument("Doc", [pad, base, derived]))
        consumers = [name for name, _l, _p in snap.nodes["Sketch"].consumers]
        self.assertEqual(sorted(consumers), ["Pad", "Sketch001"])

    def test_container_resolves_through_the_original_claimer(self):
        snap = scene.Snapshot(self._partdesign())
        self.assertEqual(snap.nodes["Sketch"].container, "Body")

    def test_containment_links_do_not_count_as_use(self):
        g = group("Group")
        sk = sketch("Sketch")
        g.claims(sk)
        g.link("Group", [sk])
        snap = scene.Snapshot(FakeDocument("Doc", [g, sk]))
        self.assertEqual(snap.nodes["Sketch"].consumers, [])
        self.assertEqual(snap.nodes["Sketch"].container, "Group")

    def test_object_claimed_only_by_a_profile_is_rehomed(self):
        """A hoisted sketch must not drag its own claims off the panel."""
        b = body("Body")
        sk = sketch("Sketch")
        array = FakeObject("Array", "Part::FeaturePython")
        b.claims(sk)
        sk.claims(array)
        array.link("Base", sk)
        snap = scene.Snapshot(FakeDocument("Doc", [b, sk, array]))
        flat = [name for name, _d in snap.flatten(set(snap.nodes))]
        self.assertIn("Array", flat)
        self.assertEqual(snap.nodes["Array"].parent, "Body")

    def test_unclaimed_sketch_is_filed_at_the_top(self):
        """An unclaimed sketch is filed at the top.

        With no container to belong to, a loose sketch is filed in the
        document's Sketches group rather than lost.
        """
        sk = sketch("Loose")
        snap = scene.Snapshot(FakeDocument("Doc", [sk]))
        self.assertEqual(snap.profiles, ["Loose"])
        self.assertEqual(snap.roots, ["~Sketches"])
        self.assertEqual(snap.nodes["~Sketches"].children, ["Loose"])
        self.assertEqual(snap.nodes["Loose"].consumers, [])

    def test_double_claim_is_recorded_not_duplicated(self):
        a = feature("A")
        bb = feature("B")
        child = feature("Child")
        a.claims(child)
        bb.claims(child)
        snap = scene.Snapshot(FakeDocument("Doc", [a, bb, child]))
        flat = [name for name, _d in snap.flatten(set(snap.nodes))]
        self.assertEqual(flat.count("Child"), 1)
        self.assertEqual(snap.orphan_claims, [("Child", ["A", "B"])])

    def test_claim_order_is_preserved(self):
        b = body("Body")
        first = feature("First")
        second = feature("Second")
        b.claims(second, first)     # deliberately not document order
        snap = scene.Snapshot(FakeDocument("Doc", [b, first, second]))
        self.assertEqual(snap.nodes["Body"].children, ["Second", "First"])

    def test_widen_hoists_draft_geometry(self):
        wire = FakeObject("Wire", "Part::Part2DObjectPython",
                          ["Part::Part2DObject"])
        doc = FakeDocument("Doc", [wire])
        self.assertEqual(scene.Snapshot(doc).profiles, [])
        self.assertEqual(scene.Snapshot(doc, widen=True).profiles, ["Wire"])


class FeatureStackTests(unittest.TestCase):
    """The Body's rollback bar is only as good as the order it walks."""

    def _body(self, group, tip=None):
        b = body("Body")
        b.Group = list(group)
        b.claims(*group)
        b.Tip = tip
        return b

    def _chain(self, *names):
        feats = []
        previous = None
        for name in names:
            f = feature(name)
            f.link("BaseFeature", previous)
            feats.append(f)
            previous = f
        return feats

    def test_order_follows_basefeature_not_group(self):
        pad, pocket, fillet = self._chain("Pad", "Pocket", "Fillet")
        b = self._body([fillet, pad, pocket], tip=fillet)   # scrambled
        snap = scene.Snapshot(FakeDocument("Doc", [b, fillet, pad, pocket]))
        self.assertEqual(snap.nodes["Body"].stack, ["Pad", "Pocket", "Fillet"])

    def test_tip_marks_everything_after_it_as_inert(self):
        pad, pocket, fillet = self._chain("Pad", "Pocket", "Fillet")
        b = self._body([pad, pocket, fillet], tip=pocket)
        snap = scene.Snapshot(FakeDocument("Doc", [b, pad, pocket, fillet]))
        self.assertEqual(snap.nodes["Body"].tip, "Pocket")
        self.assertFalse(snap.nodes["Pad"].after_tip)
        self.assertFalse(snap.nodes["Pocket"].after_tip)
        self.assertTrue(snap.nodes["Fillet"].after_tip)

    def test_every_stack_member_knows_its_body(self):
        pad, pocket = self._chain("Pad", "Pocket")
        b = self._body([pad, pocket], tip=pocket)
        snap = scene.Snapshot(FakeDocument("Doc", [b, pad, pocket]))
        self.assertTrue(snap.nodes["Pad"].is_feature)
        self.assertEqual(snap.nodes["Pad"].body, "Body")
        self.assertFalse(snap.nodes["Body"].is_feature)

    def test_no_tip_means_the_whole_stack_is_inert(self):
        pad, pocket = self._chain("Pad", "Pocket")
        b = self._body([pad, pocket], tip=None)
        snap = scene.Snapshot(FakeDocument("Doc", [b, pad, pocket]))
        self.assertTrue(snap.nodes["Pad"].after_tip)
        self.assertTrue(snap.nodes["Pocket"].after_tip)

    def test_members_without_basefeature_are_not_stack_entries(self):
        """Datums and shape binders live in the Body but are not history."""
        pad, pocket = self._chain("Pad", "Pocket")
        datum = FakeObject("DatumPlane", "PartDesign::Plane",
                           ["PartDesign::Feature"])     # no BaseFeature
        b = self._body([pad, datum, pocket], tip=pocket)
        snap = scene.Snapshot(FakeDocument("Doc", [b, pad, datum, pocket]))
        self.assertEqual(snap.nodes["Body"].stack, ["Pad", "Pocket"])
        self.assertFalse(snap.nodes["DatumPlane"].is_feature)

    def test_only_the_chain_through_the_tip_is_the_stack(self):
        """Group membership is not history.

        A feature claiming no predecessor and reachable from no other
        feature is off the chain, and the tip can never be moved to it.
        """
        a = feature("A")
        stray = feature("Stray")
        a.link("BaseFeature", None)
        stray.link("BaseFeature", None)
        b = self._body([a, stray], tip=a)
        snap = scene.Snapshot(FakeDocument("Doc", [b, a, stray]))
        self.assertEqual(snap.nodes["Body"].stack, ["A"])
        self.assertFalse(snap.nodes["Stray"].is_feature)

    def test_multitransform_subfeatures_never_enter_the_stack(self):
        """MultiTransform subfeatures never enter the stack.

        A MultiTransform is a real history step; the transformations it
        owns are not. They derive from PartDesign::Feature and carry a
        BaseFeature property, so only the chain walk keeps them out.
        """
        pad, multi = self._chain("Pad", "MultiTransform")
        mirrored = feature("Mirrored")
        mirrored.link("BaseFeature", None)
        multi.link("Transformations", [mirrored])

        # The Body lists it in Group but does not claim it - the
        # MultiTransform owns it in the tree, which is exactly the shape
        # that made Group membership an unsafe definition of history.
        b = body("Body")
        b.Group = [pad, multi, mirrored]
        b.claims(pad, multi)
        b.Tip = multi
        multi.claims(mirrored)
        snap = scene.Snapshot(FakeDocument("Doc", [b, pad, multi, mirrored]))
        self.assertEqual(snap.nodes["Body"].stack, ["Pad", "MultiTransform"])
        self.assertFalse(snap.nodes["Mirrored"].is_feature)
        # ...and it is lifted, like any other thing an operation reads: the
        # MultiTransform links to it through Transformations, so nesting it
        # would say the MultiTransform owns it. It joins the Body's
        # timeline, off the stack, with a chip left on its user.
        self.assertTrue(snap.nodes["Mirrored"].is_lifted)
        self.assertEqual(snap.nodes["Mirrored"].parent, "Body")
        self.assertEqual(
            [n for n, _l, _s, _p in snap.nodes["MultiTransform"].refs],
            ["Mirrored"])

    def test_the_chain_is_recovered_from_either_side_of_the_tip(self):
        pad, pocket, fillet = self._chain("Pad", "Pocket", "Fillet")
        b = self._body([pad, pocket, fillet], tip=pad)   # tip at the start
        snap = scene.Snapshot(FakeDocument("Doc", [b, pad, pocket, fillet]))
        self.assertEqual(snap.nodes["Body"].stack, ["Pad", "Pocket", "Fillet"])

    def test_without_a_tip_the_longest_chain_wins(self):
        pad, pocket = self._chain("Pad", "Pocket")
        stray = feature("Stray")
        stray.link("BaseFeature", None)
        b = self._body([stray, pad, pocket], tip=None)
        snap = scene.Snapshot(FakeDocument("Doc", [b, stray, pad, pocket]))
        self.assertEqual(snap.nodes["Body"].stack, ["Pad", "Pocket"])

    def test_a_body_without_features_offers_no_bar(self):
        b = self._body([], tip=None)
        snap = scene.Snapshot(FakeDocument("Doc", [b]))
        self.assertEqual(snap.nodes["Body"].stack, [])


class HealthTests(unittest.TestCase):
    """Solver findings, read defensively - the accessors vary by build."""

    def _sketch(self, name="Sketch", **findings):
        """Findings set as plain attributes - the real API is properties."""
        obj = sketch(name)
        for accessor, value in findings.items():
            setattr(obj, accessor, value)
        return obj

    def _sketch_with_getters(self, name="Sketch", **findings):
        """Findings behind zero-argument getters.

        The same findings behind zero-argument getters, since which shape
        a build offers has already changed once.
        """
        obj = sketch(name)
        for accessor, value in findings.items():
            setattr(obj, accessor, (lambda v: (lambda: v))(value))
        return obj

    def test_a_build_without_the_accessors_says_so(self):
        """Missing accessors are reported, not read as healthy.

        Absence must read as 'no information', never as 'no problem
        found' - and it must not raise.
        """
        severity, notes = health.inspect(self._sketch(),
                                         note_unavailable=True)
        self.assertEqual(severity, health.NONE)
        self.assertEqual(notes, ["solver findings unavailable in this build"])
        self.assertFalse(health.answers(self._sketch()))
        self.assertEqual(health.available(self._sketch()),
                         {a: False for a, _s, _p in health.CHECKS})

    def test_the_unavailable_note_is_off_by_default(self):
        """The unavailable note is off by default.

        It is one fact about the installation, not thirty about
        sketches; repeating it per card buried the cards with findings.
        """
        obj = sketch("Sketch")
        obj.FullyConstrained = False
        self.assertEqual(health.inspect(obj)[1], [])

    def test_no_accessors_is_reported_rather_than_implying_health(self):
        """The failure mode that matters.

        reporting only what little is readable reads as a clean bill of
        health.
        """
        obj = sketch("Sketch")
        obj.FullyConstrained = False
        _severity, notes = health.inspect(obj, note_unavailable=True)
        self.assertEqual(notes, ["solver findings unavailable in this build"])

    def test_an_accessor_that_answers_cleanly_is_not_called_unavailable(self):
        obj = self._sketch(RedundantConstraints=[])
        _severity, notes = health.inspect(obj, note_unavailable=True)
        self.assertNotIn("solver findings unavailable in this build", notes)
        self.assertTrue(health.answers(obj))

    def test_the_snapshot_records_whether_the_build_answers_at_all(self):
        quiet = sketch("Sketch")
        snap = scene.Snapshot(FakeDocument("Doc", [quiet]))
        self.assertFalse(snap.solver_findings)

        talks = sketch("Sketch001")
        talks.RedundantConstraints = lambda: []
        snap = scene.Snapshot(FakeDocument("Doc", [talks]))
        self.assertTrue(snap.solver_findings)

    def test_redundant_constraints_warn_and_name_their_indices(self):
        obj = self._sketch(RedundantConstraints=[32])
        severity, notes = health.inspect(obj)
        self.assertEqual(severity, health.WARNING)
        self.assertIn("redundant constraints: 32", notes)

    def test_a_finding_behind_a_getter_is_honoured(self):
        """Property or zero-argument getter - both must register."""
        obj = self._sketch_with_getters(RedundantConstraints=[32])
        severity, notes = health.inspect(obj)
        self.assertEqual(severity, health.WARNING)
        self.assertIn("redundant constraints: 32", notes)

    def test_an_empty_property_is_not_a_finding(self):
        obj = self._sketch(RedundantConstraints=[])
        self.assertEqual(health.inspect(obj)[0], health.NONE)

    def test_the_snapshot_separates_open_sketches_from_broken_ones(self):
        open_one = sketch("Sketch001")
        open_one.FullyConstrained = False
        open_one.DoF = 14
        done = sketch("Sketch002")
        done.FullyConstrained = True
        done.DoF = 0
        broken = sketch("Sketch003")
        broken.RedundantConstraints = [32]
        broken.FullyConstrained = True
        broken.DoF = 0

        snap = scene.Snapshot(FakeDocument("Doc", [open_one, done, broken]))
        self.assertEqual(snap.unconstrained_profiles(), ["Sketch001"])
        self.assertEqual(snap.problem_profiles(), ["Sketch003"])
        self.assertEqual(snap.nodes["Sketch001"].dof, 14)
        self.assertIs(snap.nodes["Sketch002"].constrained, True)

    def test_freecads_own_words_are_the_fallback(self):
        """FreeCAD's own words are the fallback.

        GetStatusString is what the stock tree puts in its tooltip, so
        using it verbatim keeps the panel from drifting from the rest of
        the application.
        """
        obj = sketch("Sketch")
        obj.getStatusString = lambda: "Sketch with redundant constraints\n32\n"
        _severity, notes = health.inspect(obj)
        self.assertEqual(notes[:2],
                         ["Sketch with redundant constraints", "32"])

    def test_dump_never_calls_a_method_that_could_edit_the_sketch(self):
        """Several names matching "redundant" remove redundant constraints."""
        obj = sketch("Sketch")
        calls = []
        obj.autoRemoveRedundants = lambda *a: calls.append("autoRemove")
        obj.RedundantConstraints = lambda: [3]
        rows = dict(health.dump(obj))
        self.assertEqual(calls, [])
        self.assertEqual(rows["autoRemoveRedundants"], "<method, not called>")
        self.assertEqual(rows["RedundantConstraints"], "[3]")

    def test_conflicting_constraints_are_an_error_not_a_warning(self):
        obj = self._sketch(ConflictingConstraints=[4, 9])
        severity, notes = health.inspect(obj)
        self.assertEqual(severity, health.ERROR)
        self.assertIn("conflicting constraints: 4, 9", notes)

    def test_the_worst_finding_sets_the_severity(self):
        obj = self._sketch(RedundantConstraints=[1],
                           ConflictingConstraints=[2])
        severity, _notes = health.inspect(obj)
        self.assertEqual(severity, health.ERROR)

    def test_a_failed_recompute_is_an_error_on_its_own(self):
        severity, notes = health.inspect(self._sketch(), in_error=True)
        self.assertEqual(severity, health.ERROR)
        self.assertIn("failed to recompute", notes)

    def test_an_accessor_that_raises_is_treated_as_absent(self):
        obj = sketch("Sketch")

        def boom():
            raise RuntimeError("solver unavailable")

        obj.RedundantConstraints = boom
        severity, notes = health.inspect(obj, note_unavailable=True)
        self.assertEqual(severity, health.NONE)
        self.assertIn("solver findings unavailable in this build", notes)
        self.assertFalse(health.answers(obj))

    def test_constraint_state_is_not_a_finding(self):
        """Constraint state is not a finding.

        Most working sketches have degrees of freedom left - 18 of 30 in
        the document this was built against - so treating that as a finding
        would mark the majority of the shelf and say nothing. It is read
        separately and shown on the line that already carries the container.
        """
        obj = sketch("Sketch")
        obj.FullyConstrained = False
        obj.DoF = 14
        severity, notes = health.inspect(obj)
        self.assertEqual(severity, health.NONE)
        self.assertEqual(notes, [])
        self.assertEqual(health.degrees_of_freedom(obj), 14)
        self.assertIs(health.fully_constrained(obj), False)

    def test_the_snapshot_counts_only_profiles_with_findings(self):
        bad = sketch("Sketch001")
        bad.RedundantConstraints = lambda: [32]
        good = sketch("Sketch002")
        pad = feature("Pad")
        pad.link("Profile", bad)
        snap = scene.Snapshot(FakeDocument("Doc", [pad, bad, good]))
        self.assertEqual(snap.problem_profiles(), ["Sketch001"])
        self.assertEqual(snap.nodes["Sketch001"].severity, health.WARNING)
        self.assertEqual(snap.nodes["Sketch002"].severity, health.NONE)

    def test_solver_findings_are_not_read_for_non_profiles(self):
        """A Pad has no solver; its only health is the document's State."""
        pad = feature("Pad")
        pad.RedundantConstraints = lambda: [1]
        snap = scene.Snapshot(FakeDocument("Doc", [pad]))
        self.assertEqual(snap.nodes["Pad"].severity, health.NONE)


class BlameTests(unittest.TestCase):
    """Blame lands on the broken sketch, not its consumer.

    A feature that failed because its sketch is broken should say so on
    the sketch, not on itself.
    """

    def _doc(self):
        pad = feature("Pad")
        pad.State = ["Invalid"]
        sk = sketch("Sketch")
        sk.RedundantConstraints = [32]
        pad.claims(sk)
        pad.link("Profile", sk)
        return FakeDocument("Doc", [pad, sk])

    def test_a_reference_carries_the_profiles_severity(self):
        snap = scene.Snapshot(self._doc())
        self.assertEqual(snap.nodes["Pad"].refs,
                         [("Sketch", "Sketch", health.WARNING, "")])

    def test_a_healthy_profile_carries_no_severity(self):
        pad = feature("Pad")
        sk = sketch("Sketch")
        pad.link("Profile", sk)
        snap = scene.Snapshot(FakeDocument("Doc", [pad, sk]))
        self.assertEqual(snap.nodes["Pad"].refs[0][2], health.NONE)

    def test_an_errored_profile_is_flagged_on_the_reference(self):
        pad = feature("Pad")
        sk = sketch("Sketch")
        sk.State = ["Invalid"]
        pad.link("Profile", sk)
        snap = scene.Snapshot(FakeDocument("Doc", [pad, sk]))
        self.assertEqual(snap.nodes["Pad"].refs[0][2], health.ERROR)


class SearchTests(unittest.TestCase):
    """Search returns somewhere to go; it never reshapes the tree."""

    def _doc(self):
        root = group("Assembly")
        b = body("Bracket")
        pad = feature("Pad")
        pad.Label = "Base Pad"
        hole = feature("HoleCut")
        sk = sketch("Outline")
        root.claims(b)
        b.claims(pad, hole)
        pad.claims(sk)
        pad.link("Profile", sk)
        return FakeDocument("Doc", [root, b, pad, hole, sk])

    def _names(self, snap, text):
        return [node.name for node in snap.search(text)]

    def test_a_prefix_beats_a_match_in_the_middle(self):
        """Typing 'pad' should reach Pad before HolePadded."""
        a = feature("Pad")
        b = feature("HolePadded")
        snap = scene.Snapshot(FakeDocument("Doc", [b, a]))
        self.assertEqual(self._names(snap, "pad"), ["Pad", "HolePadded"])

    def test_labels_beat_internal_names(self):
        shown = feature("Feature001")
        shown.Label = "Rib"
        internal = feature("Rib002")
        internal.Label = "Chamfer"
        snap = scene.Snapshot(FakeDocument("Doc", [internal, shown]))
        self.assertEqual(self._names(snap, "rib"), ["Feature001", "Rib002"])

    def test_profiles_are_searchable_too(self):
        """Profiles are searchable too.

        They have no row in the tree at all, so a tree-only search would
        miss exactly the objects this panel goes out of its way to hoist.
        """
        snap = scene.Snapshot(self._doc())
        self.assertEqual(self._names(snap, "outline"), ["Outline"])

    def test_search_is_case_insensitive(self):
        snap = scene.Snapshot(self._doc())
        self.assertIn("HoleCut", self._names(snap, "HOLE"))

    def test_empty_query_returns_nothing(self):
        snap = scene.Snapshot(self._doc())
        self.assertEqual(snap.search(""), [])
        self.assertEqual(snap.search("   "), [])

    def test_the_limit_is_honoured(self):
        objects = [feature("Pad%03d" % n) for n in range(40)]
        snap = scene.Snapshot(FakeDocument("Doc", objects))
        self.assertEqual(len(snap.search("pad", limit=5)), 5)

    def test_the_tree_is_untouched_by_a_search(self):
        snap = scene.Snapshot(self._doc())
        before = snap.flatten(snap.default_expansion())
        snap.search("holecut")
        self.assertEqual(snap.flatten(snap.default_expansion()), before)

    def test_path_gives_a_hit_somewhere_to_say_it_lives(self):
        snap = scene.Snapshot(self._doc())
        self.assertEqual(snap.path_of("HoleCut"), ["Assembly", "Bracket"])
        self.assertEqual(snap.path_of("HoleCut", limit=1), ["Bracket"])
        self.assertEqual(snap.path_of("Assembly"), [])


class FlattenTests(unittest.TestCase):

    def _nested(self):
        root = group("Root")
        mid = group("Mid")
        leaf = feature("Leaf")
        root.claims(mid)
        mid.claims(leaf)
        return FakeDocument("Doc", [root, mid, leaf])

    def test_collapsed_hides_descendants(self):
        snap = scene.Snapshot(self._nested())
        self.assertEqual(snap.flatten(set()), [("Root", 0)])

    def test_expansion_is_honoured_level_by_level(self):
        snap = scene.Snapshot(self._nested())
        self.assertEqual(snap.flatten({"Root"}), [("Root", 0), ("Mid", 1)])
        self.assertEqual(snap.flatten({"Root", "Mid"}),
                         [("Root", 0), ("Mid", 1), ("Leaf", 2)])

    def test_default_expansion_opens_containers_only(self):
        snap = scene.Snapshot(self._nested())
        self.assertEqual(snap.default_expansion(), {"Root", "Mid"})

    def test_mutual_claim_cycle_still_yields_a_root(self):
        """Two objects claiming each other must not both vanish."""
        a = group("A")
        b = group("B")
        a.claims(b)
        b.claims(a)
        snap = scene.Snapshot(FakeDocument("Doc", [a, b]))
        flat = [name for name, _d in snap.flatten(set(snap.nodes))]
        self.assertEqual(sorted(flat), ["A", "B"])

    def test_self_claiming_object_does_not_hang(self):
        odd = group("Odd")
        odd.claims(odd)
        snap = scene.Snapshot(FakeDocument("Doc", [odd]))
        self.assertEqual(snap.flatten(set(snap.nodes)), [("Odd", 0)])


class LiftingTests(unittest.TestCase):
    """Lifting was never really about sketches.

    Anything an operation *reads* is lifted out of it, for the same
    reasons.
    """

    def test_a_referenced_solid_is_lifted_like_a_sketch(self):
        b = body("Body")
        tool = FakeObject("Tool", "Part::Box", ["Part::Feature"])
        cut = feature("Cut")
        cut.claims(tool)              # stock tree nests the tool under it
        cut.link("Base", tool)
        b.Group = [tool, cut]
        b.claims(cut)
        snap = scene.Snapshot(FakeDocument("Doc", [b, tool, cut]))

        self.assertTrue(snap.nodes["Tool"].is_lifted)
        self.assertFalse(snap.nodes["Tool"].is_profile)
        self.assertEqual(snap.nodes["Tool"].parent, "Body")
        self.assertEqual(snap.nodes["Body"].children, ["Tool", "Cut"])
        self.assertEqual([n for n, _l, _s, _p in snap.nodes["Cut"].refs],
                         ["Tool"])
        self.assertEqual([n for n, _l, _p in snap.nodes["Tool"].consumers],
                         ["Cut"])

    def test_holding_something_is_not_using_it(self):
        """A container claims its members and links them through Group.

        That is containment, and lifting on it would empty every tree.
        """
        part = group("Part")
        box = FakeObject("Box", "Part::Box", ["Part::Feature"])
        part.claims(box)
        part.link("Group", [box])
        snap = scene.Snapshot(FakeDocument("Doc", [part, box]))

        self.assertFalse(snap.nodes["Box"].is_lifted)
        self.assertEqual(snap.nodes["Box"].parent, "Part")

    def test_a_claim_without_a_link_is_left_nested(self):
        """A claim without a link is left nested.

        An Origin claims its planes but reaches them through a
        containment property. Nothing reads them, so nothing is lifted.
        """
        origin = FakeObject("Origin", "App::Origin", ["App::Origin"])
        plane = FakeObject("XY_Plane", "App::Plane", ["App::Plane"])
        origin.claims(plane)
        origin.link("OriginFeatures", [plane])
        snap = scene.Snapshot(FakeDocument("Doc", [origin, plane]))

        self.assertFalse(snap.nodes["XY_Plane"].is_lifted)
        self.assertEqual(snap.nodes["XY_Plane"].parent, "Origin")

    def test_a_lifted_reference_rolls_back_with_the_timeline(self):
        b = body("Body")
        datum = FakeObject("Datum", "PartDesign::Plane",
                           ["PartDesign::Feature"])
        pad, pocket = feature("Pad"), feature("Pocket")
        pad.link("BaseFeature", None)
        pocket.link("BaseFeature", pad)
        pocket.claims(datum)
        pocket.link("AttachmentSupport", datum)
        b.Group = [pad, datum, pocket]
        b.claims(pad, pocket)
        b.Tip = pad
        snap = scene.Snapshot(FakeDocument("Doc", [b, pad, datum, pocket]))

        self.assertTrue(snap.nodes["Datum"].is_lifted)
        self.assertEqual(snap.nodes["Body"].children,
                         ["Pad", "Datum", "Pocket"])
        # drawn after the tip, so it had not been made yet
        self.assertTrue(snap.nodes["Datum"].after_tip)
        self.assertEqual(snap.nodes["Datum"].body, "Body")

    def test_what_a_lifted_object_claims_is_not_lifted_with_it(self):
        b = body("Body")
        tool = FakeObject("Tool", "Part::Box", ["Part::Feature"])
        knob = FakeObject("Knob", "Part::Feature", ["Part::Feature"])
        cut = feature("Cut")
        cut.claims(tool)
        cut.link("Base", tool)
        tool.claims(knob)             # and nothing links to Knob
        b.Group = [tool, cut]
        b.claims(cut)
        snap = scene.Snapshot(FakeDocument("Doc", [b, tool, knob, cut]))

        self.assertTrue(snap.nodes["Tool"].is_lifted)
        self.assertFalse(snap.nodes["Knob"].is_lifted)
        # re-homed onto the lifted object's nearest unlifted ancestor, so it
        # does not vanish and the lifted row stays a leaf
        self.assertEqual(snap.nodes["Knob"].parent, "Body")
        self.assertEqual(snap.nodes["Tool"].children, [])

    def test_the_lifted_list_covers_profiles_and_references(self):
        b = body("Body")
        sk = sketch("Sketch")
        tool = FakeObject("Tool", "Part::Box", ["Part::Feature"])
        pad = feature("Pad")
        pad.link("Profile", sk)
        pad.claims(sk, tool)
        pad.link("Base", tool)
        b.Group = [sk, tool, pad]
        b.claims(pad)
        snap = scene.Snapshot(FakeDocument("Doc", [b, sk, tool, pad]))

        self.assertEqual(snap.profiles, ["Sketch"])
        self.assertEqual(sorted(snap.lifted), ["Sketch", "Tool"])
        self.assertEqual([n for n, _l, _s, _p in snap.nodes["Pad"].refs],
                         ["Sketch", "Tool"])


class SubElementTests(unittest.TestCase):
    """A feature built on a selected face of an earlier feature.

    The owner of that face is a solid in the Body, claimed by a container,
    so it is never lifted - which is exactly why reading references
    backwards from the lifted objects found nothing to show here.
    """

    def _doc(self, value):
        b = body("Body")
        pad, pocket = feature("Pad"), feature("Pocket")
        pad.link("BaseFeature", None)
        pocket.link("BaseFeature", pad)
        pocket.link("UpToFace", value)
        b.Group = [pad, pocket]
        b.claims(pad, pocket)
        b.Tip = pocket
        return pad, pocket, FakeDocument("Doc", [b, pad, pocket])

    def test_a_face_reference_names_its_owner_and_the_face(self):
        pad, _pocket, doc = self._doc(None)
        pad_obj = doc.getObject("Pad")
        doc.getObject("Pocket")._props["UpToFace"] = (pad_obj, ["Face3"])
        doc.getObject("Pocket").UpToFace = (pad_obj, ["Face3"])
        snap = scene.Snapshot(doc)
        self.assertEqual(snap.nodes["Pocket"].refs,
                         [("Pad", "Pad", 0, "Face3")])

    def test_several_faces_of_one_object_are_one_reference(self):
        pad, _pocket, doc = self._doc(None)
        pad_obj = doc.getObject("Pad")
        doc.getObject("Pocket").UpToFace = (pad_obj, ["Face3", "Face5"])
        snap = scene.Snapshot(doc)
        self.assertEqual(snap.nodes["Pocket"].refs,
                         [("Pad", "Pad", 0, "Face3, Face5")])

    def test_a_whole_object_reference_names_no_part(self):
        pad, _pocket, doc = self._doc(None)
        doc.getObject("Pocket").UpToFace = doc.getObject("Pad")
        snap = scene.Snapshot(doc)
        self.assertEqual(snap.nodes["Pocket"].refs, [("Pad", "Pad", 0, "")])

    def test_the_face_owner_is_not_lifted_by_being_referenced(self):
        """A face owner is not lifted by being referenced.

        It is claimed by the Body, which is a container, so it keeps its
        place in the timeline instead of being pulled under the Pocket.
        """
        pad, _pocket, doc = self._doc(None)
        doc.getObject("Pocket").UpToFace = (doc.getObject("Pad"), ["Face3"])
        snap = scene.Snapshot(doc)
        self.assertFalse(snap.nodes["Pad"].is_lifted)
        self.assertEqual(snap.nodes["Body"].children, ["Pad", "Pocket"])
        self.assertEqual([n for n, _l, _p in snap.nodes["Pad"].consumers],
                         ["Pocket"])

    def test_link_entries_reads_every_shape_freecad_uses(self):
        a = feature("A")
        bb = feature("B")
        cases = [
            (None, []),
            (a, [("A", [])]),
            ([a, bb], [("A", []), ("B", [])]),
            ((a, "Face1"), [("A", ["Face1"])]),
            ((a, ["Face1", "Edge2"]), [("A", ["Face1", "Edge2"])]),
            ([(a, ["Face1"]), (bb, ["Edge9"])],
             [("A", ["Face1"]), ("B", ["Edge9"])]),
        ]
        for value, expected in cases:
            got = [(obj.Name, subs) for obj, subs in scene.link_entries(value)]
            self.assertEqual(got, expected, "misread %r" % (value,))

    def test_a_link_list_is_not_mistaken_for_a_link_sub(self):
        """Both arrive as a two-item sequence.

        Only the shape tells them apart, so the length must not be what
        decides.
        """
        a, bb = feature("A"), feature("B")
        got = [(obj.Name, subs) for obj, subs in scene.link_entries([a, bb])]
        self.assertEqual(got, [("A", []), ("B", [])])


class ChipRestraintTests(unittest.TestCase):
    """References that are true but not worth a chip.

    Reading every link forwards found references that are true but not
    worth saying. These are the ones that get filtered.
    """

    def test_a_reference_to_your_own_container_is_not_a_chip(self):
        """You can see which Body a row is in - the row is inside it."""
        b = body("Body")
        pad = feature("Pad")
        pad.link("BaseFeature", None)
        pad.link("AttachmentSupport", (b, ["Face1"]))
        b.Group = [pad]
        b.claims(pad)
        b.Tip = pad
        snap = scene.Snapshot(FakeDocument("Doc", [b, pad]))

        self.assertEqual(snap.nodes["Pad"].refs, [])
        self.assertEqual(snap.nodes["Body"].consumers, [])

    def test_a_reference_to_a_grandparent_is_not_a_chip_either(self):
        outer = group("Part")
        b = body("Body")
        pad = feature("Pad")
        pad.link("BaseFeature", None)
        pad.link("AttachmentSupport", (outer, ["Face1"]))
        b.Group = [pad]
        b.claims(pad)
        outer.link("Group", [b])
        outer.claims(b)
        snap = scene.Snapshot(FakeDocument("Doc", [outer, b, pad]))

        self.assertEqual(snap.nodes["Pad"].parent, "Body")
        self.assertEqual(snap.nodes["Body"].parent, "Part")
        self.assertEqual(snap.nodes["Pad"].refs, [])

    def test_a_sibling_is_still_a_chip(self):
        """Only the way *up* is suppressed.

        A reference across the timeline is exactly what the chips exist
        for.
        """
        b = body("Body")
        pad, pocket = feature("Pad"), feature("Pocket")
        pad.link("BaseFeature", None)
        pocket.link("BaseFeature", pad)
        pocket.link("UpToFace", (pad, ["Face3"]))
        b.Group = [pad, pocket]
        b.claims(pad, pocket)
        b.Tip = pocket
        snap = scene.Snapshot(FakeDocument("Doc", [b, pad, pocket]))

        self.assertEqual(snap.nodes["Pocket"].refs,
                         [("Pad", "Pad", 0, "Face3")])

    def test_a_sketch_reference_names_no_sub_element(self):
        """A feature reads a sketch, whole.

        The edge index an attachment happens to name is how it is
        attached, not what was chosen.
        """
        b = body("Body")
        sk = sketch("Sketch")
        pad = feature("Pad")
        pad.link("BaseFeature", None)
        pad.link("Profile", (sk, ["Edge3"]))
        b.Group = [sk, pad]
        b.claims(pad)
        b.Tip = pad
        snap = scene.Snapshot(FakeDocument("Doc", [b, sk, pad]))

        self.assertEqual(snap.nodes["Pad"].refs,
                         [("Sketch", "Sketch", 0, "")])

    def test_a_non_profile_keeps_its_sub_element(self):
        b = body("Body")
        datum = FakeObject("Datum", "PartDesign::Plane",
                           ["PartDesign::Feature"])
        pad = feature("Pad")
        pad.link("BaseFeature", None)
        pad.link("AttachmentSupport", (datum, ["Edge3"]))
        b.Group = [datum, pad]
        b.claims(pad)
        b.Tip = pad
        snap = scene.Snapshot(FakeDocument("Doc", [b, datum, pad]))

        self.assertEqual(snap.nodes["Pad"].refs,
                         [("Datum", "Datum", 0, "Edge3")])


class TimelineTests(unittest.TestCase):
    """Mapping between where the bar lands and the tip it sets.

    The bar sets a tip, but it drops into a list that also holds
    sketches, so the mapping between where it lands and what it sets is
    the whole contract.
    """

    def _doc(self):
        """Sketch, Pad, Sketch001, Pocket - drawn and used alternately."""
        b = body("Body")
        s1, s2 = sketch("Sketch"), sketch("Sketch001")
        pad, pocket = feature("Pad"), feature("Pocket")
        pad.link("BaseFeature", None)
        pocket.link("BaseFeature", pad)
        pad.link("Profile", s1)
        pocket.link("Profile", s2)
        b.Group = [s1, pad, s2, pocket]
        b.claims(pad, pocket)
        b.Tip = pocket
        return b, FakeDocument("Doc", [b, s1, pad, s2, pocket])

    def test_timeline_interleaves_sketches_and_features(self):
        _b, doc = self._doc()
        snap = scene.Snapshot(doc)
        self.assertEqual(snap.nodes["Body"].children,
                         ["Sketch", "Pad", "Sketch001", "Pocket"])
        self.assertEqual([snap.nodes[n].timeline for n in
                          ("Sketch", "Pad", "Sketch001", "Pocket")],
                         [0, 1, 2, 3])

    # The bar is dropped against the rows on screen, so these pass the
    # rows above the drop, nearest first - which is what the panel has.
    def test_bar_on_a_sketch_snaps_back_to_the_feature_before_it(self):
        _b, doc = self._doc()
        snap = scene.Snapshot(doc)
        # dropped just under Sketch001, which cannot be a tip
        self.assertEqual(
            snap.tip_at_or_before("Body", ["Sketch001", "Pad", "Sketch"]),
            "Pad")

    def test_bar_above_the_first_feature_rolls_back_to_empty(self):
        _b, doc = self._doc()
        snap = scene.Snapshot(doc)
        self.assertIsNone(snap.tip_at_or_before("Body", ["Sketch", "Body"]))

    def test_bar_at_the_end_sets_the_last_feature(self):
        _b, doc = self._doc()
        snap = scene.Snapshot(doc)
        self.assertEqual(
            snap.tip_at_or_before(
                "Body", ["Pocket", "Sketch001", "Pad", "Sketch"]),
            "Pocket")

    def test_the_scan_stops_at_the_first_feature_it_meets(self):
        """Consumed lazily, so a long tree above the drop is not walked."""
        _b, doc = self._doc()
        snap = scene.Snapshot(doc)
        seen = []

        def rows():
            for name in ["Sketch001", "Pad", "Sketch", "Body"]:
                seen.append(name)
                yield name

        self.assertEqual(snap.tip_at_or_before("Body", rows()), "Pad")
        self.assertEqual(seen, ["Sketch001", "Pad"])

    def test_a_sketch_past_the_tip_is_rolled_back_too(self):
        b, doc = self._doc()
        b.Tip = doc.getObject("Pad")
        snap = scene.Snapshot(doc)
        self.assertFalse(snap.nodes["Sketch"].after_tip)
        self.assertFalse(snap.nodes["Pad"].after_tip)
        self.assertTrue(snap.nodes["Sketch001"].after_tip)
        self.assertTrue(snap.nodes["Pocket"].after_tip)

    def test_rolled_back_sketch_knows_which_body_it_is_in(self):
        _b, doc = self._doc()
        snap = scene.Snapshot(doc)
        self.assertEqual(snap.nodes["Sketch001"].body, "Body")

    def test_an_origin_is_never_rolled_back(self):
        b, doc = self._doc()
        origin = FakeObject("Origin", "App::Origin", ["App::Origin"])
        b.Group = [origin] + list(b.Group)
        b.claims(origin)
        doc.Objects.append(origin)
        b.Tip = None
        snap = scene.Snapshot(doc)
        self.assertFalse(snap.nodes["Origin"].after_tip)
        self.assertTrue(snap.nodes["Sketch"].after_tip)

    def test_tip_for_a_body_that_is_not_there(self):
        _b, doc = self._doc()
        snap = scene.Snapshot(doc)
        self.assertIsNone(snap.tip_at_or_before("Nope", ["Pocket"]))

    # -- retip: the in-place update used while the bar is dragged -------- #

    def test_retip_matches_a_full_rebuild(self):
        """The drag path and the rebuild path must not disagree.

        Anything `retip` gets wrong would show while the bar moved and
        silently correct itself the moment it was released.
        """
        b, doc = self._doc()
        for tip in ("Pad", "Pocket"):
            dragged = scene.Snapshot(doc)          # built at the old tip
            dragged.retip("Body", tip)

            # Mirror what bridge._apply_tip does to the document, which is
            # both halves of the move: a Body shows through exactly one
            # visible feature, so setting Tip alone would leave the rebuild
            # comparing against a state the application never reaches.
            b.Tip = doc.getObject(tip)
            for member in ("Pad", "Pocket"):
                doc.getObject(member).ViewObject.Visibility = (member == tip)
            rebuilt = scene.Snapshot(doc)

            for name in ("Body", "Sketch", "Pad", "Sketch001", "Pocket"):
                self.assertEqual(
                    (dragged.nodes[name].after_tip,
                     dragged.nodes[name].visible),
                    (rebuilt.nodes[name].after_tip,
                     rebuilt.nodes[name].visible),
                    "%s disagrees after retip to %s" % (name, tip))
            self.assertEqual(dragged.nodes["Body"].tip, tip)

    def test_retip_reports_what_it_changed(self):
        _b, doc = self._doc()
        snap = scene.Snapshot(doc)
        touched = set(snap.retip("Body", "Pad"))
        self.assertIn("Pad", touched)
        self.assertIn("Sketch001", touched)
        self.assertIn("Body", touched)

    def test_retip_on_a_body_that_is_not_there(self):
        _b, doc = self._doc()
        snap = scene.Snapshot(doc)
        self.assertEqual(list(snap.retip("Nope", "Pad")), [])


class PartNestingTests(unittest.TestCase):
    """Part workbench CSG.

    operands nest under the operation that uses them, sketches stay in the
    timeline, and the operation is chipped.
    """

    def _doc(self):
        sk = sketch("Sketch")
        extrude = FakeObject("Extrude", "Part::Extrusion", ["Part::Feature"])
        extrude.claims(sk).link("Base", sk)
        box = FakeObject("Box", "Part::Box", ["Part::Feature"])
        cut = FakeObject("Cut", "Part::Cut", ["Part::Feature"])
        cut.claims(box, extrude).link("Base", box).link("Tool", extrude)
        return scene.Snapshot(FakeDocument("Doc", [sk, extrude, box, cut]),
                              part_layout=scene.NESTED)

    def test_operands_stay_nested_under_the_boolean(self):
        snap = self._doc()
        self.assertEqual(snap.nodes["Cut"].children, ["Box", "Extrude"])
        self.assertFalse(snap.nodes["Box"].is_lifted)
        self.assertEqual(snap.nodes["Extrude"].parent, "Cut")

    def test_sketch_stays_in_the_timeline(self):
        snap = self._doc()
        self.assertEqual(snap.roots, ["Cut", "~Sketches"])
        self.assertEqual(snap.nodes["Extrude"].children, [])

    def test_the_operation_pins_a_chip_for_its_sketch(self):
        snap = self._doc()
        self.assertEqual(snap.nodes["Extrude"].pinned, {"Sketch"})
        self.assertEqual(snap.nodes["Cut"].pinned, set())
        self.assertEqual([n for n, _l, _p in snap.nodes["Sketch"].consumers],
                         ["Extrude"])


class ExpressionModelTests(unittest.TestCase):
    """Part models as flat step lists under their latest operation."""

    def _doc(self):
        sk = sketch("Sketch")
        extrude = FakeObject("Extrude", "Part::Extrusion", ["Part::Feature"])
        extrude.claims(sk).link("Base", sk)
        box = FakeObject("Box", "Part::Box", ["Part::Feature"])
        cut = FakeObject("Cut", "Part::Cut", ["Part::Feature"])
        cut.claims(box, extrude).link("Base", box).link("Tool", extrude)
        cyl = FakeObject("Cyl", "Part::Cylinder", ["Part::Feature"])
        fuse = FakeObject("Fuse", "Part::Fuse", ["Part::Feature"])
        fuse.claims(cut, cyl).link("Base", cut).link("Tool", cyl)
        lone = FakeObject("Lone", "Part::Box", ["Part::Feature"])
        return scene.Snapshot(FakeDocument(
            "Doc", [sk, extrude, box, cut, cyl, fuse, lone]))

    def test_one_root_per_model(self):
        self.assertEqual(self._doc().roots, ["Fuse", "Lone", "~Sketches"])

    def test_steps_are_flat_and_oldest_first(self):
        snap = self._doc()
        self.assertEqual(snap.nodes["Fuse"].children,
                         ["Extrude", "Box", "Cut", "Cyl"])
        self.assertEqual(snap.nodes["Fuse"].sources,
                         ["Sketch", "Extrude", "Box", "Cut", "Cyl"])
        self.assertEqual(snap.nodes["Cut"].children, [])
        self.assertTrue(snap.nodes["Fuse"].is_model)

    def test_every_reference_is_chipped(self):
        snap = self._doc()
        self.assertEqual(snap.nodes["Cut"].pinned, {"Box", "Extrude"})
        self.assertEqual(snap.nodes["Fuse"].pinned, {"Cut", "Cyl"})

    def test_an_input_created_later_still_comes_first(self):
        sk = sketch("Sketch")
        cut = FakeObject("Cut", "Part::Cut", ["Part::Feature"])
        box = FakeObject("Box", "Part::Box", ["Part::Feature"])
        fuse = FakeObject("Fuse", "Part::Fuse", ["Part::Feature"])
        late = FakeObject("Late", "Part::Box", ["Part::Feature"])
        cut.link("Base", box).link("Tool", late)
        fuse.link("Base", cut).link("Tool", sk)
        snap = scene.Snapshot(FakeDocument("Doc", [sk, cut, box, fuse, late]))
        order = snap.nodes["Fuse"].children
        self.assertLess(order.index("Late"), order.index("Cut"))

    def test_rolling_back_shows_what_was_newest(self):
        snap = self._doc()
        state = snap.model_state("Fuse", "Box")
        shown = {n for n, (_b, v) in state.items() if v}
        self.assertEqual(shown, {"Extrude", "Box"})
        self.assertFalse(state["Cut"][0])
        full = {n for n, (_b, v) in snap.model_state("Fuse", "Fuse").items()
                if v}
        self.assertEqual(full, {"Fuse"})

    def test_retip_marks_later_steps(self):
        snap = self._doc()
        snap.retip("Fuse", "Cut")
        self.assertTrue(snap.nodes["Cyl"].after_tip)
        self.assertTrue(snap.nodes["Fuse"].after_tip)
        self.assertFalse(snap.nodes["Cut"].after_tip)
        self.assertTrue(snap.nodes["Cut"].visible)

    def test_bodies_are_left_alone(self):
        b = body("Body")
        sk = sketch("Sketch")
        pad = feature("Pad")
        pad.link("Profile", sk)
        b.Group = [sk, pad]
        b.claims(sk, pad)
        snap = scene.Snapshot(FakeDocument("Doc", [b, sk, pad]))
        self.assertFalse(any(n.is_model for n in snap.nodes.values()))


def part(name):
    return FakeObject(name, "App::Part", ["App::Part"])


class CompartmentTests(unittest.TestCase):
    """Free sketches and datums collected into panel-only groups."""

    def test_sorted_by_label_number_aware(self):
        sketches = [sketch(n) for n in ("Sketch10", "Sketch2", "Base")]
        snap = scene.Snapshot(FakeDocument("Doc", sketches))
        self.assertEqual(snap.nodes["~Sketches"].children,
                         ["Base", "Sketch2", "Sketch10"])
        self.assertTrue(snap.nodes["~Sketches"].is_virtual)
        self.assertIn("~Sketches", snap.default_expansion())

    def test_datums_get_their_own_group_after_sketches(self):
        plane = FakeObject("Plane", "Part::DatumPlane", ["Part::Datum"])
        origin = FakeObject("X_Axis", "App::Line",
                            ["App::DatumElement", "App::OriginFeature"])
        snap = scene.Snapshot(
            FakeDocument("Doc", [plane, sketch("S"), origin]))
        self.assertEqual(snap.roots, ["X_Axis", "~Sketches", "~DatumObjects"])
        self.assertEqual(snap.nodes["~DatumObjects"].label, "Datum Objects")

    def test_an_app_part_gets_its_own(self):
        p = part("Part")
        sk = sketch("Inner")
        p.claims(sk)
        p.Group = [sk]
        snap = scene.Snapshot(FakeDocument("Doc", [p, sk, sketch("Outer")]))
        self.assertEqual(snap.nodes["Part"].children, ["~Sketches~Part"])
        self.assertEqual(snap.nodes["~Sketches~Part"].children, ["Inner"])
        self.assertEqual(snap.nodes["~Sketches"].children, ["Outer"])

    def test_body_sketches_stay_in_the_body(self):
        b = body("Body")
        sk = sketch("Sketch")
        b.claims(sk)
        b.Group = [sk]
        snap = scene.Snapshot(FakeDocument("Doc", [b, sk]))
        self.assertEqual(snap.nodes["Sketch"].parent, "Body")
        self.assertNotIn("~Sketches", snap.nodes)

    def test_a_users_own_group_is_respected(self):
        g = group("Mine")
        sk = sketch("Sketch")
        g.claims(sk)
        g.link("Group", [sk])
        snap = scene.Snapshot(FakeDocument("Doc", [g, sk]))
        self.assertEqual(snap.nodes["Sketch"].parent, "Mine")

    def test_rolling_back_still_shows_a_filed_sketch(self):
        sk = sketch("Sketch")
        ext = FakeObject("Extrude", "Part::Extrusion", ["Part::Feature"])
        ext.link("Base", sk)
        box = FakeObject("Box", "Part::Box", ["Part::Feature"])
        cut = FakeObject("Cut", "Part::Cut", ["Part::Feature"])
        cut.link("Base", box).link("Tool", ext)
        snap = scene.Snapshot(FakeDocument("Doc", [sk, box, ext, cut]))
        self.assertEqual(snap.nodes["Cut"].stack, ["Box", "Extrude"])
        state = snap.model_state("Cut", "Box")
        self.assertTrue(state["Sketch"][1])
        self.assertEqual(snap.nodes["Extrude"].pinned, {"Sketch"})


class BinderTests(unittest.TestCase):

    def test_a_free_binder_nests_in_the_model_that_first_reads_it(self):
        binder = FakeObject("Binder", "PartDesign::SubShapeBinder",
                            ["PartDesign::SubShapeBinder"])
        box = FakeObject("Box", "Part::Box", ["Part::Feature"])
        cut = FakeObject("Cut", "Part::Cut", ["Part::Feature"])
        cut.link("Base", box).link("Tool", binder)
        fuse = FakeObject("Fuse", "Part::Fuse", ["Part::Feature"])
        other = FakeObject("Other", "Part::Box", ["Part::Feature"])
        fuse.link("Base", other).link("Tool", binder)
        snap = scene.Snapshot(FakeDocument(
            "Doc", [binder, box, cut, other, fuse]))
        self.assertEqual(snap.nodes["Binder"].parent, "Cut")
        self.assertIn("Binder", snap.nodes["Cut"].stack)
        self.assertIn("Binder", snap.nodes["Fuse"].pinned)

    def test_a_binder_in_a_body_stays_there(self):
        b = body("Body")
        binder = FakeObject("Binder", "PartDesign::ShapeBinder",
                            ["PartDesign::ShapeBinder"])
        b.claims(binder)
        b.Group = [binder]
        snap = scene.Snapshot(FakeDocument("Doc", [b, binder]))
        self.assertEqual(snap.nodes["Binder"].parent, "Body")


if __name__ == "__main__":
    unittest.main(verbosity=2)
