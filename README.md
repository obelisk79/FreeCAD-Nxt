<img src="freecad/nxt/resources/icons/FreeCAD-Nxt.svg" alt="" width="64" align="right">

# FreeCAD-Nxt

A revolutionary take for the FreeCAD user interface based on QtQuick and established User Experience(UX) principles. 


## Install

With the Addon Manager, once published. By hand, clone or copy this folder
into FreeCAD's `Mod` directory and restart FreeCAD:

```bash
git clone https://github.com/obelisk79/FreeCAD-NXT ~/.local/share/FreeCAD/Mod/FreeCAD-Nxt
```


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
| `Nxt_ModelPanel` | View › FreeCAD-Nxt | show or hide the model panel |
| `Nxt_ModelPanelOverlay` | View › FreeCAD-Nxt | draw the panel as floating labels |
| `Nxt_PropertyInspector` | View › FreeCAD-Nxt | the selection's properties in an inspector |
| `Nxt_Reload` | View › FreeCAD-Nxt, for now | hot-reload the addon's Python modules |

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
python3 tests/test_menus.py        # context menu definitions
python3 tests/test_reorder.py      # reordering a Body by drag and drop
python3 tests/test_context_menu_qml.py  # the context menu's QML; PySide6
python3 tests/test_tree_settings_qml.py # the gear's quick settings; PySide6
python3 tests/test_inspector_qml.py  # the inspector's QML; PySide6
python3 tests/test_selection_keys.py # Space, arrows, Shift+click; PySide6
ruff check . && pycodestyle freecad tests && mypy
```
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

### Running it

```python
Gui.runCommand("Nxt_ModelPanel")      # or
from freecad.nxt.tree import panel; panel.toggle()
```

The panel docks itself beside the stock Model tree and tabs with it, so the
two can be compared directly.

### Known gaps

* The context menu covers the common object types (see
  `freecad/nxt/tree/CONTEXT_MENU.md`); anything else falls back to
  FreeCAD's own menu, the last entry under More.
* Drag-drop leans on `canDropObject`/`dropObject`. Check `probe.run()` for
  how widely your build exposes them.
* Cross-Body reuse is still a PartDesign restriction, not a UI one. Drawing
  each sketch inside its own Body makes the restriction visible rather than
  surprising; offering to create a `SubShapeBinder` is a later step.
