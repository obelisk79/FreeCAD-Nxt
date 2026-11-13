"""The menu's own words, marked for translation.

lupdate cannot read TOML, so every label `default.toml` uses is listed
here; a test checks the two stay in step.
"""

from __future__ import annotations

from ..app.i18n import QT_TRANSLATE_NOOP

ACTIONS: dict[str, str] = {
    "nxt:isolate": QT_TRANSLATE_NOOP("NxtMenu", "Isolate"),
    "nxt:inspector": QT_TRANSLATE_NOOP("NxtMenu", "Property Inspector"),
    "nxt:rename": QT_TRANSLATE_NOOP("NxtMenu", "Rename"),
    "nxt:edit_attachment": QT_TRANSLATE_NOOP("NxtMenu", "Edit attachment"),
    "nxt:recompute_object": QT_TRANSLATE_NOOP("NxtMenu", "Recompute"),
    "nxt:reveal_failure": QT_TRANSLATE_NOOP("NxtMenu", "Why did it fail?"),
    "nxt:reveal_first_problem": QT_TRANSLATE_NOOP(
        "NxtMenu", "Show the failed feature"),
    "nxt:show_solver_issues": QT_TRANSLATE_NOOP(
        "NxtMenu", "Show the solver's findings"),
    "nxt:select_consumers": QT_TRANSLATE_NOOP(
        "NxtMenu", "Select what uses it"),
    "nxt:select_support": QT_TRANSLATE_NOOP(
        "NxtMenu", "Select what it's built from"),
    "nxt:set_tip": QT_TRANSLATE_NOOP("NxtMenu", "Roll back to here"),
    "nxt:roll_forward": QT_TRANSLATE_NOOP("NxtMenu", "Roll forward to here"),
    "nxt:make_active": QT_TRANSLATE_NOOP("NxtMenu", "Make active"),
    "nxt:select_group_contents": QT_TRANSLATE_NOOP(
        "NxtMenu", "Select group contents"),
    "nxt:select_instances": QT_TRANSLATE_NOOP(
        "NxtMenu", "Select all instances"),
    "nxt:select_same_type": QT_TRANSLATE_NOOP(
        "NxtMenu", "Select all of this type in the Body"),
    "nxt:expand_all": QT_TRANSLATE_NOOP("NxtMenu", "Expand all"),
    "nxt:show_all": QT_TRANSLATE_NOOP("NxtMenu", "Show all objects"),
    "nxt:show_contents": QT_TRANSLATE_NOOP("NxtMenu", "Show all"),
    "nxt:collapse_all": QT_TRANSLATE_NOOP("NxtMenu", "Collapse all"),
    "nxt:open_file_location": QT_TRANSLATE_NOOP(
        "NxtMenu", "Open file location"),
    "nxt:synchronize_binder": QT_TRANSLATE_NOOP("NxtMenu", "Synchronize"),
    "nxt:select_bound": QT_TRANSLATE_NOOP("NxtMenu", "Select bound object"),
    "nxt:native_menu": QT_TRANSLATE_NOOP("NxtMenu", "FreeCAD's menu…"),
    "nxt:expressions_copy_selected": QT_TRANSLATE_NOOP(
        "NxtMenu", "Copy selected"),
    "nxt:expressions_copy_document": QT_TRANSLATE_NOOP(
        "NxtMenu", "Copy active document"),
    "nxt:expressions_copy_all": QT_TRANSLATE_NOOP(
        "NxtMenu", "Copy all documents"),
    "nxt:expressions_paste": QT_TRANSLATE_NOOP("NxtMenu", "Paste"),
}

#: Short labels under the bar's icons.
BAR: dict[str, str] = {
    "hide": QT_TRANSLATE_NOOP("NxtMenu", "Hide"),
    "show": QT_TRANSLATE_NOOP("NxtMenu", "Show"),
    "nxt:isolate": QT_TRANSLATE_NOOP("NxtMenu", "Isolate"),
    "nxt:isolate_exit": QT_TRANSLATE_NOOP("NxtMenu", "Exit isolate"),
    "Std_ViewFitSelection": QT_TRANSLATE_NOOP("NxtMenu", "Fit"),
    "Std_SetAppearance": QT_TRANSLATE_NOOP("NxtMenu", "Appearance"),
    "nxt:inspector": QT_TRANSLATE_NOOP("NxtMenu", "Inspect"),
}

#: Labels that show a count for several objects: "Delete 3".
COUNTED: frozenset[str] = frozenset({
    "Std_Delete", "Std_DuplicateSelection", "Std_Cut", "Std_Copy",
    "Std_ToggleVisibility", "Std_ToggleSuppress", "Std_ToggleFreeze",
    "Std_ToggleTransparency", "Std_ToggleSelectability",
    "Std_SetAppearance", "Std_SetMaterial", "Std_RandomColor",
    "Std_MarkToRecompute", "nxt:isolate", "nxt:recompute_object",
})

#: How a count is added to a label; %1 the label, %2 how many.
COUNTED_LABEL = QT_TRANSLATE_NOOP("NxtMenu", "%1 %2")

#: FreeCAD command icons that Nxt's actions borrow.
ICONS: dict[str, str] = {
    "nxt:isolate": "Std_ShowSelection",
    "nxt:inspector": "Std_Properties",
    "nxt:rename": "Std_Rename",
    "nxt:recompute_object": "Std_Refresh",
    "nxt:select_instances": "Std_TreeSelectAllInstances",
    "nxt:set_tip": "PartDesign_MoveTip",
    "nxt:roll_forward": "PartDesign_MoveTip",
    "nxt:open_file_location": "Std_Open",
}

#: Group names, listed for translation extraction.
GROUPS: tuple[str, ...] = (
    QT_TRANSLATE_NOOP("NxtMenu", "Model"),
    QT_TRANSLATE_NOOP("NxtMenu", "Organize"),
    QT_TRANSLATE_NOOP("NxtMenu", "Relations"),
    QT_TRANSLATE_NOOP("NxtMenu", "Inspect"),
    QT_TRANSLATE_NOOP("NxtMenu", "Clipboard"),
    QT_TRANSLATE_NOOP("NxtMenu", "Display"),
    QT_TRANSLATE_NOOP("NxtMenu", "Recompute"),
    QT_TRANSLATE_NOOP("NxtMenu", "Links"),
    QT_TRANSLATE_NOOP("NxtMenu", "Sketcher"),
    QT_TRANSLATE_NOOP("NxtMenu", "Part Design"),
    QT_TRANSLATE_NOOP("NxtMenu", "Part"),
    QT_TRANSLATE_NOOP("NxtMenu", "Draft"),
    QT_TRANSLATE_NOOP("NxtMenu", "More"),
    QT_TRANSLATE_NOOP("NxtMenu", "Delete"),
    #: The tree header's menu: its sections and subtitle.
    QT_TRANSLATE_NOOP("NxtMenu", "Visibility"),
    QT_TRANSLATE_NOOP("NxtMenu", "File"),
    QT_TRANSLATE_NOOP("NxtMenu", "Document"),
    QT_TRANSLATE_NOOP("NxtMenu", "Open documents"),
    #: An edit mode's label; %1 is the object's label.
    QT_TRANSLATE_NOOP("NxtMenu", "Edit %1"),
    #: The menu's title for a selection of several; %1 is how many.
    QT_TRANSLATE_NOOP("NxtMenu", "%1 objects"),
)

#: Labels `default.toml` gives FreeCAD commands, for translation.
OVERRIDES: tuple[str, ...] = (
    QT_TRANSLATE_NOOP("NxtMenu", "Make link"),
    QT_TRANSLATE_NOOP("NxtMenu", "Move to another Body"),
    QT_TRANSLATE_NOOP("NxtMenu", "Move after another feature"),
    QT_TRANSLATE_NOOP("NxtMenu", "Set face colors"),
    QT_TRANSLATE_NOOP("NxtMenu", "New group inside"),
    QT_TRANSLATE_NOOP("NxtMenu", "Appearance per face"),
    QT_TRANSLATE_NOOP("NxtMenu", "Show spreadsheet"),
    QT_TRANSLATE_NOOP("NxtMenu", "Expressions"),
)
