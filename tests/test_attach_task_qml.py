"""AttachTask.qml, loaded offscreen against a stub bridge.

Checks it loads cleanly in each state, and that its controls reach the
bridge.

Run with: python3 tests/test_attach_task_qml.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import fakes  # noqa: E402
from PySide6 import QtCore, QtGui, QtQuick  # noqa: E402

App, Gui = fakes.install(ParamGet=fakes.params({}))

from freecad.nxt.core import settings  # noqa: E402
from freecad.nxt.ui.theme import Theme  # noqa: E402

QML = ROOT / "freecad" / "nxt" / "resources" / "qml"
BAD = ("binding loop", "is not defined", "cannot read property",
       "unable to assign", "typeerror", "referenceerror", "cannot assign",
       "is not a function", "required property")
problems: list[str] = []


def _handler(_mode: object, _context: object, message: str) -> None:
    print(message)
    if any(token in str(message).lower() for token in BAD):
        problems.append(str(message))


QtCore.qInstallMessageHandler(_handler)
app = QtGui.QGuiApplication(sys.argv)
calls: list[tuple[str, object]] = []

ATTACHED: dict[str, Any] = {
    "attached": True, "picking": False, "hint": "",
    "references": [{"word": "Curve", "shape": "curve",
                    "text": "Path · Edge1", "faulty": False}],
    "problem": "", "fix": "", "wayLabel": "Along path", "choice": "Plane",
    "variants": [{"value": "FrenetNB", "label": "Across"},
                 {"value": "FrenetTN", "label": "In bend"},
                 {"value": "FrenetTB", "label": "Beside"}],
    "variant": "FrenetNB", "flipped": False, "alongPath": True,
    "pathText": "0.35",
    "offset": ["12 mm", "0 mm", "15 mm", "0 °", "0 °", "30 °"],
    "offsetUsed": True, "turns": True,
}
EMPTY = dict(ATTACHED, attached=False, picking=True, references=[],
             wayLabel="", variants=[], alongPath=False, offsetUsed=False)
FAULTY = dict(ATTACHED, attached=False, problem="These points are in a "
              "line, so no plane fits.", fix="Pick a point off the line.",
              references=[{"word": "Line", "shape": "edge",
                           "text": "Pad · Edge4", "faulty": False},
                          {"word": "Point", "shape": "point",
                           "text": "Pad · Vertex2", "faulty": True}])


class Stub(QtCore.QObject):
    changed = QtCore.Signal()

    def __init__(self) -> None:
        super().__init__()
        self.state = dict(ATTACHED)

    def show(self, state: dict[str, Any]) -> None:
        self.state = dict(state)
        self.changed.emit()


def _value(name: str, kind: type) -> object:
    return QtCore.Property(kind, lambda self: self.state[name],
                           notify=Stub.changed)


def _slot(name: str, *kinds: type, result: type | None = None) -> object:
    def record(_self: object, *args: object) -> object:
        calls.append((name, args))
        return True if result is bool else None
    if result is None:
        return QtCore.Slot(*kinds)(record)
    return QtCore.Slot(*kinds, result=result)(record)


for key, value in ATTACHED.items():
    setattr(Stub, key, _value(key, type(value)))
for name, kinds, result in (
        ("pick", (), None), ("stopPicking", (), None),
        ("removeReference", (int,), None), ("chooseVariant", (str,), None),
        ("setFlipped", (bool,), None), ("setPath", (str,), bool),
        ("setOffset", (int, str), bool), ("resetOffset", (), None),
        ("detach", (), None),
        ("openWays", (float, float, float), None)):
    setattr(Stub, name, _slot(name, *kinds, result=result))

attach = Stub()
view = QtQuick.QQuickView()
view.engine().addImportPath(str(QML))
view.rootContext().setContextProperty("theme", Theme())
view.rootContext().setContextProperty("attach", attach)
view.setResizeMode(QtQuick.QQuickView.ResizeMode.SizeRootObjectToView)
view.resize(340, 700)
view.setSource(QtCore.QUrl.fromLocalFile(str(QML / "AttachTask.qml")))
problems += [e.toString() for e in view.errors()]
view.show()


def settle() -> None:
    for _ in range(20):
        app.processEvents()


def find(text: str) -> Any:
    """The first visible item showing `text`."""
    def walk(item: Any) -> Any:
        if item.property("text") == text and item.isVisible():
            return item
        for child in item.childItems():
            found = walk(child)
            if found is not None:
                return found
        return None
    return walk(view.rootObject())


def check(label: str, ok: bool) -> None:
    print(("ok   " if ok else "FAIL ") + label)
    if not ok:
        problems.append(label)


settle()
root = view.rootObject()
check("the panel loads", root is not None)
heights = {}
for name, state in (("attached", ATTACHED), ("empty", EMPTY),
                    ("faulty", FAULTY)):
    attach.show(state)
    settle()
    heights[name] = root.property("implicitHeight")
    check("the %s panel has a height" % name, heights[name] > 0)

attach.show(EMPTY)
settle()
check("an empty panel listens for a pick",
      find("Pick a face, edge or point") is not None)
check("an empty panel hides the offset", find("Offset") is None)
attach.show(ATTACHED)
settle()
check("an attached panel shows the way", find("Along path") is not None)
check("a used offset opens with its fields", find("Move") is not None)
check("the setting starts off", settings.DEFAULTS["AttachPanel"] is False)

print("ATTACH TASK QML PASSED" if not problems else "ATTACH TASK QML FAILED")
for p in problems:
    print("  *", p)
sys.exit(1 if problems else 0)
