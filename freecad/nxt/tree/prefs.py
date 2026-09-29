"""The tree's preferences: the quick panel under the gear, and the page.

Both read and write the same values in FreeCAD's parameter store (see
settings.py), so a change in either shows in the other at once. A change
takes effect as it is made: view settings restyle the panel, the Part
layout rebuilds its snapshot.

`Preferences` is what QML sees, as the context property `prefs`.
`PreferencesPage` is the page under Edit > Preferences > FreeCAD-Nxt,
registered by init_gui.
"""

from __future__ import annotations

import weakref
from typing import Any

import FreeCAD as App

from .. import resources
from ..i18n import translate
from ..qt import QtCore, QtGui, QtWidgets
from . import gizmos, settings

#: The page's group in FreeCAD's Preferences dialog.
GROUP = "FreeCAD-Nxt"

#: What the quick panel offers. The page offers these and more.
QUICK = ("PartLayout", "RowDensity", "ReferenceChips",
         "UnderConstrainedMarks", "FollowSelection", "EditOnDoubleClick",
         "DependencyArrows")

#: Settings the theme reads: changing one restyles the panel.
_VIEW = frozenset({"RowDensity", "ReferenceChips", "UnderConstrainedMarks",
                   "HeaderMaxPercent", "HeaderMinWidth"})
#: Settings the snapshot reads: changing one rebuilds it.
_SNAPSHOT = frozenset({"PartLayout", "DependencyArrows"})

#: Every value a choice setting may take, in the order it is offered.
CHOICES: dict[str, tuple[str, ...]] = {
    "PartLayout": ("expression", "nested"),
    "RowDensity": ("compact", "normal", "roomy"),
    "ReferenceChips": ("problems", "all", "none"),
}

_live: weakref.WeakSet[Preferences] = weakref.WeakSet()


def apply(keys: set[str] | frozenset[str]) -> None:
    """Bring the open panel, and every `prefs`, in line with the store."""
    from . import panel
    dock = panel.instance()
    if dock is not None:
        if keys & _VIEW:
            dock.refresh_theme()
        if keys & _SNAPSHOT:
            bridge = panel.bridge()
            if bridge is not None:
                bridge.rebuild()
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

    # A type name as a string is how PySide spells QVariantMap; its stubs
    # only allow a Python type here.
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
        # Deferred: the quick panel is closing, and a modal dialog opened
        # under its closing click would take the click with it.
        QtCore.QTimer.singleShot(0, open_page)


# ---------------------------------------------------------------------------
# The Preferences page
# ---------------------------------------------------------------------------

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


class PreferencesPage:
    """Edit > Preferences > FreeCAD-Nxt.

    FreeCAD's Preferences dialog is a widgets dialog, so this page is made of
    widgets, as every other page in it is; the quick panel is where Nxt's
    own controls are.
    """

    def __init__(self) -> None:
        self.form = QtWidgets.QWidget()
        self.form.setWindowTitle(translate("Nxt", "Model panel"))
        self.form.setWindowIcon(QtGui.QIcon(str(resources.LOGO)))
        outer = QtWidgets.QVBoxLayout(self.form)

        tree = QtWidgets.QGroupBox(translate("Nxt", "Tree"), self.form)
        layout = QtWidgets.QFormLayout(tree)
        labels = _labels()
        self._choices: dict[str, QtWidgets.QComboBox] = {}
        for key, text in (
                ("PartLayout", translate("Nxt", "Part workbench models")),
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
        self._follow = QtWidgets.QCheckBox(
            translate("Nxt", "Show objects picked in the 3D view"), tree)
        layout.addRow(self._follow)
        self._dbl = QtWidgets.QCheckBox(translate(
            "Nxt", "Double-click a face to edit the feature that made it"),
            tree)
        layout.addRow(self._dbl)
        self._arrows = QtWidgets.QCheckBox(translate(
            "Nxt", "Show the selection's dependencies as arrows"), tree)
        layout.addRow(self._arrows)
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
        outer.addWidget(panel)

        # FreeCAD's own preferences (gizmos.py), which no FreeCAD page
        # shows. Nxt sets fine-first and Ctrl once, on its first run.
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
        self._follow.setChecked(bool(settings.get("FollowSelection")))
        self._dbl.setChecked(bool(settings.get("EditOnDoubleClick")))
        self._arrows.setChecked(bool(settings.get("DependencyArrows")))
        self._visible.setChecked(bool(settings.get("Visible")))
        self._percent.setValue(int(settings.get("HeaderMaxPercent")))
        self._min_width.setValue(int(settings.get("HeaderMinWidth")))
        self._pinned.setChecked(bool(settings.get("InspectorPinned")))
        self._show_drag(gizmos.read())
        self._floating.setChecked(bool(settings.get("FloatingValues")))

    def saveSettings(self) -> None:  # noqa: N802
        for key, box in self._choices.items():
            settings.put(key, str(box.currentData()))
        settings.put("UnderConstrainedMarks", self._marks.isChecked())
        settings.put("FollowSelection", self._follow.isChecked())
        settings.put("EditOnDoubleClick", self._dbl.isChecked())
        settings.put("DependencyArrows", self._arrows.isChecked())
        settings.put("Visible", self._visible.isChecked())
        settings.put("HeaderMaxPercent", self._percent.value())
        settings.put("HeaderMinWidth", self._min_width.value())
        settings.put("InspectorPinned", self._pinned.isChecked())
        settings.put("FloatingValues", self._floating.isChecked())
        gizmos.write({
            "plain": self._plain.currentData(),
            "key": self._key.currentData(),
            "coarse": self._coarse.isChecked(),
            "step": self._step.value(),
            "linear": self._linear.value(),
            "rotation": self._rotation.value(),
        })
        try:
            apply(set(QUICK) | _VIEW)
        except Exception as exc:
            App.Console.PrintError("Nxt: could not apply preferences: %s\n"
                                   % exc)

    def _reset(self) -> None:
        """Put the page's fields back to Nxt's defaults; Apply or OK saves."""
        for key, box in self._choices.items():
            box.setCurrentIndex(max(0, box.findData(settings.DEFAULTS[key])))
        self._marks.setChecked(
            bool(settings.DEFAULTS["UnderConstrainedMarks"]))
        self._follow.setChecked(bool(settings.DEFAULTS["FollowSelection"]))
        self._dbl.setChecked(bool(settings.DEFAULTS["EditOnDoubleClick"]))
        self._arrows.setChecked(bool(settings.DEFAULTS["DependencyArrows"]))
        self._visible.setChecked(bool(settings.DEFAULTS["Visible"]))
        self._percent.setValue(int(settings.DEFAULTS["HeaderMaxPercent"]))
        self._min_width.setValue(int(settings.DEFAULTS["HeaderMinWidth"]))
        self._pinned.setChecked(bool(settings.DEFAULTS["InspectorPinned"]))
        self._show_drag(gizmos.DEFAULTS)
        self._floating.setChecked(bool(settings.DEFAULTS["FloatingValues"]))

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
