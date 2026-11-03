# UI and UX

Nxt should feel like a well-made desktop application that happens to be
inside FreeCAD: quiet, quick, predictable.

## Feedback and responsiveness

- **Every control responds at once**: hover, press and release are drawn
  immediately. A switch or selector changes visually *first*; the work it
  triggers starts a frame later (`NxtSwitch`: flip now, `changedTo` after
  ~30 ms, settle back if the change never lands).
- **Widget state never waits on computation.** Recomputes, document walks
  and solver reads happen after the frame that shows the change.
- **Live previews degrade honestly.** If a live preview is too slow (the
  rollback bar's ~120 ms budget), fall back to apply-on-release and say so
  in the Report view, rather than stuttering.
- Animations are short (~90–150 ms) and never animate a colour through
  `"transparent"` (that is transparent *black*); animate opacity instead.

## Desktop conventions

- Arrow cursor on buttons, switches, rows and chips. Pointing hand only on
  text links.
- Double-click opens an object for editing; F2 (Return on macOS) or a click on an
  already-selected name renames (armed after the double-click interval).
- Escape backs out of the innermost thing (popup, detail strip, edit),
  never two at once. Return applies; Escape in a field reverts.
- Keyboard actions work on FreeCAD's selection, not a list's current row.
- Context menus open at the pointer and offer what is most likely next.
- Mouse wheel over a number steps it (fine; with the modifier, coarse), the
  same steps as the 3D drag handles.

## Keyboard

The keyboard reaches everything the mouse does, in the order the eye
reads, and focus is always visible and never lost.

- **Tab order is reading order**: left to right, then top to bottom. In
  QML that is child order, so declare items in the order they are read
  (a field's lead choice before its text: `TextField` puts what is placed
  inside it ahead of its input). Every value control takes Tab focus:
  text fields, dropdowns, selectors, switches, check boxes, chip pickers.
- **Task panels are one Tab sequence**, cards and FreeCAD's own options
  together (`task_layout.tab_in_order`): Tab goes from the last card on to
  Preview and its check boxes, not off to the main window.
- **Focus is drawn by a ring** in the accent colour, outside the control
  so it shows on an accent fill too (a switch that is on). Keyboard focus
  only; a click shows no ring. Hover is a separate, plainly visible cue
  (fill change, a darker outline), never a one-shade shift.
- **Dropdowns open as combo boxes do**: Space, Return/Enter, Down,
  Alt+Down, F4. Up/Down on a closed dropdown never changes its value.
  Closing the list (by choice or Escape) gives the focus back to it.
- **Selectors step with the arrows**, and keep the focus while the panel
  rebuilds around them (Two sides adds a card): the bridge remembers the
  focused property and its new field takes the keyboard back
  (`ValueEditor.takeFocusBack`), unless another control already has it.
- **Leaving a field keeps what was typed**, as FreeCAD's fields do: on
  Tab, a click elsewhere, or a task's OK (which takes no focus, so the
  cards apply pending edits first). Escape is the only way to drop an
  edit.
- **When the keyboard leaves a view, its ring goes** (Tab out, a click
  elsewhere, a shortcut): `quick_host.LetsGo` / `let_go`. Not for the
  view's own popup or menu, another application, or the dialog
  rebuilding; focus stays put through those.

## Controls

- **Switches, not checkboxes**, for on/off settings, in most places.
- **Segmented control** for a few choices that change the shape (One side
  / Two sides / Symmetric); **dropdown** for longer lists.
- Labels are short; explanation goes in a tooltip or a card hint.
- A value that can't be changed in the current mode is hidden, not shown
  disabled, unless seeing it helps (then read-only).
- The same control behaves the same everywhere (a chip that double-clicks
  to open on a row also does in the detail strip).

## Information

- **A mark means something is wrong.** Don't decorate every row; a marker
  on everything is read by no one. Severity has a shape before a colour
  (ring, triangle, disc).
- **Accessibility is a constraint**: every state has a non-colour cue
  (shape, dashed vs solid, italic). Interactive borders ≥ 3:1 contrast,
  text ≥ 4.5:1.
- **Whole name or clean icon, never a fragment.** Elide only where the full
  name is a hover away.
- Follow the host theme: colours from FreeCAD's stylesheet (`ui/theme.py`),
  in light and dark, docked and in overlay mode. Test both.
- Plain words in messages: what happened and what to do ("Repaired Sketch
  (2 gaps closed)", with Undo).

## Where things live

- The **detail strip** (under a tree row) only changes values. Structural
  edits (adding a variable, renaming its type) belong in the Property
  Inspector.
- **Task panels and the inspector use the same template**, so a feature
  looks and works the same in both.
- Nxt's automatic fixes (wire repair) are undoable in one click and never
  hide what they did.
- Commands that act without a dialog in FreeCAD act without one here.
