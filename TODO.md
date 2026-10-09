# FreeCAD-Nxt — TODO

Ideas for improving the tree, its context menu and the Property Inspector.
Sizes: **S** under a day · **M** a few days · **L** a week or more.
Tick items off as they land; add notes under an item as decisions are made.

## Already queued

- [x] Multi-object drag reorder within a Body: dragging one of several selected rows carries the selection; within one Body the group slides and lands as a run (`dragNames`, `inOneBody` in tree/bridge.py)
- [x] Appearance label clipped in the icon bar: fits since an icon was removed from the bar
- [ ] VarSets — when Joe prompts
- [x] Wayland placement check for other popups: the Inspector's dropdowns are placed correctly

## Detail strip

- [x] Left edge aligned with the row's pill, indent capped at two levels (accent tick under the pill when capped)
- [x] Close button (×) on the strip; Escape closes the selected row's strip, else all open strips
- [x] Optional auto-show ("Show details on click", off by default): a single click in the tree opens that row's strip after 300 ms and closes the one it opened before; the clicked row is held in place; a pin on the strip keeps it open

## 3D drag handles (FreeCAD 26.3 gizmos)

- [x] Step settings on the Nxt Preferences page (tree/gizmos.py): plain drag fine or coarse, the switch key, fine step, coarse multipliers; Nxt default on first run: fine on a plain drag, Ctrl for coarse
- [x] FreeCAD's own values for the two preferences the first-run default changes are kept, and put back on uninstall (`uninstall.py`, run by the Addon Manager) or at the quit after Nxt is disabled or removed; a value the user changed since is left (`restore_freecads` in tree/gizmos.py)
- [x] Floating value field beside the visible arrow, typing into the task's own field (tree/float_input.py; Pad/Pocket `lengthEdit`)
- [x] Floating fields for a second arrow (two-length pads) and the taper/rotation handles: a box per handle, paired with its task field by the order FreeCAD makes them in (`HANDLES`, `pair` in tree/float_input.py)
- [x] Confirm that pairing in FreeCAD (`probe.draggers()` with a two-length, tapered Pad open): the rotation handle's node type and the order of the handles are taken from FreeCAD's source, not seen
- [x] Snap the dragged length to a parallel face (Pad and Pocket): faces gathered once per edit, the length held on a face within 10 px and the face highlighted; Alt lets it go; "Snap a dragged length to parallel faces" (face_snap.py, separate from the tree)

## Overlay (tree over the 3D view)

- [x] Tip bar and expand arrows take their colour from the theme and, in overlay, from the 3D view background (`branchInk` in tree/theme.py)
- [x] Follow a change of the view background at once (`theme.ViewBackgroundWatch`)
- [x] Tests for view_overlay.py (tests/test_view_overlay.py)
- [x] Write the overlay up in DESIGN.md ("Nxt's own overlay")

## Tree — finding and navigating

- [x] Tree lines ("Show tree lines", off by default): dotted connectors from each container to its children, in the accent colour for the active Body, Part or assembly and everything inside it (`branch_lines` in tree/models.py, TreeLines.qml)
- [x] Double-click a Body, Part or assembly that is not active to make it active; the active one opens and closes as before

- [x] 3D-view picks, as SolidWorks does: a face is traced through the element map to the feature that made it (tree/picking.py), which stays outlined until the selection changes; its path opens, the tree scrolls to it and it flashes (setting "Show objects picked in the 3D view")
- [x] Double-click a face in the 3D view to edit the feature that made it (tree/face_edit.py; setting "Double-click a face to edit its feature")
- [x] Home and End select the first and last row, Shift extends to it; claimed from FreeCAD's "home view" shortcut while the panel has the keyboard (`jumpSelection` in tree/bridge.py)
- [x] Breadcrumb pinned over the top of the list once the containers of the top row have scrolled away ("Bracket › Body › Pocket001"); a name scrolls back to its row (Breadcrumb.qml, `breadcrumb` in tree/bridge.py)

## Tree — acting on objects

Not planned (decided 2026-10-09): stepping the tip from the keyboard, dragging a feature into another Body, Tab between inline renames.

- [x] Undo toast after a reorder, a move between containers, a tip move or a rename ("Moved Pocket after Pad · Undo"); its Undo acts only while that change is still the document's last (toast.py, UndoToast.qml; raised through `services.toast`, shown over the 3D view with the panel open or closed)
- [x] Profiles that will not close are mended without asking: near-miss gaps joined with coincident constraints; for stray, duplicate or overlapping edges the failing feature is pointed at the sketch's closed regions (MakeInternals faces, holes kept) instead of the whole sketch, geometry untouched; also when a sketch is picked during a task (inside the task's undo step); what cannot be mended is reported once, in a toast that stays, with Edit (sketch_closure.py, sketch_repair.py; `RepairProfiles`). **Untested inside FreeCAD.**
- [x] New Sketch with three points, or a straight edge and a point, preselected attaches as "Plane by 3 points" and opens the sketch, answering FreeCAD's attachment dialog; Shift or PartDesign's `NewSketchUseAttachmentDialog` keeps the dialog (sketch_attach.py; `AttachSketchByPoints`). **Untested inside FreeCAD.**

## Context menu

- [ ] **S** Recently used: the two commands last run on this object type, after the lead action (with a setting to turn it off)
- [ ] **M** Prove the addon definition format with one real addon (e.g. Fasteners or Assembly4)
- [x] Multi-select polish: with several selected, actions that apply to each say how many ("Delete 3", "Isolate 3" on the bar; `labels.COUNTED`); "Select all of this type in the Body" for one object in a Body

## Property Inspector

- [ ] **M** Part Design and Sketch templates (after the three card cases are confirmed)
- [ ] **S** Drag to change numbers: horizontal drag on a field's label, Shift fine / Ctrl coarse
- [x] Expression editing with autocomplete: `=` in a value field lists the document's objects, the properties after a dot, the owner's own properties and FreeCAD's functions, with the live result under them; in the inspector, the detail strip and the floating fields (freecad/nxt/expressions.py, Nxt/ExpressionAssist.qml; independent of the tree)
- [ ] **M** Compare mode for multi-select: "— mixed" lists each object's value; pick one to apply to all

## Possible future: structured Report view

- [ ] **L** A Qt Quick Report view: severity filters with counts, repeated messages collapsed (×40), tracebacks folded to one line, object names as chips that select or reveal the row, search, timestamps. Probed in FreeCAD 26.3: Python cannot register a console observer (`App.Console.GetObservers()` only lists them) and console messages do not pass through `sys.stdout`, so the only source is the stock Report view's text document - which does carry everything, C++ messages included. Severity would be read back from the configured Report view colours; only what the stock view is set to show can be captured (log lines are off by default); the stock view must exist, though its dock can stay hidden. Workable, but a mirror of the stock view and somewhat fragile. Not planned; revisit after the overlay work.
- Python console: not worth replacing (editor parity, command echo and macro recording are tied into the stock console).

## Housekeeping

- [x] Preferences: gear quick panel in the tree header (Part layout, row density, reference chips, under-constrained marks) and Edit › Preferences › FreeCAD-Nxt page; `NxtSwitch` and `Segmented` controls
- [x] Preferences for every feature that has landed: the Preferences page now also has "Attach a new sketch to three picked points without asking". Still waiting on their features, which are not built: context-menu Recent, and replacing the native tree rather than sitting beside it
- [x] On quit the QML view is destroyed first, so its bindings do not fire against null (`_on_quit` in tree/panel.py)
- [x] GitHub workflow (`.github/workflows/checks.yml`): ruff, pycodestyle, mypy and the offscreen tests on every push
- [x] Type-check against `freecad-stubs`: clean with and without them (CI installs them). Unchecked `None` from `ActiveDocument` is now guarded; the calls the stubs do not cover go through `freecad/nxt/fc.py`

## Suggested first picks

Keyboard tip stepping · undo toast · Part Design/Sketch templates · multi-select menu polish
