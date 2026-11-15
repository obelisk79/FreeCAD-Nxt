# Qt, QML and FreeCAD pitfalls

Each of these has broken Nxt before. The full list, with the reason for
each, is "Decisions" and "Gotchas" in `freecad/nxt/tree/DESIGN.md`.

## Crashes and lost events

- **Never destroy a QML object from inside its own signal handler.** It
  calls `qFatal` and FreeCAD exits. If a handler can cause its delegate to
  be rebuilt (changing a model, clearing a search), do it with
  `Qt.callLater` or a zero timer.
- **No Python exception may escape a Qt event handler**: it terminates the
  process. Do heavy or risky work on a queued timer, with a guard.
- **`QTimer.singleShot` with a bound method outlives its object.** After a
  reload it fires into a deleted wrapper. Use a `QTimer` parented to the
  owner.
- **Never null a QML context property to tear down a view.** Delete the
  `QQuickWidget` instead.
- **FreeCAD's progress indicator spins the event loop** during recompute:
  mouse moves and releases can arrive mid-operation. Make drag code
  re-entrant; recompute only what changed (`doc.recompute([body])`).
- **`setEdit` nests an event loop**; call it deferred, and open a
  transaction yourself (setEdit opens none).
- A Gui observer with `slotChangedObject` breaks Python view providers
  (Assembly). Use the App observer's `Visibility` instead.
- `Std_Expressions.isActive()` before its menu exists segfaults. Commands
  that act on an implicit target need that target established first.

## QML

- A `MouseArea` that accepts presses takes an exclusive grab: put a
  row-wide one at `z: -1`, below the row's `TapHandler`s.
- `TapHandler.tapped` fires again on a double tap; use `singleTapped` and
  `doubleTapped` when both mean something.
- A binding that only calls `itemAtIndex()` evaluates once; read a
  reactive property too.
- Elided `Text` re-emits `implicitWidth`; measure with `TextMetrics` to
  avoid binding loops.
- A popup that closes on focus loss must outlive the click on it (defer
  the close).
- A `Repeater` driven by a list rebuilds every delegate on each new list,
  taking focus with it; drive it by a count when fields are edited.
- `Popup.Window` grabs the keyboard; a suggestion list next to a field is
  a `Qt::ToolTip` window.

## Wayland and windows

- The app can't read the global pointer or place top-level windows. Open
  popups and menus from a 1 px anchor item at the click point, shifted by
  `quick_host.window_offset`.
- **Never resize a `QQuickWidget` from a signal QML emits while laying
  out** (`implicitHeightChanged`): the resize starts a frame inside the
  frame, both are dropped ("beginFrame() must be followed by ...
  endFrame()") and the view stays blank. Resize on a zero timer.
- A translucent `QQuickWidget` doesn't make what's behind it redraw: call
  `host.repaintBehind()` on movement.
- Reparenting a `QQuickWidget` to another top-level window needs
  `releaseResources()` (new QRhi).

## Qt and PySide6

- PySide6 enums are `enum.Enum`: use `.value`, not `int()`.
- Assign model state before emitting `dataChanged`.
- `QApplication.palette()` is not FreeCAD's stylesheet; colours come from
  `ui/theme.py`.

## FreeCAD

- A task dialog owns its feature: OK writes every field back. Edit through
  its widgets (`task_sync.py`); set `QuantitySpinBox` by `rawValue`.
- Not every view provider's Python type has `.Object` (Assembly's has
  not): in observer slots use `core.fc.object_of(view_provider)`.
- A selection inside a Body is filed under the Body (`("Body", "Pad.")`).
- `InList` has one entry per link, not per object.
- Redundant sketch constraints leave `State` clean; read Sketcher's own
  properties. `None` means unknown, never healthy.
- Hidden enumeration values start with `?` (kept for old files); leave them
  out of choices unless current.
- FreeCAD keys Python preference pages by class name: give yours a unique
  one (`NxtPreferencesPage`).
- Workbench commands don't exist until their Gui module is imported.
- `getPointOnViewport` has y up from the bottom.
- Prefer detection (`hasattr`) to version checks; FreeCAD versions differ.
