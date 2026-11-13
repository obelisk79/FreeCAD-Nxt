"""The tree's preferences: the quick panel under the gear, and the page."""

from __future__ import annotations

import weakref
from typing import Any

import FreeCAD as App

from .. import resources
from ..app import menu_button
from ..app.i18n import follow, translate
from ..core import settings
from ..core.qt import QtCore, QtGui, QtWidgets
from ..tools import gizmos

#: The page's group in FreeCAD's Preferences dialog.
GROUP = "FreeCAD-Nxt"

#: What the quick panel offers. The page offers these and more.
QUICK = ("PartLayout", "RowDensity", "ReferenceChips",
         "EditOnDoubleClick", "DependencyArrows", "HighlightRelated",
         "DetailAutoShow", "TreeLines", "RepairProfiles", "OverlayMode",
         "QuickMass", "AutoRename", "SketchPanel", "AttachPanel")

#: Settings the theme reads: changing one restyles the panel.
_VIEW = frozenset({"RowDensity", "ReferenceChips", "UnderConstrainedMarks",
                   "RowToolTips", "TreeLines",
                   "HeaderMaxPercent", "HeaderMinWidth"})
#: Settings the snapshot reads: changing one rebuilds it.
_SNAPSHOT = frozenset({"PartLayout", "DependencyArrows"})

#: Every value a choice setting may take, in the order it is offered.
CHOICES: dict[str, tuple[str, ...]] = {
    "PartLayout": ("expression", "nested"),
    "RowDensity": ("compact", "normal", "roomy"),
    "ReferenceChips": ("problems", "all", "none"),
    "OverlayMode": ("freecad", "nxt"),
}

_live: weakref.WeakSet[Preferences] = weakref.WeakSet()


def apply(keys: set[str] | frozenset[str]) -> None:
    """Bring the open panel, and every `prefs`, in line with the store."""
    from ..tree import panel
    dock = panel.instance()
    if dock is not None:
        if keys & _VIEW:
            dock.refresh_theme()
        if "OverlayMode" in keys:
            dock.apply_overlay_mode()
        if keys & _SNAPSHOT:
            bridge = panel.bridge()
            if bridge is not None:
                bridge.rebuild()
        if "HighlightRelated" in keys:
            bridge = panel.bridge()
            if bridge is not None:
                bridge.refresh_related()
        if "DetailAutoShow" in keys:
            bridge = panel.bridge()
            if bridge is not None:
                bridge.refresh_auto_detail()
    if menu_button.SETTING in keys:
        menu_button.apply()
    if "QuickMass" in keys:
        from ..app import services
        live = services.instance()
        if live is not None:
            live.quick_mass_changed()
    if "SketchPanel" in keys:
        from ..app import services
        live = services.instance()
        if live is not None:
            live.sketch_panel_changed()
    for prefs in list(_live):
        prefs.changed.emit()


def open_page() -> None:
    import FreeCADGui as Gui
    Gui.showPreferences(GROUP, 0)


class Preferences(QtCore.QObject):
    """The quick panel's view of the settings."""

    changed = QtCore.Signal()

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        _live.add(self)

    # PySide spells QVariantMap as a string; its stubs expect a type.
    @QtCore.Property("QVariantMap", notify=changed)  # type: ignore[arg-type]
    def values(self) -> dict[str, Any]:
        return {key: settings.get(key) for key in QUICK}

    @QtCore.Slot(str, "QVariant")
    def set(self, key: str, value: Any) -> None:
        if key not in QUICK:
            return
        if key in CHOICES and value not in CHOICES[key]:
            return
        if settings.get(key) == value:
            return
        settings.put(key, value)
        apply({key})

    @QtCore.Slot()
    def openPage(self) -> None:  # noqa: N802 - QML API
        # Deferred: a modal opened under the closing click would eat it.
        QtCore.QTimer.singleShot(0, open_page)


# -- the Preferences page --

def _labels() -> dict[str, dict[str, str]]:
    return {
        "PartLayout": {
            "expression": translate("Nxt", "Expression rows"),
            "nested": translate("Nxt", "Nested"),
        },
        "RowDensity": {
            "compact": translate("Nxt", "Compact"),
            "normal": translate("Nxt", "Normal"),
            "roomy": translate("Nxt", "Roomy"),
        },
        "ReferenceChips": {
            "problems": translate("Nxt", "Problems only"),
            "all": translate("Nxt", "All"),
            "none": translate("Nxt", "None"),
        },
    }


class NxtPreferencesPage:
    """Edit > Preferences > FreeCAD-Nxt.

    Named apart from other addons' pages: FreeCAD keys Python pages by
    class name, and Assembly's is also called PreferencesPage.
    """

    def __init__(self) -> None:
        self.form = QtWidgets.QWidget()
        #: FollowSelection as loaded, to tell an edit on this page.
        self._followed = bool(settings.DEFAULTS["FollowSelection"])
        self.form.setWindowTitle(translate("Nxt", "Model panel"))
        self.form.setWindowIcon(QtGui.QIcon(str(resources.LOGO)))
        follow(self.form)
        outer = QtWidgets.QVBoxLayout(self.form)

        tree = QtWidgets.QGroupBox(translate("Nxt", "Tree"), self.form)
        layout = QtWidgets.QFormLayout(tree)
        labels = _labels()
        self._choices: dict[str, QtWidgets.QComboBox] = {}
        for key, text in (
                ("PartLayout", translate("Nxt", "Tree structure")),
                ("RowDensity", translate("Nxt", "Row density")),
                ("ReferenceChips", translate("Nxt", "Reference chips"))):
            box = QtWidgets.QComboBox(tree)
            for value in CHOICES[key]:
                box.addItem(labels[key][value], value)
            layout.addRow(text, box)
            self._choices[key] = box
        self._marks = QtWidgets.QCheckBox(
            translate("Nxt", "Mark under-constrained sketches"), tree)
        layout.addRow(self._marks)
        self._tips = QtWidgets.QCheckBox(
            translate("Nxt", "Show tooltips on the tree's rows"), tree)
        layout.addRow(self._tips)
        self._follow = QtWidgets.QCheckBox(
            translate("Nxt", "Show objects picked in the 3D view"), tree)
        layout.addRow(self._follow)
        self._dbl = QtWidgets.QCheckBox(translate(
            "Nxt", "Double-click a face to edit the feature that made it"),
            tree)
        layout.addRow(self._dbl)
        self._repair = QtWidgets.QCheckBox(translate(
            "Nxt", "Auto repair 'Wire not closed' errors"), tree)
        layout.addRow(self._repair)
        self._rename = QtWidgets.QCheckBox(translate(
            "Nxt", "Rename new sketches, containers and features"), tree)
        self._rename.setToolTip(translate(
            "Nxt", "When a new object's edit closes (or a container is "
                   "made), its name opens for editing in the tree."))
        layout.addRow(self._rename)
        self._sketch_panel = QtWidgets.QCheckBox(translate(
            "Nxt", "Experimental: Nxt's task panel while a sketch is edited"),
            tree)
        self._sketch_panel.setToolTip(translate(
            "Nxt", "The solver's status moves to a pill in the 3D view, "
                   "with the grid and snap settings. The task panel "
                   "shows only problems and what is selected; FreeCAD's "
                   "lists stay one click away."))
        layout.addRow(self._sketch_panel)
        self._attach_panel = QtWidgets.QCheckBox(translate(
            "Nxt", "Experimental: Nxt's attachment task panel"), tree)
        self._attach_panel.setToolTip(translate(
            "Nxt", "Edit attachment opens Nxt's panel: picks named for "
                   "what they are, ways grouped by what they do, and the "
                   "offset shut until wanted."))
        layout.addRow(self._attach_panel)
        self._attach = QtWidgets.QCheckBox(translate(
            "Nxt", "Attach a new sketch to three picked points without "
                   "asking"), tree)
        self._attach.setToolTip(translate(
            "Nxt", "Three points, or a straight edge and a point, give "
                   "the sketch's plane.\nHold Shift to get the attachment "
                   "dialog anyway."))
        layout.addRow(self._attach)
        self._arrows = QtWidgets.QCheckBox(translate(
            "Nxt", "Show the selection's dependencies as arrows"), tree)
        layout.addRow(self._arrows)
        self._related = QtWidgets.QCheckBox(translate(
            "Nxt", "Highlight the objects related to the selection"), tree)
        layout.addRow(self._related)
        self._lines = QtWidgets.QCheckBox(translate(
            "Nxt", "Show tree lines"), tree)
        layout.addRow(self._lines)
        self._auto_detail = QtWidgets.QCheckBox(translate(
            "Nxt", "Show a row's details when it is clicked"), tree)
        layout.addRow(self._auto_detail)
        outer.addWidget(tree)

        panel = QtWidgets.QGroupBox(translate("Nxt", "Panel"), self.form)
        layout = QtWidgets.QFormLayout(panel)
        self._visible = QtWidgets.QCheckBox(
            translate("Nxt", "Open the model panel at startup"), panel)
        layout.addRow(self._visible)
        self._percent = QtWidgets.QSpinBox(panel)
        self._percent.setRange(10, 60)
        self._percent.setSuffix(" %")
        layout.addRow(translate("Nxt", "Header and detail strip, widest"),
                      self._percent)
        self._min_width = QtWidgets.QSpinBox(panel)
        self._min_width.setRange(120, 600)
        self._min_width.setSuffix(" px")
        layout.addRow(translate("Nxt", "…but never narrower than"),
                      self._min_width)
        self._pinned = QtWidgets.QCheckBox(
            translate("Nxt", "Keep the Property Inspector open (pinned)"),
            panel)
        layout.addRow(self._pinned)
        self._updates = QtWidgets.QCheckBox(translate(
            "Nxt", "Check installed addons for updates at startup"), panel)
        self._updates.setToolTip(translate(
            "Nxt", "Uses the Addon Manager's check, once per session, and "
                   "lists any updates to review and apply."))
        layout.addRow(self._updates)
        self._menu_button = QtWidgets.QCheckBox(translate(
            "Nxt", "Menus in a FreeCAD button, menu bar hidden"), panel)
        self._menu_button.setToolTip(translate(
            "Nxt", "The menus open from the FreeCAD logo, first on the "
                   "toolbars. Shortcuts keep working."))
        self._menu_button.setVisible(menu_button.supported())
        layout.addRow(self._menu_button)
        outer.addWidget(panel)

        # FreeCAD's own gizmo preferences, which no FreeCAD page shows.
        drag = QtWidgets.QGroupBox(
            translate("Nxt", "3D drag handles"), self.form)
        layout = QtWidgets.QFormLayout(drag)
        self._plain = QtWidgets.QComboBox(drag)
        self._plain.addItem(translate("Nxt", "Fine steps"), "fine")
        self._plain.addItem(translate("Nxt", "Coarse steps"), "coarse")
        layout.addRow(translate("Nxt", "A plain drag moves in"), self._plain)
        self._key = QtWidgets.QComboBox(drag)
        for key, text in (("ctrl", "Ctrl"), ("shift", "Shift"),
                          ("alt", "Alt")):
            self._key.addItem(text, key)
        layout.addRow(translate("Nxt", "Hold to switch steps"), self._key)
        self._step = QtWidgets.QDoubleSpinBox(drag)
        self._step.setRange(0.001, 1000.0)
        self._step.setDecimals(3)
        self._step.setSuffix(" mm")
        self._step.setToolTip(translate(
            "Nxt", "Kept with FreeCAD's dialog history: another tool, "
                   "such as Transform, may change it."))
        layout.addRow(translate("Nxt", "Fine step"), self._step)
        self._coarse = QtWidgets.QCheckBox(
            translate("Nxt", "Coarse steps"), drag)
        layout.addRow(self._coarse)
        self._linear = QtWidgets.QSpinBox(drag)
        self._linear.setRange(1, 100)
        self._linear.setPrefix("× ")
        self._linear_note = QtWidgets.QLabel(drag)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self._linear)
        row.addWidget(self._linear_note, 1)
        layout.addRow(translate("Nxt", "Coarse step"), row)
        self._rotation = QtWidgets.QSpinBox(drag)
        self._rotation.setRange(1, 100)
        self._rotation.setPrefix("× ")
        layout.addRow(translate("Nxt", "Coarse rotation step"),
                      self._rotation)
        self._floating = QtWidgets.QCheckBox(translate(
            "Nxt", "Show the value beside the arrow while dragging"), drag)
        layout.addRow(self._floating)
        self._no_handles = QtWidgets.QCheckBox(translate(
            "Nxt", "No drag handles when a feature is edited from the tree"),
            drag)
        self._no_handles.setToolTip(translate(
            "Nxt", "Double-clicking a feature's row opens it without the "
                   "handles.\nA new feature still gets them."))
        layout.addRow(self._no_handles)
        self._snap = QtWidgets.QCheckBox(translate(
            "Nxt", "Snap a dragged length to parallel faces"), drag)
        self._snap.setToolTip(translate(
            "Nxt", "Pad and Pocket lengths stop on a face square to the "
                   "arrow.\nHold Alt while dragging to pass through."))
        layout.addRow(self._snap)
        for signal in (self._step.valueChanged, self._linear.valueChanged):
            signal.connect(self._update_note)
        self._coarse.toggled.connect(self._linear.setEnabled)
        self._coarse.toggled.connect(self._rotation.setEnabled)
        outer.addWidget(drag)

        reset = QtWidgets.QPushButton(
            translate("Nxt", "Reset to defaults"), self.form)
        reset.clicked.connect(self._reset)
        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        row.addWidget(reset)
        outer.addLayout(row)
        outer.addStretch(1)

    # FreeCAD calls these two by name.
    def loadSettings(self) -> None:  # noqa: N802
        for key, box in self._choices.items():
            index = box.findData(settings.get(key))
            box.setCurrentIndex(max(0, index))
        self._marks.setChecked(bool(settings.get("UnderConstrainedMarks")))
        self._tips.setChecked(bool(settings.get("RowToolTips")))
        self._followed = bool(settings.get("FollowSelection"))
        self._follow.setChecked(self._followed)
        self._dbl.setChecked(bool(settings.get("EditOnDoubleClick")))
        self._repair.setChecked(bool(settings.get("RepairProfiles")))
        self._rename.setChecked(bool(settings.get("AutoRename")))
        self._sketch_panel.setChecked(bool(settings.get("SketchPanel")))
        self._attach_panel.setChecked(bool(settings.get("AttachPanel")))
        self._attach.setChecked(bool(settings.get("AttachSketchByPoints")))
        self._arrows.setChecked(bool(settings.get("DependencyArrows")))
        self._related.setChecked(bool(settings.get("HighlightRelated")))
        self._auto_detail.setChecked(bool(settings.get("DetailAutoShow")))
        self._lines.setChecked(bool(settings.get("TreeLines")))
        self._visible.setChecked(bool(settings.get("Visible")))
        self._percent.setValue(int(settings.get("HeaderMaxPercent")))
        self._min_width.setValue(int(settings.get("HeaderMinWidth")))
        self._pinned.setChecked(bool(settings.get("InspectorPinned")))
        self._updates.setChecked(bool(settings.get("CheckAddonUpdates")))
        self._menu_button.setChecked(bool(settings.get(menu_button.SETTING)))
        self._show_drag(gizmos.read())
        self._floating.setChecked(bool(settings.get("FloatingValues")))
        self._no_handles.setChecked(
            bool(settings.get("TreeEditHidesHandles")))
        self._snap.setChecked(bool(settings.get("SnapToFaces")))

    def saveSettings(self) -> None:  # noqa: N802
        for key, box in self._choices.items():
            settings.put(key, str(box.currentData()))
        settings.put("UnderConstrainedMarks", self._marks.isChecked())
        settings.put("RowToolTips", self._tips.isChecked())
        # FreeCAD's Selection page saves this too, first: write it only if
        # changed here, or this page's stale copy would undo that edit.
        if self._follow.isChecked() != self._followed:
            self._followed = self._follow.isChecked()
            settings.put("FollowSelection", self._followed)
        settings.put("EditOnDoubleClick", self._dbl.isChecked())
        settings.put("RepairProfiles", self._repair.isChecked())
        settings.put("AutoRename", self._rename.isChecked())
        settings.put("SketchPanel", self._sketch_panel.isChecked())
        settings.put("AttachPanel", self._attach_panel.isChecked())
        settings.put("AttachSketchByPoints", self._attach.isChecked())
        settings.put("DependencyArrows", self._arrows.isChecked())
        settings.put("HighlightRelated", self._related.isChecked())
        settings.put("DetailAutoShow", self._auto_detail.isChecked())
        settings.put("TreeLines", self._lines.isChecked())
        settings.put("Visible", self._visible.isChecked())
        settings.put("HeaderMaxPercent", self._percent.value())
        settings.put("HeaderMinWidth", self._min_width.value())
        settings.put("InspectorPinned", self._pinned.isChecked())
        settings.put("CheckAddonUpdates", self._updates.isChecked())
        settings.put(menu_button.SETTING, self._menu_button.isChecked())
        settings.put("FloatingValues", self._floating.isChecked())
        settings.put("TreeEditHidesHandles", self._no_handles.isChecked())
        settings.put("SnapToFaces", self._snap.isChecked())
        gizmos.write({
            "plain": self._plain.currentData(),
            "key": self._key.currentData(),
            "coarse": self._coarse.isChecked(),
            "step": self._step.value(),
            "linear": self._linear.value(),
            "rotation": self._rotation.value(),
        })
        try:
            apply(set(QUICK) | _VIEW | {menu_button.SETTING})
        except Exception as exc:
            App.Console.PrintError("Nxt: could not apply preferences: %s\n"
                                   % exc)

    def _reset(self) -> None:
        """Put the page's fields back to Nxt's defaults; Apply or OK saves."""
        for key, box in self._choices.items():
            box.setCurrentIndex(max(0, box.findData(settings.DEFAULTS[key])))
        self._marks.setChecked(
            bool(settings.DEFAULTS["UnderConstrainedMarks"]))
        self._tips.setChecked(bool(settings.DEFAULTS["RowToolTips"]))
        self._follow.setChecked(bool(settings.DEFAULTS["FollowSelection"]))
        self._dbl.setChecked(bool(settings.DEFAULTS["EditOnDoubleClick"]))
        self._repair.setChecked(bool(settings.DEFAULTS["RepairProfiles"]))
        self._rename.setChecked(bool(settings.DEFAULTS["AutoRename"]))
        self._sketch_panel.setChecked(
            bool(settings.DEFAULTS["SketchPanel"]))
        self._attach_panel.setChecked(
            bool(settings.DEFAULTS["AttachPanel"]))
        self._attach.setChecked(
            bool(settings.DEFAULTS["AttachSketchByPoints"]))
        self._arrows.setChecked(bool(settings.DEFAULTS["DependencyArrows"]))
        self._related.setChecked(
            bool(settings.DEFAULTS["HighlightRelated"]))
        self._auto_detail.setChecked(
            bool(settings.DEFAULTS["DetailAutoShow"]))
        self._lines.setChecked(bool(settings.DEFAULTS["TreeLines"]))
        self._visible.setChecked(bool(settings.DEFAULTS["Visible"]))
        self._percent.setValue(int(settings.DEFAULTS["HeaderMaxPercent"]))
        self._min_width.setValue(int(settings.DEFAULTS["HeaderMinWidth"]))
        self._pinned.setChecked(bool(settings.DEFAULTS["InspectorPinned"]))
        self._updates.setChecked(
            bool(settings.DEFAULTS["CheckAddonUpdates"]))
        self._menu_button.setChecked(
            bool(settings.DEFAULTS[menu_button.SETTING]))
        self._show_drag(gizmos.DEFAULTS)
        self._floating.setChecked(bool(settings.DEFAULTS["FloatingValues"]))
        self._no_handles.setChecked(
            bool(settings.DEFAULTS["TreeEditHidesHandles"]))
        self._snap.setChecked(bool(settings.DEFAULTS["SnapToFaces"]))

    def _show_drag(self, values: dict[str, Any]) -> None:
        self._plain.setCurrentIndex(
            max(0, self._plain.findData(values["plain"])))
        self._key.setCurrentIndex(max(0, self._key.findData(values["key"])))
        self._step.setValue(float(values["step"]))
        self._coarse.setChecked(bool(values["coarse"]))
        self._linear.setValue(int(values["linear"]))
        self._rotation.setValue(int(values["rotation"]))
        self._linear.setEnabled(bool(values["coarse"]))
        self._rotation.setEnabled(bool(values["coarse"]))
        self._update_note()

    def _update_note(self) -> None:
        size = self._step.value() * self._linear.value()
        self._linear_note.setText("= %s mm" % ("%g" % round(size, 3)))
