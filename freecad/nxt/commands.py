"""The addon's GUI commands.

Plain duck-typed command classes, registered by `init_gui`. Imports of the
modules that do the work are deferred to `Activated`, so registering the
commands at startup costs nothing and pulls in no QtQuick.
"""

from __future__ import annotations

import FreeCADGui as Gui

from .i18n import QT_TRANSLATE_NOOP

ICON = "Nxt.svg"


class _Command:
    """Shared plumbing: resources from class attributes."""

    menu_text: str = ""
    tool_tip: str = ""
    pixmap: str = ""

    def GetResources(self) -> dict[str, str]:  # noqa: N802 - FreeCAD command API
        resources = {"MenuText": self.menu_text, "ToolTip": self.tool_tip}
        if self.pixmap:
            resources["Pixmap"] = self.pixmap
        return resources

    def IsActive(self) -> bool:  # noqa: N802 - FreeCAD command API
        return True


class ModelPanel(_Command):
    """Show or hide the Nxt model panel."""

    menu_text = QT_TRANSLATE_NOOP("Nxt_ModelPanel", "Nxt model panel")
    tool_tip = QT_TRANSLATE_NOOP(
        "Nxt_ModelPanel",
        "Model history as a timeline, with a draggable rollback bar")
    pixmap = ICON

    def Activated(self) -> None:  # noqa: N802 - FreeCAD command API
        from .tree import panel
        panel.toggle()


class ModelPanelOverlay(_Command):
    """Draw the panel as floating labels over the 3D view."""

    menu_text = QT_TRANSLATE_NOOP("Nxt_ModelPanelOverlay",
                                  "Nxt panel overlay")
    tool_tip = QT_TRANSLATE_NOOP(
        "Nxt_ModelPanelOverlay",
        "Draw the model panel as floating labels with no background")

    def Activated(self) -> None:  # noqa: N802 - FreeCAD command API
        from .tree import panel
        panel.toggle_overlay()

    def IsActive(self) -> bool:  # noqa: N802 - FreeCAD command API
        from .tree import panel
        return panel.is_open()


class PropertyInspector(_Command):
    """Open FreeCAD's Property editor in an inspector beside the panel."""

    menu_text = QT_TRANSLATE_NOOP("Nxt_PropertyInspector",
                                  "Nxt Property Inspector")
    tool_tip = QT_TRANSLATE_NOOP(
        "Nxt_PropertyInspector",
        "Show the selection's properties beside the model panel")

    def Activated(self) -> None:  # noqa: N802 - FreeCAD command API
        from . import property_inspector
        property_inspector.toggle()


class Reload(_Command):
    """Hot-reload the addon's Python modules during development."""

    menu_text = QT_TRANSLATE_NOOP("Nxt_Reload", "Reload Nxt")
    tool_tip = QT_TRANSLATE_NOOP("Nxt_Reload",
                                 "Hot-reload the addon's Python modules")

    def Activated(self) -> None:  # noqa: N802 - FreeCAD command API
        from . import reload_all
        reload_all()


COMMANDS: dict[str, type[_Command]] = {
    "Nxt_ModelPanel": ModelPanel,
    "Nxt_ModelPanelOverlay": ModelPanelOverlay,
    "Nxt_PropertyInspector": PropertyInspector,
    "Nxt_Reload": Reload,
}

#: Listed in the View menu. Reload stays console-only: it is a
#: development tool, not a feature.
MENU = ("Nxt_ModelPanel", "Nxt_ModelPanelOverlay", "Nxt_PropertyInspector")


def register() -> None:
    for name, command in COMMANDS.items():
        Gui.addCommand(name, command())
