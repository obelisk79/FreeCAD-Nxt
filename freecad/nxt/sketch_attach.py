"""A new sketch on three picked points, without the attachment dialog.

FreeCAD's New Sketch skips its attachment dialog for one preselected
face or plane. Given three points, or a straight edge and a point, it
fills the dialog in with them and waits to be told the mode. Those
selections say "plane by 3 points" as plainly as a face says "on this
face", so this answers the dialog for the user: it sets that mode and
presses the dialog's own OK, which is what commits the sketch and opens
it for editing.

The dialog is left up, as FreeCAD leaves it for a face, when Shift is
held or PartDesign's "NewSketchUseAttachmentDialog" preference is on -
and whenever the mode would not work: a curved edge, or points in line.
"""

from __future__ import annotations

import traceback
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from .qt import QtCore, QtWidgets
from .tree import settings
from .tree.float_input import task_ok_button

SKETCH = "Sketcher::SketchObject"
#: The attachment mode FreeCAD lists as "Plane by 3 points".
MODE = "ThreePointsPlane"
#: In the class or object name of the attachment task's panel, however
#: this build spells the namespace ("PartGui::" or "PartGui__").
ATTACHER_PANEL = "TaskAttacher"
#: The dialog's OK button can take a moment to be on screen: how often to
#: look for it, in milliseconds, and how many times.
RETRY_MS = 50
RETRIES = 20
PARTDESIGN_PREFERENCES = "User parameter:BaseApp/Preferences/Mod/PartDesign"

#: Datum objects picked whole, with no sub-element to name their kind.
POINTS = ("App::Point", "PartDesign::Point")
LINES = ("App::Line", "PartDesign::Line")
#: The selections answered for: (points, edges).
PLANES = frozenset({(3, 0), (1, 1)})


def _derived(obj: Any, bases: tuple[str, ...]) -> bool:
    return any(obj.isDerivedFrom(base) for base in bases)


def _picked(support: Any) -> tuple[int, int] | None:
    """(points, edges) in an attachment support; None with anything else."""
    points = edges = 0
    for obj, subs in support or ():
        for sub in subs or ("",):
            element = sub.rsplit(".", 1)[-1]
            if element.startswith("Vertex") \
                    or not element and _derived(obj, POINTS):
                points += 1
            elif element.startswith("Edge") \
                    or not element and _derived(obj, LINES):
                edges += 1
            else:
                return None
    return points, edges


def _dialog_asked_for() -> bool:
    """Whether the user wants the attachment dialog whatever is selected."""
    shift = QtCore.Qt.KeyboardModifier.ShiftModifier
    return bool(QtWidgets.QApplication.queryKeyboardModifiers() & shift) \
        or bool(App.ParamGet(PARTDESIGN_PREFERENCES).GetBool(
            "NewSketchUseAttachmentDialog", False))


def _log(why: str) -> None:
    """Why the dialog was left up. Report view, with log messages on."""
    App.Console.PrintLog("Nxt new sketch: %s\n" % why)


def _attacher_ok() -> Any:
    """The open attachment dialog's OK button, or None."""
    for widget in Gui.getMainWindow().findChildren(QtWidgets.QWidget):
        if widget.isVisible() and (
                ATTACHER_PANEL in widget.metaObject().className()
                or ATTACHER_PANEL in widget.objectName()):
            return task_ok_button()
    return None


def _set_mode(sketch: Any) -> bool:
    """Attach the sketch as a plane by 3 points. False, undone, if it fails."""
    before = sketch.MapMode
    if before == MODE:
        return True
    if MODE not in sketch.Attacher.suggestModes()["allApplicableModes"]:
        return False            # a curved edge
    sketch.MapMode = MODE
    sketch.recompute()
    if sketch.isValid():
        return True
    sketch.MapMode = before     # points in line
    sketch.recompute()
    return False


class _Observer:
    def __init__(self, attach: SketchAttach) -> None:
        self._attach = attach

    def slotCreatedObject(self, obj: Any) -> None:  # noqa: N802
        if obj.isDerivedFrom(SKETCH):
            self._attach.created(obj)


class SketchAttach(QtCore.QObject):
    """Answers the attachment dialog a new sketch was created with."""

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._observer = _Observer(self)
        #: The sketch just created: (document, sketch), by name.
        self._created: tuple[str, str] | None = None
        self._tries = 0
        # After the command that made the sketch: its dialog is up by then.
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._answer)

    def install(self) -> None:
        App.addDocumentObserver(self._observer)

    def remove(self) -> None:
        self._timer.stop()
        try:
            App.removeDocumentObserver(self._observer)
        except Exception:
            pass

    def created(self, sketch: Any) -> None:
        if settings.get("AttachSketchByPoints"):
            self._created = (sketch.Document.Name, sketch.Name)
            self._tries = 0
            self._timer.start(0)

    def _answer(self) -> None:
        created, self._created = self._created, None
        try:
            doc = App.ActiveDocument
            if created is None or doc is None or doc.Name != created[0]:
                return
            sketch = doc.getObject(created[1])
            if sketch is None:
                return
            if _dialog_asked_for():
                return _log("Shift or the preference asks for the dialog")
            picked = _picked(sketch.AttachmentSupport)
            if picked not in PLANES:
                return _log("not three points or an edge and a point: %r"
                            % (picked,))
            ok = _attacher_ok()
            if ok is None:
                self._tries += 1
                if self._tries > RETRIES:
                    return _log("no attachment dialog with an OK to press")
                self._created = created
                return self._timer.start(RETRY_MS)
            if not _set_mode(sketch):
                return _log("plane by 3 points does not fit the selection")
            ok.click()
        except Exception:
            App.Console.PrintError(
                "Nxt: could not attach the new sketch by its points\n")
            App.Console.PrintError(traceback.format_exc())
