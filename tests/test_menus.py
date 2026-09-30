"""The context menu's definitions: reading, checking, merging, resolving.

Run with: python3 tests/test_menus.py
"""

from __future__ import annotations

import sys
import tomllib
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# The package imports FreeCAD for its console; the definitions do not.
App = types.ModuleType("FreeCAD")
App.Console = types.SimpleNamespace(PrintError=lambda _m: None,
                                    PrintWarning=lambda _m: None,
                                    PrintMessage=lambda _m: None)
sys.modules.setdefault("FreeCAD", App)
sys.modules.setdefault("FreeCADGui", types.ModuleType("FreeCADGui"))

from freecad.nxt.menus import definitions as d  # noqa: E402

DEFAULT = ROOT / "freecad" / "nxt" / "resources" / "menus" / "default.toml"
BAR = ["nxt:isolate", "Std_ViewFitSelection", "Std_SetAppearance",
       "nxt:inspector"]


def obj(*types: str, flags: tuple[str, ...] = (), in_body: bool = False,
        proxy: str = "") -> d.ObjectFacts:
    return d.ObjectFacts(types=types, proxy_module=proxy, in_body=in_body,
                         flags=frozenset(flags))


SKETCH = ("Sketcher::SketchObject", "Part::Part2DObject", "Part::Feature")
POCKET = ("PartDesign::Pocket", "PartDesign::ProfileBased",
          "PartDesign::FeatureAddSub", "PartDesign::Feature",
          "Part::Feature")
SHAPED = ("has_shape", "shown_in_3d", "has_inputs")


def section(menu: d.Resolved, name: str) -> list[str]:
    return [i.command for n, items in menu.sections if n == name
            for i in items]


def more(menu: d.Resolved, name: str) -> list[str]:
    return [i.command for n, items in menu.more if n == name for i in items]


class DefaultFileTests(unittest.TestCase):

    def setUp(self) -> None:
        self.defs = d.load(DEFAULT)

    def resolve(self, *objects: d.ObjectFacts) -> d.Resolved:
        return d.resolve(self.defs, list(objects))

    def test_the_file_reads_cleanly(self) -> None:
        self.assertEqual(self.defs.errors, [])
        self.assertEqual([i.command for i in self.defs.bar], BAR)

    def test_a_sketch_with_solver_findings(self) -> None:
        menu = self.resolve(obj(*SKETCH, flags=SHAPED + ("solver_issues",
                                                         "has_dependents")))
        self.assertEqual(menu.lead.command, "edit:default")
        self.assertEqual([i.command for i in menu.state],
                         ["nxt:show_solver_issues"])
        self.assertIn("Sketcher_MapSketch", more(menu, "Sketcher"))
        self.assertIn("nxt:select_consumers", section(menu, "Relations"))
        self.assertIn("Sketcher_ValidateSketch", more(menu, "Sketcher"))
        self.assertEqual(menu.delete.command, "Std_Delete")
        self.assertEqual(menu.dimmed, set())

    def test_a_failed_feature_leads_with_the_failure(self) -> None:
        menu = self.resolve(obj(*POCKET, flags=SHAPED + ("failed",),
                                in_body=True))
        self.assertEqual(menu.lead.command, "edit:default")
        self.assertEqual([i.command for i in menu.state],
                         ["nxt:reveal_failure", "nxt:recompute_object"])
        # Placed once: the state row, not again under Model.
        self.assertNotIn("nxt:recompute_object", section(menu, "Model"))

    def test_the_rollback_items_follow_the_tip(self) -> None:
        before = self.resolve(obj(*POCKET, flags=SHAPED, in_body=True))
        self.assertIn("nxt:set_tip", section(before, "Model"))
        self.assertNotIn("nxt:roll_forward", section(before, "Model"))
        past = self.resolve(obj(*POCKET, flags=SHAPED + ("past_tip",),
                                in_body=True))
        self.assertIn("nxt:roll_forward", section(past, "Model"))
        self.assertNotIn("nxt:set_tip", section(past, "Model"))
        tip = self.resolve(obj(*POCKET, flags=SHAPED + ("is_tip",),
                               in_body=True))
        self.assertNotIn("nxt:set_tip", section(tip, "Model"))

    def test_several_objects_drop_single_object_actions(self) -> None:
        feature = obj(*POCKET, flags=SHAPED, in_body=True)
        menu = self.resolve(feature, feature, feature)
        self.assertIsNone(menu.lead)            # nothing to edit as one
        self.assertNotIn("nxt:rename", section(menu, "Organize"))
        self.assertNotIn("nxt:set_tip", section(menu, "Model"))
        self.assertIn("PartDesign_MoveFeature", section(menu, "Organize"))
        self.assertNotIn("edit:color", more(menu, "Part Design"))

    def test_the_clipboard_is_under_more(self) -> None:
        menu = self.resolve(obj(*SKETCH, flags=SHAPED))
        self.assertEqual(more(menu, "Clipboard"),
                         ["Std_Cut", "Std_Copy", "Std_Paste"])
        for name, _items in menu.sections:
            self.assertNotIn("Std_Copy", section(menu, name))

    def test_show_and_hide_selection_are_gone(self) -> None:
        menu = self.resolve(obj(*SKETCH, flags=SHAPED))
        self.assertNotIn("Std_ShowSelection", menu.commands())
        self.assertNotIn("Std_HideSelection", menu.commands())

    def test_draft_utilities_only_on_draft_objects(self) -> None:
        wire = obj("Part::FeaturePython", "Part::Feature", flags=SHAPED,
                   proxy="draftobjects.wire")
        self.assertIn("Draft_SetStyle", more(self.resolve(wire), "Draft"))
        pocket = obj(*POCKET, flags=SHAPED, in_body=True)
        self.assertEqual(more(self.resolve(pocket), "Draft"), [])

    def test_the_bar_dims_rather_than_shrinks(self) -> None:
        sheet = obj("Spreadsheet::Sheet")
        menu = self.resolve(sheet)
        self.assertEqual([i.command for i in menu.bar], BAR)
        self.assertEqual(menu.dimmed, {"nxt:isolate", "Std_ViewFitSelection",
                                       "Std_SetAppearance"})
        self.assertEqual(menu.lead.label, "Show spreadsheet")

    def test_a_body_leads_with_make_active(self) -> None:
        body = obj("PartDesign::Body", "Part::BodyBase", "Part::Feature",
                   flags=SHAPED)
        menu = self.resolve(body)
        self.assertEqual(menu.lead.command, "nxt:make_active")
        self.assertIn("PartDesign_NewSketch", section(menu, "Model"))
        self.assertNotIn("edit:default", menu.commands())

    def test_a_sketch_in_a_body_can_be_moved_like_a_feature(self) -> None:
        inside = self.resolve(obj(*SKETCH, flags=SHAPED, in_body=True))
        self.assertIn("PartDesign_MoveFeature", section(inside, "Organize"))
        loose = self.resolve(obj(*SKETCH, flags=SHAPED))
        self.assertNotIn("PartDesign_MoveFeature", section(loose, "Organize"))

    def test_attachable_objects_offer_the_attachment_editor(self) -> None:
        menu = self.resolve(obj(*SKETCH, flags=SHAPED + ("attachable",)))
        self.assertIn("nxt:edit_attachment", section(menu, "Model"))
        plain = self.resolve(obj(*SKETCH, flags=SHAPED))
        self.assertNotIn("nxt:edit_attachment", section(plain, "Model"))

    def test_replaced_commands_are_dropped_not_carried_over(self) -> None:
        menu = self.resolve(obj(*POCKET, flags=SHAPED, in_body=True))
        self.assertTrue({"PartDesign_MoveTip", "Std_ShowSelection",
                         "Std_HideSelection", "Std_Properties"}
                        <= menu.dropped)
        sketch = self.resolve(obj(*SKETCH, flags=SHAPED))
        self.assertNotIn("PartDesign_MoveTip", sketch.dropped)

    def test_material_sits_with_the_display_commands(self) -> None:
        menu = self.resolve(obj(*SKETCH, flags=SHAPED))
        self.assertEqual(more(menu, "Display")[0], "Std_SetMaterial")

    def test_sections_keep_their_order(self) -> None:
        menu = self.resolve(obj(*SKETCH, flags=SHAPED + ("has_dependents",)))
        names = [n for n, _items in menu.sections]
        self.assertEqual(names, [n for n in d.SECTIONS if n in names])


class LabelTests(unittest.TestCase):

    def test_every_label_is_listed_for_translation(self) -> None:
        from freecad.nxt.menus import labels
        data = tomllib.loads(DEFAULT.read_text(encoding="utf-8"))
        found: set[str] = set()
        commands: set[str] = set()

        def walk(value: object) -> None:
            if isinstance(value, dict):
                if "label" in value:
                    found.add(str(value["label"]))
                if "command" in value:
                    commands.add(str(value["command"]))
                for inner in value.values():
                    walk(inner)
            elif isinstance(value, list):
                for inner in value:
                    walk(inner)
            elif isinstance(value, str) and value.startswith("nxt:"):
                commands.add(value)

        walk(data)
        self.assertEqual(found - set(labels.OVERRIDES), set())
        nxt = {c for c in commands if c.startswith("nxt:")}
        self.assertEqual(nxt - set(labels.ACTIONS), set())


class PresentTests(unittest.TestCase):

    def lookup(self, name: str) -> object:
        from freecad.nxt.menus import present
        if name.startswith("Sketcher_"):
            return None                     # Sketcher not installed
        return present.CommandInfo(label=name.split("_", 1)[1],
                                   active=name != "Std_Paste", icon=name)

    def show(self, *objects: d.ObjectFacts, shown: bool = True) -> dict:
        from freecad.nxt.menus import present
        resolved = d.resolve(d.load(DEFAULT), list(objects))
        return present.present(
            resolved, present.Subject(title="Sketch", any_shown=shown),
            self.lookup)

    def test_visibility_is_the_eye_not_the_bar(self) -> None:
        bar = self.show(obj(*SKETCH, flags=SHAPED))["bar"]
        self.assertNotIn("Std_ToggleVisibility", [b["command"] for b in bar])

    def test_isolate_says_exit_while_isolating(self) -> None:
        from freecad.nxt.menus import present
        sketch = obj(*SKETCH, flags=SHAPED)
        self.assertEqual(self.show(sketch)["bar"][0]["short"], "Isolate")
        saved = present._isolating
        present._isolating = lambda: True  # type: ignore[assignment]
        try:
            self.assertEqual(self.show(sketch)["bar"][0]["short"],
                             "Exit isolate")
        finally:
            present._isolating = saved  # type: ignore[assignment]

    def test_edit_is_named_for_the_object(self) -> None:
        menu = self.show(obj(*SKETCH, flags=SHAPED))
        self.assertEqual(menu["lead"]["label"], "Edit Sketch")

    def test_unregistered_commands_are_left_out(self) -> None:
        menu = self.show(obj(*SKETCH, flags=SHAPED))
        names = [g["name"] for g in menu["more"]]
        self.assertNotIn("Sketcher", names)     # every entry unregistered

    def test_inactive_commands_stay_disabled(self) -> None:
        menu = self.show(obj(*SKETCH, flags=SHAPED))
        clipboard = next(g for g in menu["more"] if g["name"] == "Clipboard")
        paste = next(i for i in clipboard["items"]
                     if i["command"] == "Std_Paste")
        self.assertFalse(paste["enabled"])

    def test_freecads_menu_closes_more(self) -> None:
        menu = self.show(obj(*SKETCH, flags=SHAPED))
        self.assertEqual(menu["more"][-1]["items"][0]["command"],
                         "nxt:native_menu")

    def test_every_nxt_action_has_an_implementation(self) -> None:
        from freecad.nxt.menus import labels
        source = (ROOT / "freecad" / "nxt" / "tree"
                  / "menu_actions.py").read_text(encoding="utf-8")
        for command in labels.ACTIONS:
            if command == "nxt:native_menu":
                continue
            self.assertIn('"%s":' % command[4:], source, command)


class SubmenuTests(unittest.TestCase):

    def test_expressions_are_a_submenu_of_nxt_actions(self) -> None:
        menu = d.resolve(d.load(DEFAULT), [obj(*SKETCH, flags=SHAPED)])
        inspect = [i for n, items in menu.sections if n == "Inspect"
                   for i in items]
        group = inspect[0]
        self.assertEqual((group.command, group.label),
                         (d.SUBMENU, "Expressions"))
        self.assertEqual([i.command for i in group.items],
                         ["nxt:expressions_copy_selected",
                          "nxt:expressions_copy_document",
                          "nxt:expressions_copy_all",
                          "nxt:expressions_paste"])
        self.assertIn("nxt:expressions_paste", menu.commands())
        self.assertIn("Std_Expressions", menu.dropped)

    def test_a_submenu_with_nothing_left_goes(self) -> None:
        defs = d.parse(tomllib.loads("""
            [[menu]]
            [menu.section]
            Model = [{ label = "Tools", submenu = [
                { command = "A_B", flags = ["failed"] }] }]
        """.replace("\n                ", " ")), "x.toml")
        self.assertEqual(defs.errors, [])
        menu = d.resolve(defs, [obj("X")])
        self.assertEqual(menu.sections, [])

    def test_the_clipboard_format_matches_freecads(self) -> None:
        """What FreeCAD's own copy writes is what Nxt's paste reads."""
        from freecad.nxt.tree import menu_actions
        text = ("##@@ .Length Unnamed#Pad.ExpressionEngine (Pad)\n"
                "##@@\nSketch.Constraints.width * 2\n\n"
                "##@@ Placement.Base.x Unnamed#Box.ExpressionEngine (Box)\n"
                "##@@a note\nPad.Length\n\n")
        found = list(menu_actions._EXPRESSION.finditer(text))
        self.assertEqual([m.group(1, 2, 3, 4) for m in found],
                         [(".Length", "Unnamed", "Pad", "ExpressionEngine"),
                          ("Placement.Base.x", "Unnamed", "Box",
                           "ExpressionEngine")])

    def test_std_expressions_is_never_offered_or_run(self) -> None:
        from freecad.nxt.menus import runner
        self.assertIsNone(runner.lookup("Std_Expressions"))
        self.assertFalse(runner.run_command("Std_Expressions"))


class CheckingTests(unittest.TestCase):

    def parse(self, text: str) -> d.Definitions:
        return d.parse(tomllib.loads(text), "addon.toml")

    def test_a_bad_entry_is_reported_and_skipped(self) -> None:
        defs = self.parse("""
            [[menu]]
            id = "screw"
            when = { type = "Fasteners::*" }
            lead = "edit:bogus"
            [menu.section]
            Model = ["Fasteners_Flip", { label = "no command" },
                     { command = "Fasteners_Move", flags = ["shiny"] }]
        """)
        self.assertEqual(len(defs.errors), 3, defs.errors)
        self.assertTrue(all(e.startswith("addon.toml, menu screw")
                            for e in defs.errors))
        menu = defs.menus[0]
        self.assertIsNone(menu.lead)
        self.assertEqual([i.command for i in menu.sections["Model"]],
                         ["Fasteners_Flip"])

    def test_an_unreadable_condition_drops_its_menu(self) -> None:
        defs = self.parse("""
            [[menu]]
            id = "odd"
            when = { colour = "red" }
            lead = "edit:default"
        """)
        self.assertEqual(defs.menus, [])
        self.assertIn("unknown condition 'colour'", defs.errors[0])

    def test_a_file_that_is_not_toml(self) -> None:
        path = Path(__file__).with_name("_broken_menu.toml")
        path.write_text("[[menu]\n", encoding="utf-8")
        try:
            defs = d.load(path)
        finally:
            path.unlink()
        self.assertEqual(defs.menus, [])
        self.assertEqual(len(defs.errors), 1)


class MergingTests(unittest.TestCase):

    def test_an_addon_places_hides_and_adds_a_section(self) -> None:
        defs = d.load(DEFAULT)
        defs.extend(d.parse(tomllib.loads("""
            [bar]
            items = ["Addon_Ignored"]

            [[menu]]
            id = "fasteners"
            when = { type = "Part::Feature" }
            hide = ["Std_Copy"]
            [menu.section]
            Organize = [{ command = "Fasteners_Flip", after = "nxt:rename" }]
            Fasteners = ["Fasteners_Resize"]
        """), "fasteners.toml"))
        self.assertEqual(defs.errors, [])
        menu = d.resolve(defs, [obj(*SKETCH, flags=SHAPED)])
        self.assertEqual([i.command for i in menu.bar], BAR)
        organize = section(menu, "Organize")
        self.assertEqual(organize.index("Fasteners_Flip"),
                         organize.index("nxt:rename") + 1)
        self.assertEqual([n for n, _i in menu.sections][-1], "Fasteners")
        self.assertNotIn("Std_Copy", menu.commands())
        self.assertTrue(any("Std_Copy: hidden" in t for t in menu.trace))

    def test_count_and_negated_flags(self) -> None:
        cond = d.Condition(count="2+", absent=frozenset({"failed"}))
        good = obj("X")
        bad = obj("X", flags=("failed",))
        self.assertFalse(cond.holds([good]))
        self.assertTrue(cond.holds([good, good]))
        self.assertFalse(cond.holds([good, bad]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
