"""A stand-in sketch in edit, for the sketch task panel's tests."""

from __future__ import annotations

import types
from typing import Any

#: Sketcher's "no geometry" index in a constraint.
UNSET = -2000


class LineSegment:
    """Named as Part's class is: the panel reads the name."""


class Circle:
    """Named as Part's class is."""


class Constraint:
    def __init__(self, kind: str, first: int, second: int = UNSET,
                 value: float = 0.0, name: str = "") -> None:
        self.Type, self.Value, self.Name = kind, value, name
        self.First, self.Second, self.Third = first, second, UNSET
        self.Driving, self.IsActive = True, True


class Document:
    Name = "Unnamed"

    def __init__(self) -> None:
        self.steps: list[str] = []

    def openTransaction(self, name: str) -> None:
        self.steps.append(name)

    def commitTransaction(self) -> None:
        self.steps.append("commit")

    def abortTransaction(self) -> None:
        self.steps.append("abort")


class Sketch:
    """Three lines and a circle; constraint 2 is a named distance."""

    Name = "Sketch"

    def __init__(self) -> None:
        self.Document = Document()
        self.Geometry: list[Any] = [LineSegment(), LineSegment(),
                                    LineSegment(), Circle()]
        self.Constraints = [Constraint("Horizontal", 0),
                            Constraint("Distance", 1, value=32.0,
                                       name="Width"),
                            Constraint("Coincident", 0, 1),
                            Constraint("PointOnObject", 3, 2)]
        self.construction = {3}
        self.DoF = 3
        self.ConflictingConstraints: list[int] = []
        self.RedundantConstraints: list[int] = []
        self.MalformedConstraints: list[int] = []
        self.PartiallyRedundantConstraints: list[int] = []
        self.solved = 0
        self.ViewObject = types.SimpleNamespace(
            Object=self, ShowGrid=True, GridAuto=True, Autoconstraints=True,
            GridSize=types.SimpleNamespace(UserString="10.00 mm"))

    @property
    def GeometryCount(self) -> int:
        return len(self.Geometry)

    @property
    def ConstraintCount(self) -> int:
        return len(self.Constraints)

    def isDerivedFrom(self, type_id: str) -> bool:
        return type_id == "Sketcher::SketchObject"

    def getDatum(self, index: int) -> Any:
        return types.SimpleNamespace(
            UserString="%.2f mm" % self.Constraints[index].Value)

    def getConstruction(self, geo: int) -> bool:
        return geo in self.construction

    def setConstruction(self, geo: int, on: bool) -> None:
        (self.construction.add if on else self.construction.discard)(geo)

    def solve(self) -> int:
        self.solved += 1
        return 0

    def getGeoVertexIndex(self, vertex: int) -> tuple[int, int]:
        return vertex // 2, 1 + vertex % 2

    def delConstraint(self, index: int) -> None:
        del self.Constraints[index]

    def setActive(self, index: int, on: bool) -> None:
        self.Constraints[index].IsActive = on

    def setDriving(self, index: int, on: bool) -> None:
        self.Constraints[index].Driving = on

    def renameConstraint(self, index: int, name: str) -> None:
        self.Constraints[index].Name = name
