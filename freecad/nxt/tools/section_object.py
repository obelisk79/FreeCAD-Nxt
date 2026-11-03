"""Section planes as document objects, kept in a "Sections" group.

Each section is a FeaturePython holding its plane; its exact cut is a
Part::FeaturePython beside it in the group. The eye turns the cut on
and off, a double-click on either edits the section, and both are saved
with the file. Opened without Nxt, the objects load and simply do
nothing.
"""

from __future__ import annotations

from typing import Any

import FreeCAD as App

from .. import resources
from ..core.qt import QtCore

GROUP_NAME = "Sections"
SECTION_NAME = "Section"
#: How many sections may cut a view at once.
LIMIT = 3
MODES = ["Plane", "Wedge"]
#: The wedge's opening between its two planes, by default.
WEDGE_ANGLE = 90.0
ICON = str(resources.ICONS / "nxt_section.svg")


class SectionPlane:
    """The section's data: where its plane is."""

    def __init__(self, obj: Any) -> None:
        obj.Proxy = self
        add_properties(obj)

    def execute(self, obj: Any) -> None:
        pass

    def onChanged(self, obj: Any, prop: str) -> None:  # noqa: N802
        if prop == "Excluded" and _whole_bodies(obj):
            return
        if prop in ("Mode", "Angle", "Excluded"):
            from . import section_view
            section_view.changed(obj)

    def dumps(self) -> None:
        return None

    def loads(self, _state: Any) -> None:
        return None

    def onDocumentRestored(self, obj: Any) -> None:  # noqa: N802
        add_properties(obj)


def _body_of(obj: Any) -> Any:
    """A Part Design feature's Body: picked, it stands for the body."""
    try:
        body = obj.getParentGeoFeatureGroup()
    except Exception:
        return obj
    if body is not None and body.TypeId == "PartDesign::Body":
        return body
    return obj


def _whole_bodies(obj: Any) -> bool:
    """Excluded features become their bodies; True if it was changed."""
    out: list[Any] = []
    for item in obj.Excluded:
        whole = _body_of(item)
        if all(o is not whole for o in out):
            out.append(whole)
    if [o.Name for o in out] == [o.Name for o in obj.Excluded]:
        return False
    obj.Excluded = out
    return True


def add_properties(obj: Any) -> None:
    for kind, name, doc in (
            ("App::PropertyVector", "Base", "A point on the plane"),
            ("App::PropertyVector", "Normal",
             "Points into the half that stays"),
            ("App::PropertyVector", "XAxis", "The frame's own x axis"),
            ("App::PropertyLink", "Cut", "The exact cut faces"),
            ("App::PropertyEnumeration", "Mode",
             "One plane, or two hinged on the frame's middle"),
            ("App::PropertyAngle", "Angle",
             "The wedge's opening, between its two planes"),
            ("App::PropertyLinkListGlobal", "Excluded",
             "Left whole: these and all inside them")):
        if not hasattr(obj, name):
            obj.addProperty(kind, name, "Section", doc)
            if name == "Mode":
                obj.Mode = MODES
            elif name == "Angle":
                obj.Angle = WEDGE_ANGLE
    obj.setEditorMode("Cut", 2)


class ViewProviderSection:
    """Eye, double-click and delete for a section."""

    def __init__(self, vobj: Any) -> None:
        vobj.Proxy = self

    def attach(self, vobj: Any) -> None:
        self.Object = vobj.Object
        # The 3D view may not exist yet while a file is opening.
        obj = vobj.Object
        QtCore.QTimer.singleShot(0, lambda: sync(obj))

    def getIcon(self) -> str:  # noqa: N802 - FreeCAD API
        return ICON

    def doubleClicked(self, vobj: Any) -> bool:  # noqa: N802
        edit(vobj.Object)
        return True

    def setEdit(self, vobj: Any, _mode: int = 0) -> bool:  # noqa: N802
        """Edit from the Nxt tree or Edit menu, as a double-click does.

        The frame is its own edit; FreeCAD's edit mode is not entered.
        """
        edit(vobj.Object)
        return False

    def onChanged(self, vobj: Any, prop: str) -> None:  # noqa: N802
        if prop == "Visibility":
            sync(vobj.Object)

    def onDelete(self, vobj: Any, _subelements: Any) -> bool:  # noqa: N802
        from . import section_view
        section_view.stop(vobj.Object, delete_cut=True)
        return True

    def dumps(self) -> None:
        return None

    def loads(self, _state: Any) -> None:
        return None


class ViewProviderCut:
    """A section's exact cut: a double-click edits its section."""

    def __init__(self, vobj: Any) -> None:
        vobj.Proxy = self

    def attach(self, vobj: Any) -> None:
        self.Object = vobj.Object

    def getIcon(self) -> str:  # noqa: N802 - FreeCAD API
        return ICON

    def doubleClicked(self, vobj: Any) -> bool:  # noqa: N802
        section = section_of(vobj.Object)
        if section is not None:
            edit(section)
        return True

    def setEdit(self, vobj: Any, _mode: int = 0) -> bool:  # noqa: N802
        """Any edit is its section's: the cut has no placement of its own."""
        self.doubleClicked(vobj)
        return False

    def dumps(self) -> None:
        return None

    def loads(self, _state: Any) -> None:
        return None


def is_cut(obj: Any) -> bool:
    view = getattr(obj, "ViewObject", None)
    return view is None or isinstance(getattr(view, "Proxy", None),
                                      ViewProviderCut)


def section_of(cut: Any) -> Any:
    """The section whose exact cut this is, or None."""
    return next((o for o in cut.InList
                 if is_section(o) and getattr(o, "Cut", None) is cut), None)


def group(doc: Any) -> Any:
    """The document's Sections group, made on first use."""
    found = doc.getObject(GROUP_NAME)
    if found is None:
        found = doc.addObject("App::DocumentObjectGroup", GROUP_NAME)
        found.Label = GROUP_NAME
    return found


def create(doc: Any, normal: Any, point: Any, x_axis: Any) -> Any:
    """A new section object in the Sections group, visible."""
    obj = doc.addObject("App::FeaturePython", SECTION_NAME)
    SectionPlane(obj)
    obj.Base, obj.Normal, obj.XAxis = point, normal, x_axis
    if obj.ViewObject is not None:
        ViewProviderSection(obj.ViewObject)
    group(doc).addObject(obj)
    return obj


def is_section(obj: Any) -> bool:
    return isinstance(getattr(obj, "Proxy", None), SectionPlane)


def shown(obj: Any) -> bool:
    view = getattr(obj, "ViewObject", None)
    return bool(view is not None and view.Visibility)


def sections(doc: Any) -> list[Any]:
    return [o for o in doc.Objects if is_section(o)]


def sync(obj: Any) -> None:
    """Cut the view while the section's eye is open; stop when shut."""
    from . import section_view
    try:
        doc = obj.Document
    except Exception:            # deleted meanwhile
        return
    if not shown(obj):
        section_view.stop(obj)
        return
    if section_view.running(obj):
        return
    others = [o for o in sections(doc)
              if o is not obj and section_view.running(o)]
    if len(others) >= LIMIT:
        App.Console.PrintWarning(
            "Nxt: at most %d section(s) can cut the view at once; hide "
            "%s first\n" % (LIMIT, ", ".join(o.Label for o in others)))
        obj.ViewObject.Visibility = False
        return
    section_view.start(obj, editing=False)


def edit(obj: Any) -> None:
    """Open a section for editing, turning it on if it is off."""
    from . import section_view
    if not shown(obj):
        obj.ViewObject.Visibility = True
    if not section_view.running(obj):
        sync(obj)
    section_view.edit(obj)
