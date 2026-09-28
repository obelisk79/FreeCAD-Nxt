# FreeCAD-Nxt — TODO

Ideas for improving the tree, its context menu and the Property Inspector.
Sizes: **S** under a day · **M** a few days · **L** a week or more.
Tick items off as they land; add notes under an item as decisions are made.

## Already queued

- [ ] Multi-object drag reorder within a Body
- [ ] Appearance label slightly clipped in the icon bar (Joe deciding)
- [ ] VarSets — when Joe prompts
- [ ] Wayland placement check for other popups (e.g. the Inspector's ChoiceList dropdowns if they become window popups)

## Detail strip

- [x] Left edge aligned with the row's pill, indent capped at two levels (accent tick under the pill when capped)
- [x] Close button (×) on the strip; Escape closes the selected row's strip, else all open strips
- [ ] **M** Optional auto-show: follow selection after ~300 ms, single tree pick only, keep the clicked row in place; setting plus pin toggle

## Tree — finding and navigating

- [x] 3D-view picks, as SolidWorks does: a face is traced through the element map to the feature that made it (tree/picking.py), which stays outlined until the selection changes; its path opens, the tree scrolls to it and it flashes (setting "Show objects picked in the 3D view")
- [x] Double-click a face in the 3D view to edit the feature that made it (tree/face_edit.py; setting "Double-click a face to edit its feature")
- [ ] **S** Right-click a face in the 3D view: "Find in tree", for when automatic scrolling is off (as Fusion 360)
- [ ] **M** Search as a filter: narrow the tree to matches and their parents; support `type:sketch`, `failed`
- [ ] **S** Keyboard jumps: Home/End for first/last row; Alt+Up/Down steps between problems
- [ ] **S** Breadcrumb header pinned when scrolled deep into a Body (e.g. Body › Pocket001)

## Tree — acting on objects

- [ ] **S** Step the tip from the keyboard: Ctrl+Up/Down on a focused Body row scrubs the rollback
- [ ] **M** Drag a feature onto another Body to move it there, with the same up-front check as reorder
- [ ] **S** Undo feedback toast after reorder, tip move or rename ("Moved Pocket after Pad · Undo")
- [ ] **S** Inline rename: Tab moves to the next row's name, Escape restores the old one

## Context menu

- [ ] **S** Recently used: the two commands last run on this object type, after the lead action (with a setting to turn it off)
- [ ] **M** Prove the addon definition format with one real addon (e.g. Fasteners or Assembly4)
- [ ] **S** Multi-select polish: counts on bar and rows ("Hide 3", "Delete 3"); "Select all of this type in the Body"

## Property Inspector

- [ ] **M** Part Design and Sketch templates (after the three card cases are confirmed)
- [ ] **S** Drag to change numbers: horizontal drag on a field's label, Shift fine / Ctrl coarse
- [ ] **M** Expression editing with autocomplete: `=` opens an inline editor with suggestions and a live result
- [ ] **M** Compare mode for multi-select: "— mixed" lists each object's value; pick one to apply to all

## Housekeeping

- [x] Preferences: gear quick panel in the tree header (Part layout, row density, reference chips, under-constrained marks) and Edit › Preferences › FreeCAD-Nxt page; `NxtSwitch` and `Segmented` controls
- [ ] Preferences still to add as their features land: dependency arrows, detail strip auto-show, context-menu Recent, replace vs. beside the native tree
- [x] GitHub workflow (`.github/workflows/checks.yml`): ruff, pycodestyle, mypy and the offscreen tests on every push
- [ ] **S** Type-check against `freecad-stubs` too: with them installed mypy reports 36 errors, mostly unchecked `None` from `ActiveDocument`/`ActiveView`

## Suggested first picks

3D-view reveal · keyboard tip stepping · undo toast · Part Design/Sketch templates · CI workflow
