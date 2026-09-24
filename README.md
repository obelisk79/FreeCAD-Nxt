# Nxt

A QtQuick model panel for FreeCAD 1.1 and later: the document's history as a
timeline with a draggable rollback bar, Part workbench models as expression
rows with history scrubbing, sketch health at a glance, and a Property Inspector
that makes the Property view optional.

Nxt adds no workbench. Its commands appear at the bottom of the **View** menu
in every workbench.

## Install

With the Addon Manager, once published. By hand, clone or copy this folder
into FreeCAD's `Mod` directory and restart FreeCAD:

```bash
git clone https://github.com/obelisk79/FreeCAD-NXT ~/.local/share/FreeCAD/Mod/FreeCAD-Nxt
```

Nxt needs a Qt 6 build of FreeCAD, as FreeCAD itself now does.

## Layout

The addon follows FreeCAD's namespaced layout from the official
[Addon-Template](https://github.com/FreeCAD/Addon-Template):

```
package.xml, pyproject.toml, LICENSE, README.md
freecad/nxt/
    init_gui.py       icon and language paths, commands, View menu, autostart
    commands.py       Nxt_* commands
    property_inspector.py  the Property Inspector
    qt.py             the Qt binding (FreeCAD's PySide shim) and QtCompat
    qtquick.py        QtQuick, imported only when a QML surface is built
    i18n.py           translate() and QT_TRANSLATE_NOOP
    version.py
    tree/             the model panel (see tree/DESIGN.md)
    resources/        icons/, qml/, translations/ - found via importlib
tests/                one test file per area, see Development
```

## Commands

| Command | Where | What |
|---|---|---|
| `Nxt_ModelPanel` | View menu | show or hide the model panel |
| `Nxt_ModelPanelOverlay` | View menu | draw the panel as floating labels |
| `Nxt_PropertyInspector` | View menu | the selection's properties in an inspector |
| `Nxt_Reload` | console | hot-reload the addon's Python modules |

```python
Gui.runCommand("Nxt_Reload")
```

## Development

```bash
python3 tests/test_scene.py        # snapshot logic, no FreeCAD needed
python3 tests/audit_qml_refs.py    # QML <-> Python name agreement
python3 tests/test_qml.py          # offscreen QML load; needs PySide6
python3 tests/test_properties.py   # the detail strip's key values
python3 tests/test_property_inspector.py  # borrowing the Property editor; PySide6
python3 tests/test_inspector.py    # the inspector's automatic layout
python3 tests/test_inspector_qml.py  # the inspector's QML; PySide6
python3 tests/test_selection_keys.py # Space, arrows, Shift+click; PySide6
ruff check . && pycodestyle freecad tests && mypy
```

User-facing text is translatable (see
`freecad/nxt/resources/translations/README.md`). Code follows PEP 8 and
PEP 257 and is fully type-hinted, with
`from __future__ import annotations` in every module. Ruff and mypy are
configured in `pyproject.toml`. Qt and FreeCAD API names (`GetResources`,
slots, properties) keep their framework spelling, as PEP 8 allows.

## The model panel

In `freecad/nxt/tree/`. It replaces the stock tree
view with a hierarchy that keeps its collapsible structure but draws a
container's children **in the order they were made**, lifting whatever an
operation reads out of that operation so it stands beside it:

```
Body
  Sketch          drawn first
  Pad             consumes Sketch
  Sketch001       drawn on the face the Pad made
  Pocket          consumes Sketch001
```

The stock tree buries a sketch under whichever feature consumed it first. A
sketch driving a Pad, a Pocket and a Pipe appears once, under the Pad, and is
invisible from the other two - and filing it at the point of first use hides
when it was drawn, which is the fact that decides what geometry it is allowed
to reference. So:

* a Body reads as a record of the work, and the draggable bar that sets its
  tip is a position in that record: drag it up and the model rolls back,
  live, under one undo step;
* everything past the bar dims **and** its spine turns from solid to dashed,
  so the rolled-back state does not depend on telling two greys apart;
* every feature row carries a reference chip per object it reads - a
  sketch, a Boolean's tool, a datum it is attached to - so nothing is
  nested under the operation that happened to use it first; hover to light
  it up, click to jump to it, double-click to edit it;
* a sketch's status sits in a gutter mark whose *shape* carries the severity
  (hollow ring, triangle, disc), and clicking it opens a strip under the row
  with the solver's own words, the constraint state and every feature that
  depends on that sketch.

An earlier version put the sketches in a shelf below the tree. That made
reuse obvious and sequence impossible to see; sequence won, and reuse moved
to the chips and the detail strip. `freecad/nxt/tree/DESIGN.md` records why.

### Running it

```python
Gui.runCommand("Nxt_ModelPanel")      # or
from freecad.nxt.tree import panel; panel.toggle()
```

The panel docks itself beside the stock Model tree and tabs with it, so the
two can be compared directly.

### Verify the API assumptions first

Different FreeCAD builds expose the view-provider API differently, and the
panel degrades quietly when something is missing. Before trusting it:

```python
from freecad.nxt.tree import probe; probe.run()
```

That reports whether QtQuick is importable, where `claimChildren()` is
reachable, whether the drag/drop protocol is exposed, and then prints the
partition it would draw so you can eyeball it against the stock tree.

### Layering

| Module | Job |
|---|---|
| `tree/scene.py` | Pure-Python document snapshot. No Qt, no GUI. Testable. |
| `tree/icons.py` | `QQuickImageProvider` serving live `ViewObject.Icon`. |
| `tree/theme.py` | Palette bridge, derived from the live `QPalette`. |
| `tree/models.py` | Flat list models with diffed rebuilds. |
| `tree/bridge.py` | The only thing QML may call. Owns the transactions. |
| `tree/observers.py` | App/Gui/Selection observers, coalesced into one rebuild. |
| `tree/panel.py` | Dock host and engine wiring. |
| `resources/qml/` | `NxtTree.qml`, `Inspector.qml` and the `Nxt` component module. |

Nothing below `panel.py` knows it is in a dock.

`python3 tests/test_scene.py` runs the partition tests headlessly - they stub
FreeCAD, so they need neither the GUI nor an install.

### Known gaps

* No context menu yet. The stock tree's actions are C++ `QAction`s; they need
  either rebuilding or bridging, and that is its own piece of work.
* Drag-drop leans on `canDropObject`/`dropObject`. Check `probe.run()` for
  how widely your build exposes them.
* Cross-Body reuse is still a PartDesign restriction, not a UI one. Drawing
  each sketch inside its own Body makes the restriction visible rather than
  surprising; offering to create a `SubShapeBinder` is a later step.
