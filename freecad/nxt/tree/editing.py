"""Opening a feature for editing, the way FreeCAD's own tree does.

Shared by everything that starts an edit - a row double-clicked in the
panel, a face double-clicked in the 3D view - so the undo behaviour is the
same whichever started it and whether or not the panel is open.
"""

from __future__ import annotations

import traceback
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

ORIGIN = "App::Origin"
ORIGIN_FEATURE = "App::OriginFeature"
#: Datum planes, lines and points: Part Design's (Part::Datum) and the
#: Part workbench's (App::DatumElement). The origin's own planes, axes
#: and point are DatumElements too, and are not attached to anything.
DATUMS = ("Part::Datum", "App::DatumElement")


def object_in(doc_name: str, name: str) -> Any:
    """The named object of an open document, or None."""
    try:
        return Gui.getDocument(doc_name).Document.getObject(name)
    except Exception:
        return None


def is_datum(obj: Any) -> bool:
    """A datum plane, line or point that can be attached."""
    try:
        return (any(obj.isDerivedFrom(t) for t in DATUMS)
                and not obj.isDerivedFrom(ORIGIN_FEATURE)
                and hasattr(obj, "MapMode"))
    except Exception:
        return False


def edit_attachment(doc_name: str, name: str) -> None:
    """Open the attachment dialog for a datum.

    FreeCAD's own Attachment editor (Part's AttachmentEditor), which
    opens its own undo step and closes it on OK or Cancel. Failing that,
    the Part workbench's command, on the datum as the selection.

    Call it deferred, as enter_edit: it opens a task dialog.
    """
    gui_doc = Gui.getDocument(doc_name)
    obj = gui_doc.Document.getObject(name) if gui_doc else None
    if obj is None:
        return
    if gui_doc.getInEdit() is not None:
        gui_doc.resetEdit()
    try:
        from AttachmentEditor import Commands
        Commands.editAttachment(obj, take_selection=False,
                                create_transaction=True)
        return
    except Exception:
        App.Console.PrintLog("Nxt: AttachmentEditor not usable: %s\n"
                             % traceback.format_exc())
    try:
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc_name, name)
        Gui.runCommand("Part_EditAttachment", 0)
    except Exception:
        App.Console.PrintError("Nxt: could not open the attachment of %s\n"
                               % name)
        App.Console.PrintError(traceback.format_exc())


def is_reference_pick(obj: Any) -> bool:
    """Whether a click on `obj` is a reference being picked.

    True for an origin plane, axis or point while a task panel is open:
    the task (attaching a sketch or a datum) is being given it, so the
    click neither opens, edits nor reveals anything.
    """
    try:
        if obj is None or not Gui.Control.activeDialog():
            return False
        return bool(obj.isDerivedFrom(ORIGIN_FEATURE)) or any(
            parent.isDerivedFrom(ORIGIN) for parent in obj.InList)
    except Exception:
        return False


def open_edit_transaction(obj: Any) -> bool:
    """Open the undo step an edit of `obj` runs in. True if one was opened.

    None is opened when one is already active: whatever opened it owns it.
    """
    try:
        if App.getActiveTransaction():
            return False
        # Kept open past this event (persist): the task closes it.
        App.setActiveTransaction("Edit %s" % obj.Label, True)
        return True
    except Exception:
        return False


def enter_edit(doc_name: str, name: str, handles: bool = True) -> None:
    """Edit an object, inside an undo step of its own.

    FreeCAD's tree opens a transaction before it edits; Part Design's task
    commits it on OK and aborts it on Cancel, which is what puts the model
    back as it was and what Ctrl+Z undoes afterwards. setEdit alone opens
    none, so an edit begun from Nxt could be neither cancelled nor undone.

    `handles` False opens the edit without the 3D drag handles (see
    gizmos.hidden): for an edit begun from the tree, when asked for.

    Call it deferred, never from inside an input event: setEdit opens a
    task dialog, which nests an event loop and can tear down whatever
    widget the event was delivered to.
    """
    opened = False
    try:
        gui_doc = Gui.getDocument(doc_name)
        obj = gui_doc.Document.getObject(name)
        if obj is None:
            return
        if gui_doc.getInEdit() is not None:
            gui_doc.resetEdit()
        opened = open_edit_transaction(obj)
        if handles:
            gui_doc.setEdit(obj)
        else:
            from . import gizmos
            with gizmos.hidden():
                gui_doc.setEdit(obj)
        if gui_doc.getInEdit() is None and opened:
            App.closeActiveTransaction(True)    # nothing was edited
    except Exception:
        if opened:
            App.closeActiveTransaction(True)
        App.Console.PrintError("Nxt: could not open %s for editing\n" % name)
        App.Console.PrintError(traceback.format_exc())
