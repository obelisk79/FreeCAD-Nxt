"""Stand-ins for FreeCAD and FreeCADGui, shared by the tests.

    import fakes
    App, Gui = fakes.install()

Install before importing Nxt: its modules import FreeCAD at load time.
"""

from __future__ import annotations

import math
import sys
import types
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def console() -> types.SimpleNamespace:
    def quiet(*_args: Any, **_kwargs: Any) -> None:
        return None

    return types.SimpleNamespace(PrintError=quiet, PrintWarning=quiet,
                                 PrintMessage=quiet, PrintLog=quiet)


class Params:
    """A parameter group: Get* reads `store` or the default, Set* writes."""

    def __init__(self, store: dict[str, Any]) -> None:
        self.store = store

    def __getattr__(self, name: str) -> Callable[..., Any]:
        if name.startswith("Get"):
            return lambda key, default=None: self.store.get(key, default)
        if name.startswith("Set"):
            return lambda key, value: self.store.__setitem__(key, value)
        raise AttributeError(name)


def params(store: dict[str, Any] | None = None) -> Callable[[str], Params]:
    """A ParamGet whose groups all share `store`."""
    shared = {} if store is None else store
    return lambda _group: Params(shared)


def install(**app: Any) -> tuple[Any, Any]:
    """FreeCAD and FreeCADGui modules, made once per process.

    Keyword arguments are set on FreeCAD, replacing what is there.
    """
    fc = sys.modules.setdefault("FreeCAD", types.ModuleType("FreeCAD"))
    gui = sys.modules.setdefault("FreeCADGui",
                                 types.ModuleType("FreeCADGui"))
    if not hasattr(fc, "Console"):
        fc.Console = console()
    if not hasattr(fc, "ParamGet"):
        fc.ParamGet = params()
    for name, value in app.items():
        setattr(fc, name, value)
    return fc, gui


# --- document objects ------------------------------------------------------ #


class Quantity:
    def __init__(self, text: str) -> None:
        self.UserString = text


class Vector:
    def __init__(self, x: float = 0, y: float = 0, z: float = 0) -> None:
        self.x, self.y, self.z = x, y, z

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Vector) and (
            (self.x, self.y, self.z) == (other.x, other.y, other.z))


class Rotation:
    def __init__(self, axis: Vector, angle_degrees: float) -> None:
        self.Axis = axis
        self.Angle = math.radians(angle_degrees)


class Placement:
    def __init__(self) -> None:
        self.Base = Vector(1, 2, 3)
        self.Rotation = Rotation(Vector(0, 0, 1), 90)


class Document:
    """Records transactions and recomputes in `log`."""

    def __init__(self) -> None:
        self.log: list[str] = []

    def openTransaction(self, name: str) -> None:
        self.log.append("open " + name)

    def commitTransaction(self) -> None:
        self.log.append("commit")

    def abortTransaction(self) -> None:
        self.log.append("abort")

    def recompute(self) -> None:
        self.log.append("recompute")


class Thing:
    """A document object: properties with a group, a kind and modes."""

    def __init__(self, type_id: str, props: dict[str, tuple[str, str, Any]],
                 modes: dict[str, list[str]] | None = None,
                 document: Document | None = None) -> None:
        self.TypeId = type_id
        self.Label = type_id.split("::")[-1]
        self.Name = self.Label
        self.Document = document or Document()
        self._props = props
        self._modes = modes or {}
        self.PropertiesList = list(props)
        self.ExpressionEngine: list[tuple[str, str]] = []
        for name, (_group, _type, value) in props.items():
            setattr(self, name, value)

    def getGroupOfProperty(self, prop: str) -> str:
        return self._props[prop][0]

    def getTypeIdOfProperty(self, prop: str) -> str:
        return self._props[prop][1]

    def getEditorMode(self, prop: str) -> list[str]:
        return self._modes.get(prop, [])

    def getDocumentationOfProperty(self, prop: str) -> str:
        return "about " + prop

    def getEnumerationsOfProperty(self, prop: str) -> list[str]:
        return ["Dimension", "ThroughAll"]

    def evalExpression(self, text: str) -> float:  # noqa: N802
        """Every expression reads: tests that need one to fail replace it."""
        return 0.0

    def setExpression(self, prop: str, expression: str | None) -> None:
        self.ExpressionEngine = [e for e in self.ExpressionEngine
                                 if e[0] != prop]
        if expression is not None:
            self.ExpressionEngine.append((prop, expression))


def helix(**overrides: Any) -> Thing:
    props = {
        "Label": ("Base", "App::PropertyString", "Helix"),
        "Placement": ("Base", "App::PropertyPlacement", Placement()),
        "Pitch": ("Helix", "App::PropertyLength", Quantity("5.00 mm")),
        "Height": ("Helix", "App::PropertyLength", Quantity("40.00 mm")),
        "LocalCoord": ("Helix", "App::PropertyEnumeration", "Dimension"),
        "Visible2": ("Helix", "App::PropertyBool", True),
        "Secret": ("Helix", "App::PropertyFloat", 1.0),
    }
    props.update(overrides)
    return Thing("Part::Helix", props, {"Secret": ["Hidden"]})
