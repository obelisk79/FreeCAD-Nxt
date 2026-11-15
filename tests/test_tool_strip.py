"""The tool strip's Python half: reading, covering and acting on toolbars.

Builds a main window with toolbars as FreeCAD leaves them: global and
workbench bars, a lingering hidden one, a dropdown command group, a
widget button with a menu, a workbench selector and a widget Nxt cannot
show.

Run with: QT_QPA_PLATFORM=offscreen python3 tests/test_tool_strip.py
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import fakes  # noqa: E402

App, Gui = fakes.install()

from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

from freecad.nxt.toolbars import (  # noqa: E402
    catalog,
    layouts,
    models,
    source,
)
from freecad.nxt.toolbars.bridge import ToolStripBridge  # noqa: E402
from freecad.nxt.toolbars.hider import ToolbarHider  # noqa: E402
from freecad.nxt.toolbars.source import Kind  # noqa: E402

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
OWN = ("NxtToolStrip",)
WORKBENCH = "PartDesignWorkbench"
TOP = QtCore.Qt.ToolBarArea.TopToolBarArea
SPLIT = QtWidgets.QToolButton.ToolButtonPopupMode.MenuButtonPopup


class FakeCommand:
    """A FreeCAD command: its info, and its QActions if any were made."""

    def __init__(self, key: str, text: str) -> None:
        self.key, self.text = key, text
        self.actions: list[QtGui.QAction] = []

    def getInfo(self) -> dict[str, str]:
        return {"menuText": self.text, "toolTip": self.text + " tip",
                "pixmap": self.key}

    def getAction(self) -> list[QtGui.QAction]:
        return list(self.actions)


class FakeWorkbench:
    def __init__(self, label: str, toolbars: dict[str, list[str]]) -> None:
        self.MenuText = label
        self._toolbars = toolbars

    def getToolbarItems(self) -> dict[str, list[str]]:
        return self._toolbars


COMMANDS = {key: FakeCommand(key, text) for key, text in (
    ("Std_New", "&New"), ("PartDesign_Pad", "Pad"),
    ("PartDesign_Pocket", "Pocket"), ("Sketcher_CreateCircle", "Circle"),
    ("Std_DlgParameter", "E&dit Parameters"))}
WORKBENCHES = {
    "PartDesignWorkbench": FakeWorkbench("Part Design", {
        "File": ["Std_New"], "Features": ["PartDesign_Pad",
                                          "PartDesign_Pocket"]}),
    "SketcherWorkbench": FakeWorkbench("Sketcher", {
        "File": ["Std_New"], "Geometry": ["Sketcher_CreateCircle"]}),
    "StartWorkbench": FakeWorkbench("Start", {}),
}
GROUP = "PartDesign_CompPrimitiveAdditive"
COMMANDS[GROUP] = FakeCommand(GROUP, "Additive Primitive")
for _name, _text in (("PartDesign_AdditiveBox", "Additive Box"),
                     ("PartDesign_AdditiveCylinder", "Additive Cylinder")):
    _member = QtGui.QAction(_text)
    _member.setObjectName(_name)
    COMMANDS[GROUP].actions.append(_member)
RAN: list[str] = []
Gui.listCommands = lambda: list(COMMANDS)
Gui.Command = type("Command", (), {"get": staticmethod(COMMANDS.get)})
Gui.listWorkbenches = lambda: dict(WORKBENCHES)
Gui.runCommand = RAN.append


def settle() -> None:
    for _ in range(3):
        APP.processEvents()


class Window:
    """A main window with toolbars laid out as FreeCAD leaves them."""

    def __init__(self) -> None:
        self.main = QtWidgets.QMainWindow()
        self.main.setCentralWidget(QtWidgets.QWidget())
        self.fired: list[str] = []
        file_bar = self.bar("File")
        self.new = self.command(file_bar, "&New")
        self.command(file_bar, "Open")
        file_bar.addSeparator()
        self.command(file_bar, "Save")
        self.command(file_bar, "Hidden").setVisible(False)
        stale = self.bar("Sketcher")
        self.command(stale, "Line")
        stale.hide()
        part = self.bar("Part")
        self.pad = self.command(part, "Pad")
        self.pad.setCheckable(True)
        self.fillet = self.command(part, "Fillet")
        self.group_menu = QtWidgets.QMenu(part)
        self.group_menu.addAction("Chamfer")
        group_button = part.widgetForAction(self.fillet)
        group_button.setMenu(self.group_menu)
        group_button.setPopupMode(SPLIT)
        tray = self.bar("Tray")
        self.layer = QtWidgets.QPushButton("Layer 1")
        self.layer_menu = QtWidgets.QMenu(self.layer)
        self.layer.setMenu(self.layer_menu)
        self.widget(tray, self.layer)
        self.plain = QtWidgets.QPushButton("Style")
        self.plain.clicked.connect(lambda: self.fired.append("Style"))
        self.widget(tray, self.plain)
        self.widget(tray, QtWidgets.QSlider())
        selector = self.bar("Workbench")
        holder = QtWidgets.QWidget()
        self.tabs = QtWidgets.QTabBar(holder)
        for name in ("Part Design", "Sketcher"):
            self.tabs.addTab(name)
        self.widget(selector, holder)
        self.own = self.bar(OWN[0])
        self.own.addAction("Strip")
        self.main.show()
        settle()

    def bar(self, name: str) -> QtWidgets.QToolBar:
        toolbar = QtWidgets.QToolBar(name, self.main)
        toolbar.setObjectName(name)
        self.main.addToolBar(TOP, toolbar)
        return toolbar

    def command(self, bar: QtWidgets.QToolBar, text: str) -> QtGui.QAction:
        action = QtGui.QAction(text, self.main)
        action.triggered.connect(lambda: self.fired.append(text))
        bar.addAction(action)
        return action

    def widget(self, bar: QtWidgets.QToolBar,
               widget: QtWidgets.QWidget) -> None:
        action = QtWidgets.QWidgetAction(bar)
        action.setDefaultWidget(widget)
        bar.addAction(action)

    def close(self) -> None:
        self.main.close()
        self.main.deleteLater()
        settle()


class Reading(unittest.TestCase):
    def setUp(self) -> None:
        self.window = Window()
        self.entries, self.unsupported = source.read(self.window.main, OWN)

    def tearDown(self) -> None:
        self.window.close()

    def labels(self) -> list[str]:
        return ["|" if e.kind is Kind.SEPARATOR
                else e.action.text() if e.kind is Kind.COMMAND
                else e.kind.value for e in self.entries]

    def test_shown_toolbars_flattened_with_a_separator_between(self) -> None:
        self.assertEqual(self.labels(), [
            "&New", "Open", "|", "Save", "|", "Pad", "Fillet", "|",
            "button", "button", "|", "choice"])

    def test_lingering_toolbars_and_hidden_actions_left_out(self) -> None:
        texts = self.labels()
        self.assertNotIn("Line", texts)
        self.assertNotIn("Hidden", texts)

    def test_own_toolbar_left_out(self) -> None:
        self.assertNotIn("Strip", self.labels())

    def test_dropdown_group_keeps_its_button(self) -> None:
        fillet = self.entries[self.labels().index("Fillet")]
        self.assertIs(fillet.widget.menu(), self.window.group_menu)

    def test_selector_proxied_by_its_tab_bar(self) -> None:
        self.assertIs(self.entries[-1].widget, self.window.tabs)

    def test_unshowable_widget_reported(self) -> None:
        self.assertEqual(self.unsupported, ["QSlider"])

    def test_separators_tidied(self) -> None:
        sep = source.SEPARATOR
        command = source.Entry(Kind.COMMAND)
        self.assertEqual(source.tidy([sep, command, sep, sep, command, sep]),
                         [command, sep, command])


class Hiding(unittest.TestCase):
    def setUp(self) -> None:
        self.window = Window()
        self.hider = ToolbarHider(self.window.main, OWN)
        self.changes: list[bool] = []
        self.hider.toolbarsChanged.connect(lambda: self.changes.append(True))
        self.hider.install()
        settle()

    def tearDown(self) -> None:
        self.hider.remove()
        self.window.close()

    def bars(self) -> list[QtWidgets.QToolBar]:
        return [b for b in self.window.main.findChildren(QtWidgets.QToolBar)
                if b is not self.window.own]

    def test_covered_not_hidden(self) -> None:
        for bar in self.bars():
            self.assertEqual(bar.maximumSize(), QtCore.QSize(0, 0))
        part = self.window.main.findChild(QtWidgets.QToolBar, "Part")
        self.assertFalse(part.isHidden())
        self.assertTrue(part.toggleViewAction().isChecked())

    def test_own_toolbar_untouched(self) -> None:
        self.assertNotEqual(self.window.own.maximumSize(),
                            QtCore.QSize(0, 0))

    def test_toolbar_added_later_is_covered(self) -> None:
        late = self.window.bar("Late")
        settle()
        self.assertEqual(late.maximumSize(), QtCore.QSize(0, 0))
        self.assertTrue(self.changes)

    def test_changed_actions_announced(self) -> None:
        self.changes.clear()
        self.window.command(self.bars()[0], "Extra")
        self.assertTrue(self.changes)

    def test_removed_cover_restores_sizes(self) -> None:
        self.hider.remove()
        for bar in self.bars():
            self.assertNotEqual(bar.maximumSize(), QtCore.QSize(0, 0))


class Acting(unittest.TestCase):
    def setUp(self) -> None:
        self.window = Window()
        self.global_point = QtCore.QPoint(5, 5)
        layouts.save(WORKBENCH, None)
        self.bridge = ToolStripBridge(self.window.main, OWN,
                                      lambda _p: self.global_point,
                                      lambda: WORKBENCH)
        self.model = self.bridge.model
        self.bridge.rebuild()

    def tearDown(self) -> None:
        self.bridge.stop()
        self.window.close()

    def row_of(self, text: str) -> int:
        role = self.role("text")
        for row in range(self.model.rowCount()):
            if self.model.data(self.model.index(row), role) == text:
                return row
        raise AssertionError(text)

    def role(self, name: str) -> int:
        names = {v.data().decode(): k
                 for k, v in self.model.roleNames().items()}
        return names[name]

    def value(self, row: int, name: str) -> object:
        return self.model.data(self.model.index(row), self.role(name))

    def test_rows_describe_commands(self) -> None:
        row = self.row_of("New")
        self.assertEqual(self.value(row, "kind"), "command")
        self.assertEqual(self.value(self.row_of("Fillet"), "dropdown"),
                         models.SPLIT)
        self.assertEqual(self.value(self.row_of("Layer 1"), "dropdown"),
                         models.INSTANT)

    def test_checked_state_follows_the_action(self) -> None:
        row = self.row_of("Pad")
        changed: list[int] = []
        self.model.dataChanged.connect(lambda a, _b: changed.append(a.row()))
        self.window.pad.setChecked(True)
        self.assertEqual(changed, [row])
        self.assertTrue(self.value(row, "checked"))

    def test_same_toolbars_no_reset(self) -> None:
        resets: list[bool] = []
        self.model.modelReset.connect(lambda: resets.append(True))
        self.bridge.rebuild()
        self.assertEqual(resets, [])

    def test_activate_runs_enabled_commands_only(self) -> None:
        self.bridge.activate(self.row_of("New"), 0.0, 0.0)
        self.window.new.setEnabled(False)
        self.bridge.activate(self.row_of("New"), 0.0, 0.0)
        self.assertEqual(self.window.fired, ["&New"])

    def test_activate_clicks_a_proxied_button(self) -> None:
        self.bridge.activate(self.row_of("Style"), 0.0, 0.0)
        self.assertEqual(self.window.fired, ["Style"])

    def test_menu_a_button_opens_itself_lands_at_the_item(self) -> None:
        menu = QtWidgets.QMenu()
        menu.addAction("Group")
        self.window.plain.clicked.connect(
            lambda: menu.popup(QtCore.QPoint(0, 0)))
        self.bridge.activate(self.row_of("Style"), 3.0, 4.0)
        self.assertEqual(menu.pos(), self.global_point)
        menu.close()

    def test_dropdown_opens_its_menu_at_the_item(self) -> None:
        with mock.patch.object(QtWidgets.QMenu, "popup") as popup:
            self.bridge.openMenu(self.row_of("Fillet"), 3.0, 4.0)
        popup.assert_called_once_with(self.global_point)

    def test_choose_switches_the_selector(self) -> None:
        row = self.model.rowCount() - 1
        self.bridge.choose(row, 1)
        self.assertEqual(self.window.tabs.currentIndex(), 1)
        self.assertEqual(self.value(row, "current"), 1)

    def test_mnemonics_dropped_from_labels(self) -> None:
        self.assertEqual(models.plain("&Save && Close"), "Save & Close")


def entry(key: str) -> source.Entry:
    return source.Entry(Kind.COMMAND, key=key)


def keys(entries: list[source.Entry]) -> list[str]:
    return ["|" if e.kind is Kind.SEPARATOR else e.key for e in entries]


class Layouts(unittest.TestCase):
    def setUp(self) -> None:
        self.live = [entry("New"), entry("Open"), source.SEPARATOR,
                     entry("Pad"), entry("Pocket")]
        layouts.save(WORKBENCH, None)

    def test_no_layout_keeps_freecads_order(self) -> None:
        self.assertEqual(keys(layouts.arrange(self.live, None)[0]),
                         ["New", "Open", "|", "Pad", "Pocket"])

    def test_saved_order_applied(self) -> None:
        layout = layouts.Layout(["Pad", "|", "New"], ["Open", "Pocket"])
        self.assertEqual(keys(layouts.arrange(self.live, layout)[0]),
                         ["Pad", "|", "New"])

    def test_unmentioned_items_appended_after_a_separator(self) -> None:
        layout = layouts.Layout(["Pad", "New"], ["Open"])
        self.assertEqual(keys(layouts.arrange(self.live, layout)[0]),
                         ["Pad", "New", "|", "Pocket"])

    def test_items_no_longer_offered_skipped(self) -> None:
        layout = layouts.Layout(["Gone", "Pad", "|", "Open"], [])
        arranged = keys(layouts.arrange(self.live, layout)[0])
        self.assertNotIn("Gone", arranged)

    def test_capture_counts_what_was_left_out_as_removed(self) -> None:
        shown = [self.live[3], source.SEPARATOR, self.live[0]]
        layout = layouts.capture(shown, self.live,
                                 layouts.Layout([], ["Elsewhere"]))
        self.assertEqual(layout.order, ["Pad", "|", "New"])
        self.assertEqual(layout.removed, ["Elsewhere", "Open", "Pocket"])

    def test_saved_layouts_round_trip(self) -> None:
        layouts.save(WORKBENCH, layouts.Layout(["Pad"], ["New"]))
        self.assertEqual(layouts.load(WORKBENCH),
                         layouts.Layout(["Pad"], ["New"]))
        layouts.save(WORKBENCH, None)
        self.assertIsNone(layouts.load(WORKBENCH))

    def test_unreadable_setting_ignored(self) -> None:
        layouts.settings.put(layouts.SETTING, "{not json")
        self.assertEqual(layouts.load_all(), {})
        layouts.save(WORKBENCH, None)


class Editing(Acting):
    def texts(self) -> list[str]:
        role = self.role("text")
        return [self.model.data(self.model.index(r), role) or "|"
                for r in range(self.model.rowCount())]

    def test_drag_saves_the_new_order(self) -> None:
        self.bridge.setEditing(True)
        self.bridge.beginDrag()
        self.bridge.move(self.row_of("Save"), 0)
        self.bridge.endDrag(0, False)
        self.assertEqual(layouts.load(WORKBENCH).order[0], "Save")
        self.bridge.rebuild()
        self.assertEqual(self.texts()[0], "Save")

    def test_drop_outside_removes_and_remembers(self) -> None:
        row = self.row_of("Open")
        self.bridge.beginDrag()
        self.bridge.endDrag(row, True)
        self.assertNotIn("Open", self.texts())
        self.bridge.rebuild()
        self.assertNotIn("Open", self.texts())

    def test_remove_button_removes(self) -> None:
        self.bridge.removeItem(self.row_of("Pad"))
        self.assertNotIn("Pad", self.texts())

    def test_reset_brings_back_freecads_toolbars(self) -> None:
        self.bridge.removeItem(self.row_of("Pad"))
        self.bridge.resetLayout()
        self.assertIn("Pad", self.texts())
        self.assertIsNone(layouts.load(WORKBENCH))

    def test_commands_do_not_run_while_editing(self) -> None:
        self.bridge.setEditing(True)
        self.bridge.activate(self.row_of("New"), 0.0, 0.0)
        self.assertEqual(self.window.fired, [])

    def test_no_rebuild_mid_drag(self) -> None:
        self.bridge.beginDrag()
        self.bridge.move(self.row_of("Save"), 0)
        self.bridge.rebuild()
        self.assertEqual(self.texts()[0], "Save")
        self.bridge.endDrag(0, False)

    def test_moved_row_still_follows_its_action(self) -> None:
        self.bridge.move(self.row_of("Pad"), 0)
        self.window.pad.setChecked(True)
        self.assertTrue(self.value(0, "checked"))


class Catalog(unittest.TestCase):
    def setUp(self) -> None:
        self.commands, self.filters = catalog.read()

    def keys(self, query: str, group: str = catalog.ALL) -> list[str]:
        return [c.key for c in catalog.search(self.commands, query, group)]

    def test_letters_in_order_match(self) -> None:
        self.assertIsNotNone(catalog.score("pdpad", "Pad Part Design Pad"))
        self.assertIsNone(catalog.score("dap", "Pad"))

    def test_word_starts_rank_first(self) -> None:
        self.assertEqual(self.keys("pa")[0], "PartDesign_Pad")
        self.assertEqual(self.keys("circ"), ["Sketcher_CreateCircle"])

    def test_empty_query_lists_by_name(self) -> None:
        self.assertEqual(self.keys("")[:2],
                         ["PartDesign_CompPrimitiveAdditive",
                          "Sketcher_CreateCircle"])

    def test_filters_follow_the_workbenches(self) -> None:
        self.assertEqual([f[1] for f in self.filters],
                         ["All", "Global", "Part Design", "Sketcher"])
        self.assertEqual(self.keys("", "SketcherWorkbench"),
                         ["Sketcher_CreateCircle", "Std_New"])

    def test_global_is_what_every_workbench_shows(self) -> None:
        self.assertEqual(self.keys("", catalog.GLOBAL), ["Std_New"])

    def test_menu_text_mnemonics_dropped(self) -> None:
        texts = {c.key: c.text for c in self.commands}
        self.assertEqual(texts["Std_DlgParameter"], "Edit Parameters")


class StandIns(unittest.TestCase):
    def setUp(self) -> None:
        self.stand_ins = catalog.StandIns()
        RAN.clear()

    def tearDown(self) -> None:
        COMMANDS["PartDesign_Pad"].actions = []

    def test_live_action_preferred(self) -> None:
        live = QtGui.QAction("Pad")
        COMMANDS["PartDesign_Pad"].actions = [live]
        self.assertIs(self.stand_ins.action("PartDesign_Pad"), live)

    def test_stand_in_runs_the_command_by_name(self) -> None:
        action = self.stand_ins.action("Sketcher_CreateCircle")
        self.assertEqual(action.text(), "Circle")
        action.trigger()
        self.assertEqual(RAN, ["Sketcher_CreateCircle"])
        self.assertIs(self.stand_ins.action("Sketcher_CreateCircle"), action)

    def test_unknown_command_has_none(self) -> None:
        self.assertIsNone(self.stand_ins.action("Nowhere_Nothing"))


class Adding(Acting):
    def texts(self) -> list[str]:
        role = self.role("text")
        return [self.model.data(self.model.index(r), role) or "|"
                for r in range(self.model.rowCount())]

    def catalog_rows(self) -> dict[str, bool]:
        drawer = self.bridge.catalogModel
        names = {v.data().decode(): k for k, v in drawer.roleNames().items()}
        return {drawer.data(drawer.index(r), names["key"]):
                drawer.data(drawer.index(r), names["placed"])
                for r in range(drawer.rowCount())}

    def open_drawer(self) -> None:
        self.bridge.setEditing(True)
        self.assertTrue(self.bridge.property("loading"))
        settle()

    def test_drawer_reads_commands_a_turn_after_opening(self) -> None:
        self.open_drawer()
        self.assertFalse(self.bridge.property("loading"))
        self.assertIn("Sketcher_CreateCircle", self.catalog_rows())

    def test_insert_while_dragging_places_it(self) -> None:
        row = self.bridge.insertCommand("Sketcher_CreateCircle", 1)
        self.assertEqual(row, 1)
        self.assertEqual(self.texts()[1], "Circle")

    def test_command_already_on_the_strip_not_added_twice(self) -> None:
        self.bridge.appendCommand("Sketcher_CreateCircle")
        self.assertEqual(self.bridge.insertCommand(
            "Sketcher_CreateCircle", 0), -1)

    def test_added_command_kept_after_a_rebuild(self) -> None:
        self.bridge.appendCommand("Sketcher_CreateCircle")
        self.bridge.rebuild()
        self.assertIn("Circle", self.texts())

    def test_added_command_marked_placed(self) -> None:
        self.open_drawer()
        self.bridge.appendCommand("PartDesign_Pocket")
        self.assertTrue(self.catalog_rows()["PartDesign_Pocket"])
        self.assertFalse(self.catalog_rows()["Sketcher_CreateCircle"])

    def test_separator_appended_and_saved(self) -> None:
        self.bridge.appendSeparator()
        self.assertEqual(layouts.load(WORKBENCH).order[-1], "|")

    def test_search_and_filter_narrow_the_drawer(self) -> None:
        self.open_drawer()
        self.bridge.setFilter("SketcherWorkbench")
        self.bridge.setQuery("circ")
        self.assertEqual(list(self.catalog_rows()), ["Sketcher_CreateCircle"])


class Lasting(Acting):
    """What survives: commands not loadable yet, files, sketch editing."""

    def test_command_not_found_keeps_its_place_on_save(self) -> None:
        layouts.save(WORKBENCH, layouts.Layout(
            ["&New", "Draft_Line", "Open", "|", "Save"], []))
        self.bridge.rebuild()
        self.bridge.beginDrag()
        self.bridge.move(self.row_of("Save"), 0)
        self.bridge.endDrag(0, False)
        order = layouts.load(WORKBENCH).order
        self.assertEqual(order[:4], ["Save", "&New", "Draft_Line", "Open"])

    def test_missing_key_without_an_anchor_goes_first(self) -> None:
        live = [entry("New")]
        layout = layouts.capture(live, live, layouts.Layout(
            ["Gone", "New"], []), ["Gone"])
        self.assertEqual(layout.order, ["Gone", "New"])

    def test_export_and_import_round_trip(self) -> None:
        layouts.save(WORKBENCH, layouts.Layout(["Pad"], ["New"]))
        text = layouts.export_text()
        layouts.save(WORKBENCH, None)
        self.assertEqual(layouts.import_text(text), 1)
        self.assertEqual(layouts.load(WORKBENCH).order, ["Pad"])

    def test_import_rejects_other_files(self) -> None:
        with self.assertRaises(ValueError):
            layouts.import_text('{"PartDesignWorkbench": [1, 2]}')

    def test_export_writes_the_chosen_file(self) -> None:
        import tempfile
        layouts.save(WORKBENCH, layouts.Layout(["Pad"], []))
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "layouts.json")
            with mock.patch.object(QtWidgets.QFileDialog, "getSaveFileName",
                                   return_value=(path, "")):
                self.bridge.exportLayouts()
                settle()
            self.assertIn("Pad", Path(path).read_text(encoding="utf-8"))

    def test_sketch_editing_has_its_own_layout(self) -> None:
        from freecad.nxt.toolbars import strip
        sketch = mock.Mock()
        sketch.Object.TypeId = strip.SKETCH
        Gui.ActiveDocument = mock.Mock()
        Gui.ActiveDocument.getInEdit.return_value = sketch
        try:
            self.assertEqual(strip._layout_name(), layouts.SKETCH_EDIT)
            Gui.ActiveDocument.getInEdit.return_value = None
            Gui.activeWorkbench = lambda: mock.Mock(**{
                "name.return_value": WORKBENCH})
            self.assertEqual(strip._layout_name(), WORKBENCH)
        finally:
            Gui.ActiveDocument = None


class Grouping(Acting):
    """Several commands behind one button: FreeCAD's groups and the user's."""

    def setUp(self) -> None:
        super().setUp()
        self.fired_members: list[str] = []
        for action in COMMANDS[GROUP].actions:
            action.triggered.connect(
                lambda _c=False, a=action: self.fired_members.append(a.text()))

    def tearDown(self) -> None:
        for action in COMMANDS[GROUP].actions:
            action.triggered.disconnect()
        super().tearDown()

    def texts(self) -> list[str]:
        role = self.role("text")
        return [self.model.data(self.model.index(r), role) or "|"
                for r in range(self.model.rowCount())]

    def saved_groups(self) -> list[dict[str, object]]:
        return [t for t in layouts.load(WORKBENCH).order
                if isinstance(t, dict)]

    def new_group(self, *keys: str) -> int:
        row = self.bridge.insertGroup(0)
        for key in keys:
            self.assertTrue(self.bridge.addToGroup(key, row))
        return row

    def test_freecad_group_from_the_drawer_gets_its_dropdown(self) -> None:
        self.bridge.appendCommand(GROUP)
        row = self.model.rowCount() - 1
        self.assertEqual(self.value(row, "kind"), "group")
        self.assertEqual(self.value(row, "dropdown"), models.SPLIT)
        self.assertFalse(self.value(row, "editable"))
        self.bridge.activate(row, 0.0, 0.0)
        self.assertEqual(self.fired_members, ["Additive Box"])

    def test_member_picked_from_the_menu_becomes_the_button(self) -> None:
        self.bridge.appendCommand(GROUP)
        row = self.model.rowCount() - 1
        with mock.patch.object(QtWidgets.QMenu, "popup"):
            self.bridge.openMenu(row, 0.0, 0.0)
        self.bridge._menu.actions()[1].trigger()
        self.assertEqual(self.value(row, "text"), "Additive Cylinder")
        self.bridge.rebuild()
        self.bridge.activate(self.row_of("Additive Cylinder"), 0.0, 0.0)
        self.assertEqual(self.fired_members[-1], "Additive Cylinder")

    def test_custom_group_saved_and_restored(self) -> None:
        self.new_group("PartDesign_Pocket", "Sketcher_CreateCircle")
        group = self.saved_groups()[0]
        self.assertEqual(group["members"],
                         ["PartDesign_Pocket", "Sketcher_CreateCircle"])
        self.bridge.rebuild()
        self.assertEqual(self.value(0, "members"), 2)
        self.assertTrue(self.value(0, "editable"))

    def test_strip_command_dropped_into_a_group_leaves_the_strip(self) -> None:
        row = self.new_group("PartDesign_Pocket")
        save = self.row_of("Save")
        self.bridge.beginDrag()
        self.bridge.dropIntoGroup(save, row)
        self.assertNotIn("Save", self.texts())
        self.bridge.rebuild()
        self.assertNotIn("Save", self.texts())
        self.assertEqual(self.value(0, "members"), 2)

    def test_no_command_twice_in_a_group_or_beside_it(self) -> None:
        row = self.new_group("PartDesign_Pocket")
        self.assertFalse(self.bridge.addToGroup("PartDesign_Pocket", row))
        self.assertEqual(
            self.bridge.insertCommand("PartDesign_Pocket", 0), -1)

    def test_editor_reorders_members(self) -> None:
        row = self.new_group("PartDesign_Pocket", "Sketcher_CreateCircle")
        self.bridge.editGroup(row)
        self.assertEqual(self.bridge.property("editedGroup"), row)
        self.bridge.setMemberOrder(["Sketcher_CreateCircle",
                                    "PartDesign_Pocket"])
        self.assertEqual(self.saved_groups()[0]["members"],
                         ["Sketcher_CreateCircle", "PartDesign_Pocket"])
        self.assertEqual(
            [m["key"] for m in self.bridge.property("groupMembers")],
            ["Sketcher_CreateCircle", "PartDesign_Pocket"])

    def test_group_of_one_becomes_its_command_when_closed(self) -> None:
        row = self.new_group("PartDesign_Pocket", "Sketcher_CreateCircle")
        self.bridge.editGroup(row)
        self.bridge.removeMember(0)
        self.assertEqual(self.value(row, "kind"), "group")
        self.bridge.editGroup(-1)
        self.assertEqual(self.value(row, "kind"), "command")
        self.assertEqual(self.value(row, "text"), "Circle")

    def test_ungroup_puts_the_members_on_the_strip(self) -> None:
        row = self.new_group("PartDesign_Pocket", "Sketcher_CreateCircle")
        self.bridge.editGroup(row)
        self.bridge.ungroup()
        self.assertEqual(self.texts()[:2], ["Pocket", "Circle"])
        self.assertEqual(self.saved_groups(), [])

    def test_rename_shows_in_the_tooltip(self) -> None:
        row = self.new_group("PartDesign_Pocket", "Sketcher_CreateCircle")
        self.bridge.editGroup(row)
        self.bridge.renameGroup("  Features ")
        self.assertTrue(str(self.value(row, "tip")).startswith("Features:"))
        self.assertEqual(self.saved_groups()[0]["name"], "Features")

    def test_empty_group_dropped_when_editing_ends(self) -> None:
        self.bridge.setEditing(True)
        self.bridge.insertGroup(0)
        self.bridge.setEditing(False)
        self.assertNotEqual(self.value(0, "kind"), "group")

    def test_member_not_loadable_yet_stays_in_the_group(self) -> None:
        layouts.save(WORKBENCH, layouts.Layout([
            {"group": "group:abc", "name": "Mixed",
             "members": ["PartDesign_Pocket", "Draft_Line"]}], []))
        self.bridge.rebuild()
        self.bridge.editGroup(0)
        self.bridge.renameGroup("Mixed tools")
        self.assertEqual(self.saved_groups()[0]["members"],
                         ["PartDesign_Pocket", "Draft_Line"])
        self.bridge.editGroup(-1)
        self.assertEqual(self.value(0, "kind"), "group")


if __name__ == "__main__":
    unittest.main()
