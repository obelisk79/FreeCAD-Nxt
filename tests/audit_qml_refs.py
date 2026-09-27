"""Cross-check the QML against the Python it has to call, without any Qt.

    python3 tests/audit_qml_refs.py

Catches the class of break that QML hides until load time: a component
deleted while something still imports it, a `nxt.*` slot renamed on one
side only, a `required property` on TreeRow with no matching model role.
Cheap enough to run on every edit, which is the point - the alternative is
restarting FreeCAD to find out.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QML = ROOT / "freecad" / "nxt" / "resources" / "qml"
PY = ROOT / "freecad" / "nxt" / "tree"
fail = []


def qml_files():
    yield from sorted(QML.rglob("*.qml"))


def strip_comments(text):
    return re.sub(r"//[^\n]*", "", text)


def py_members(path):
    tree = ast.parse(path.read_text())
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.add(node.name)
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    out.add(t.id)
    return out


bridge = py_members(PY / "bridge.py")
theme = py_members(PY / "theme.py")
panel = py_members(PY / "panel.py")

# roleNames -> the properties a delegate may declare
models_src = (PY / "models.py").read_text()
roles = set(re.findall(r':\s*"([A-Za-z]+)",', models_src))

calls = {"nxt": set(), "theme": set(), "host": set()}
components = set()
inline: set[str] = set()
declared = set()
for path in qml_files():
    src = strip_comments(path.read_text())
    for obj in calls:
        calls[obj] |= set(re.findall(r"(?<![A-Za-z0-9_.])" + obj +
                                     r"\.([A-Za-z_][A-Za-z0-9_]*)", src))
    components |= set(re.findall(r"^\s{0,12}([A-Z][A-Za-z]+)\s*\{", src, re.M))
    # Inline components (`component Name: Base`) are declared where used.
    inline |= set(re.findall(r"^\s*component\s+([A-Z]\w*)\s*:", src, re.M))
    if path.name == "TreeRow.qml":
        declared = set(re.findall(r"required property \w+ (\w+)", src))


def check(label, used, have, skip=()):
    missing = sorted(n for n in used if n not in have and n not in skip)
    print("%-28s used %3d  missing: %s"
          % (label, len(used), missing or "none"))
    if missing:
        fail.append(label)


check("nxt.* -> bridge.py", calls["nxt"], bridge)
check("theme.* -> theme.py", calls["theme"], theme)
check("host.* -> panel.py", calls["host"], panel)
check("TreeRow props -> roleNames", declared - {"index", "modelData"}, roles)

# every Nxt component referenced must be registered
registered = set()
for line in (QML / "Nxt" / "qmldir").read_text().splitlines():
    parts = line.split()
    if len(parts) == 3:
        registered.add(parts[0])
builtin = {"Item", "Rectangle", "Text", "TextInput", "Image", "Row", "Column",
           "Flow", "Canvas", "ListView", "Repeater", "MouseArea", "DropArea",
           "HoverHandler", "TapHandler", "Connections", "NumberAnimation",
           "ColorAnimation", "Behavior", "Timer", "Component", "Drag",
           "ListModel", "Keys", "Qt", "Math", "PropertyChanges", "State",
           "TextMetrics", "FontMetrics", "Application", "Flickable",
           # Qt Quick Controls, used by the context menu only.
           "Menu", "MenuItem", "MenuSeparator", "Popup", "Switch",
           "FocusScope"}
unknown = sorted(c for c in components
                 if c not in registered and c not in builtin
                 and c not in inline)
print("%-28s used %3d  unregistered: %s"
      % ("components -> qmldir", len(components), unknown or "none"))
if unknown:
    fail.append("components")

# files registered but absent, and files present but unregistered
present = {path.stem for path in (QML / "Nxt").glob("*.qml")}
print("%-28s registered-but-missing: %s   present-but-unregistered: %s"
      % ("qmldir <-> files", sorted(registered - present) or "none",
         sorted(present - registered) or "none"))
if registered - present or present - registered:
    fail.append("qmldir")

print()
print("AUDIT", "FAILED: " + ", ".join(fail) if fail else "PASSED")
sys.exit(1 if fail else 0)
