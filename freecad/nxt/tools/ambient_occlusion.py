"""Real-time ambient occlusion in every 3D view (setting: AmbientOcclusion).

The effect's node tree (ao_pipeline.py) sits right after the selection
root of each view. A poll keeps it in line with what cannot be observed
from Python (the view's size, its camera node), rebuilding only when its
signature changes; document signals mark the model's mirror and the
automatic radius stale. A sensor on each camera pauses the effect, or
drops it to its Interactive level, while the view is navigated.

The depth pass draws the view providers' roots (a "mirror" group per
document), never FreeCAD's on-top or editing roots: see ao_pipeline.py.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from ..core import log, settings
from ..core.qt import QtCore
from . import ao_pipeline, ao_temporal

VIEW_TYPE = "Gui::View3DInventor"
SELECTION_ROOT = "SoFCUnifiedSelection"
#: Children of the selection root that are not the model: the first holds
#: nodes that queue paths for after the frame, fatal in a scene texture.
NOT_MODEL_NAMES = frozenset({"GroupOnTop", "EditingRoot", "RootDimensions"})
NOT_MODEL_TYPES = frozenset({"EventCallback", "TransformSeparator",
                             "Environment", "DirectionalLight", "PointLight",
                             "SpotLight"})
#: FreeCAD 1.2+ keeps the view providers in a group of their own.
OBJECT_GROUP = "ObjectGroup"
#: What a view's size, camera and model are checked for, in ms.
POLL_MS = 400
#: The setting AOSpread is a percentage of the model's diagonal.
PERCENT = 100.0
#: Properties whose change moves the model's bounding box.
GEOMETRY_PROPERTIES = frozenset({"Shape", "Placement", "Visibility", "Mesh",
                                 "Points"})
#: Camera fields that navigation changes; clipping planes are refitted
#: by FreeCAD on model edits and do not count.
POSE_FIELDS = ("height", "heightAngle")
POSE_DIGITS = 6

#: AOWhileNavigating's values: keep the effect, use the Interactive level,
#: or switch it off until the camera has been still for AOResumeDelay.
KEEP, REDUCE, PAUSE = "keep", "reduce", "pause"
NAVIGATION = (KEEP, REDUCE, PAUSE)
QUALITIES = ("low", "medium", "high")


def display(mode: str, moving: bool) -> tuple[bool, int]:
    """Whether the effect shows, and at which level, for a camera state."""
    if moving and mode == PAUSE:
        return False, 0
    return True, 1 if moving and mode == REDUCE else 0


def diagonal(box: tuple[float, ...] | None) -> float:
    """The length of the diagonal of bounding `box`; 0 when there is none."""
    if box is None:
        return 0.0
    low, high = box[:3], box[3:]
    return float(sum((b - a) ** 2 for a, b in zip(low, high)) ** 0.5)


def auto_radius(length: float, spread: float) -> float:
    """The radius: `spread` percent of a model's diagonal `length`.

    Two significant digits, so small edits keep the same effect.
    """
    radius = length * spread / PERCENT
    return float("%.1e" % radius) if radius > 0 else 0.0


def look(get: Callable[[str], Any], radius: float) -> ao_pipeline.Look:
    """The effect as the settings ask for it and this system can show."""
    quality = str(get("AOQuality"))
    return ao_pipeline.Look(
        quality=quality if quality in QUALITIES else "medium",
        intensity=float(get("AOIntensity")),
        radius=radius,
        temporal=bool(get("AOTemporal")) and ao_temporal.available())


def address(node: Any) -> int:
    """The Coin node's C++ address: tells whether two wrappers match."""
    if node is None:
        return 0
    try:
        return int(node.this)
    except (AttributeError, TypeError, ValueError):
        return id(node)


def _type_name(node: Any) -> str:
    return str(node.getTypeId().getName().getString())


def _views() -> list[tuple[Any, Any]]:
    """(document, 3D view) for every 3D view of every open document."""
    views: list[tuple[Any, Any]] = []
    for name in App.listDocuments():
        doc = App.getDocument(name)
        with contextlib.suppress(Exception):
            gui_doc = Gui.getDocument(name)
            views.extend((doc, view)
                         for view in gui_doc.mdiViewsOfType(VIEW_TYPE))
    return views


def _selection_and_parent(view: Any) -> tuple[Any, Any]:
    """The view's selection root and the group holding it, or Nones."""
    from pivy import coin
    scene = view.getSceneGraph()
    root = scene
    if _type_name(scene) == SELECTION_ROOT:
        root = view.getViewer().getSoRenderManager().getSceneGraph()
    search = coin.SoSearchAction()
    search.setType(coin.SoType.fromName(SELECTION_ROOT))
    search.setInterest(coin.SoSearchAction.FIRST)
    search.apply(root)
    path = search.getPath()
    if path is None or path.getLength() < 2:
        return None, None
    return path.getTail(), path.getNodeFromTail(1)


def _model_roots(selection: Any) -> list[Any]:
    roots = []
    for i in range(selection.getNumChildren()):
        child = selection.getChild(i)
        name = child.getName().getString()
        if name == OBJECT_GROUP:
            roots.extend(_model_roots(child))
        elif (name not in NOT_MODEL_NAMES
              and _type_name(child) not in NOT_MODEL_TYPES):
            roots.append(child)
    return roots


def _viewport(view: Any) -> tuple[int, int]:
    region = view.getViewer().getSoRenderManager().getViewportRegion()
    width, height = region.getViewportSizePixels()
    return int(width), int(height)


def _pose(camera: Any) -> tuple[float, ...]:
    from pivy import coin
    values = list(camera.position.getValue().getValue())
    values += list(camera.orientation.getValue().getValue())
    for name in POSE_FIELDS:
        field = camera.getField(name)
        if field is not None:
            values.append(coin.cast(field, "SoSFFloat").getValue())
    return tuple(round(value, POSE_DIGITS) for value in values)


class Mirror:
    """The view provider roots of one document, as one group to draw."""

    def __init__(self) -> None:
        from pivy import coin
        self.group = coin.SoGroup()
        self.group.ref()
        self.stale = True
        #: The model's diagonal, measured once until the model changes.
        self.diagonal: float | None = None

    def refresh(self, selection: Any) -> None:
        roots = _model_roots(selection)
        current = [self.group.getChild(i)
                   for i in range(self.group.getNumChildren())]
        if [address(n) for n in current] != [address(n) for n in roots]:
            self.group.removeAllChildren()
            for node in roots:
                self.group.addChild(node)
        self.stale = False

    def measured_diagonal(self, view: Any) -> float:
        if self.diagonal is None:
            from pivy import coin
            width, height = _viewport(view)
            action = coin.SoGetBoundingBoxAction(
                coin.SbViewportRegion(max(width, 1), max(height, 1)))
            action.apply(self.group)
            box = action.getBoundingBox()
            corners = None if box.isEmpty() else (
                *box.getMin().getValue(), *box.getMax().getValue())
            self.diagonal = diagonal(corners)
        return self.diagonal

    def release(self) -> None:
        self.group.removeAllChildren()
        self.group.unref()


class ViewResources:
    """The GL helpers of one view, lent to each rebuild of its effect."""

    def __init__(self) -> None:
        self.accumulators: dict[str, ao_temporal.Accumulator] = {}

    def accumulator(self, level: str) -> ao_temporal.Accumulator:
        return self.accumulators.setdefault(level,
                                            ao_temporal.Accumulator())

    def release(self) -> None:
        for accumulator in self.accumulators.values():
            accumulator.release()


class ViewState:
    """The effect in one view, and the camera it follows."""

    def __init__(self, view: Any, owner: AmbientOcclusion) -> None:
        from pivy import coin
        self.view = view
        self.owner = owner
        self.resources = ViewResources()
        self.root: Any = None
        self.parent: Any = None
        self.camera = 0
        self.pose: tuple[float, ...] | None = None
        self.moving = False
        self.sensor = coin.SoNodeSensor(self._camera_changed, None)
        self.resume = QtCore.QTimer(owner)
        self.resume.setSingleShot(True)
        self.resume.timeout.connect(self._stopped)

    def follow(self, camera: Any) -> None:
        if address(camera) == self.camera:
            return
        self.sensor.detach()
        self.camera = address(camera)
        self.pose = _pose(camera)
        self.sensor.attach(camera)

    def _camera_changed(self, data: Any, sensor: Any) -> None:
        pose = _pose(sensor.getAttachedNode())
        if pose == self.pose:
            return
        self.pose = pose
        mode = str(settings.get("AOWhileNavigating"))
        if mode == KEEP:
            return
        self.resume.start(int(settings.get("AOResumeDelay")))
        if not self.moving:
            self.moving = True
            self.show()

    def _stopped(self) -> None:
        self.moving = False
        self.show()

    def show(self) -> None:
        """Put the effect's switches in the state the camera asks for."""
        if self.root is None:
            return
        on, level = display(str(settings.get("AOWhileNavigating")),
                            self.moving)
        from pivy import coin
        switch = ao_pipeline.find(self.root, ao_pipeline.SWITCH_NAME)
        levels = ao_pipeline.find(switch, ao_pipeline.LEVEL_NAME)
        shown = coin.SO_SWITCH_ALL if on else coin.SO_SWITCH_NONE
        if switch.whichChild.getValue() != shown:
            switch.whichChild = shown
        if levels.whichChild.getValue() != level:
            levels.whichChild = level

    def place(self, root: Any, parent: Any) -> None:
        self.take_down()
        root.ref()
        parent.addChild(root)
        self.root, self.parent = root, parent
        self.show()

    def take_down(self, view_alive: bool = True) -> None:
        """Take the effect out of the view, and let go of it.

        A closed view's scene graph is already freed: touching its
        group crashes FreeCAD, so only our own reference is dropped.
        """
        if self.root is None:
            return
        if view_alive:
            index = self.parent.findChild(self.root)
            if index >= 0:
                self.parent.removeChild(index)
        self.root.unref()
        self.root = self.parent = None

    def release(self, view_alive: bool) -> None:
        self.resume.stop()
        self.sensor.detach()
        self.take_down(view_alive)
        self.resources.release()


class _Observer:
    """Document signals that make the mirrors or radii stale."""

    def __init__(self, owner: AmbientOcclusion) -> None:
        self.owner = owner

    def slotCreatedObject(self, obj: Any) -> None:  # noqa: N802
        self.owner.stale(obj.Document.Name)

    def slotDeletedObject(self, obj: Any) -> None:  # noqa: N802
        self.owner.stale(obj.Document.Name)

    def slotChangedObject(self, obj: Any, prop: str) -> None:  # noqa: N802
        if prop in GEOMETRY_PROPERTIES:
            self.owner.moved(obj.Document.Name)

    def slotUndoDocument(self, doc: Any) -> None:  # noqa: N802
        self.owner.stale(doc.Name)

    def slotRedoDocument(self, doc: Any) -> None:  # noqa: N802
        self.owner.stale(doc.Name)

    def slotFinishRestoreDocument(self, doc: Any) -> None:  # noqa: N802
        self.owner.stale(doc.Name)

    def slotDeletedDocument(self, doc: Any) -> None:  # noqa: N802
        self.owner.forget(doc.Name)


class AmbientOcclusion(QtCore.QObject):
    """The effect in every 3D view, for as long as it is switched on."""

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self.mirrors: dict[str, Mirror] = {}
        self.views: dict[int, ViewState] = {}
        self.observer: _Observer | None = None
        #: Views whose update failed once: reported, not every poll.
        self.failed: set[int] = set()
        self.poll = QtCore.QTimer(self)
        self.poll.setInterval(POLL_MS)
        self.poll.timeout.connect(self.sync)

    def install(self) -> None:
        self.observer = _Observer(self)
        App.addDocumentObserver(self.observer)
        self.poll.start()
        self.sync()

    def remove(self) -> None:
        self.poll.stop()
        if self.observer is not None:
            with contextlib.suppress(Exception):
                App.removeDocumentObserver(self.observer)
            self.observer = None
        for state in self.views.values():
            state.release(view_alive=True)
        for mirror in self.mirrors.values():
            mirror.release()
        self.views.clear()
        self.mirrors.clear()

    def stale(self, doc_name: str) -> None:
        mirror = self.mirrors.get(doc_name)
        if mirror is not None:
            mirror.stale = True
            mirror.diagonal = None

    def moved(self, doc_name: str) -> None:
        mirror = self.mirrors.get(doc_name)
        if mirror is not None:
            mirror.diagonal = None

    def forget(self, doc_name: str) -> None:
        mirror = self.mirrors.pop(doc_name, None)
        if mirror is not None:
            mirror.release()

    def sync(self) -> None:
        """Bring every 3D view's effect in line with the settings."""
        # FreeCAD hands out Coin nodes only once pivy is loaded ("No SWIG
        # wrapped library loaded"); FreeCAD 1.1 may not have loaded it yet.
        from pivy import coin  # noqa: F401
        seen = set()
        for doc, view in _views():
            key = 0
            try:
                key = address(view.getSceneGraph())
                seen.add(key)
                self._sync_view(doc, view, key)
            except Exception:  # noqa: BLE001 - one view must not stop all
                if key not in self.failed:
                    self.failed.add(key)
                    log.error("could not update the ambient occlusion")
        for key in set(self.views) - seen:
            self.views.pop(key).release(view_alive=False)

    def _sync_view(self, doc: Any, view: Any, key: int) -> None:
        selection, parent = _selection_and_parent(view)
        if selection is None:
            return
        mirror = self.mirrors.get(doc.Name)
        if mirror is None:
            mirror = self.mirrors[doc.Name] = Mirror()
        if mirror.stale:
            mirror.refresh(selection)
        state = self.views.get(key)
        if state is not None and state.root is not None and address(
                state.parent) != address(parent):
            # a closed view's memory reused by a new one: the old group
            # is gone with the old view
            state.release(view_alive=False)
            state = None
        if state is None:
            state = self.views[key] = ViewState(view, self)
        camera = view.getCameraNode()
        state.follow(camera)
        width, height = _viewport(view)
        radius = float(settings.get("AORadius")) or auto_radius(
            mirror.measured_diagonal(view), float(settings.get("AOSpread")))
        if radius <= 0 or width < ao_pipeline.MIN_TEXTURE:
            state.take_down()
            return
        wanted = look(settings.get, radius)
        signed = ao_pipeline.signature(width, height, address(camera),
                                       address(mirror.group), wanted)
        if (state.root is not None
                and ao_pipeline.current_signature(state.root) == signed):
            return
        state.place(ao_pipeline.build(width, height, camera, mirror.group,
                                      wanted, state.resources, signed),
                    parent)
