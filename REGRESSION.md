# Regression checklist

Run in FreeCAD after each restructuring phase. **Short** items (S) after every
phase; the full list after phases 3 and 4. Note the build, the session type
(X11 or Wayland) and anything that misbehaves.

## Start-up and panels
- [ ] S FreeCAD starts with no Nxt errors in the Report view
- [ ] S The Nxt tree, Property Inspector and preferences page all open
- [ ] Reload Nxt (Tools menu) with a document open; no errors
- [ ] Quick settings (gear): each switch takes effect at once

## Opening documents
- [ ] S A large document opens with the expansion saved in the file
- [ ] A file with no saved expansion opens collapsed
- [ ] Switch to another document and back: what was open is kept
- [ ] Save, reopen: the Nxt tree and the stock tree agree
- [ ] Collapse all keeps the active Body's path; Shift-click expands all, Origins stay closed

## Selection and visibility
- [ ] S Click, Ctrl-click, Shift-click, Up/Down, Home/End
- [ ] S Space toggles the selected feature, not its Body; also from the 3D view
- [ ] The eye on a feature; isolate and leave isolation
- [ ] 3D pick reveals and flashes the feature that made the face

## Naming and activation
- [ ] F2 and slow double-click rename
- [ ] Double-click activates a Body or Part; double-click a datum opens attachment (tree and 3D view)
- [ ] Double-click a face edits its feature

## Drag and drop
- [ ] S Reorder within a Body (gap follows, label "After …")
- [ ] S Reorder within a Part or group; drop into a sibling container (outline, opens after 0.7 s)
- [ ] Drag out of a Part to the top level or another group
- [ ] Edge scroll in a long tree; Escape cancels
- [ ] Multi-select drag in a Body

## Rollback bar
- [ ] S Drag on a slow Body: no recompute until release, one undo step
- [ ] Release where it started: no undo entry; Escape/cancel restores

## Context menu
- [ ] S Right-click and Menu key/Shift+F10; placement correct (Wayland)
- [ ] Multi-select counts ("Delete 3"); More ▸ and FreeCAD's menu…
- [ ] Expressions submenu copy and paste

## Detail strip and Property Inspector
- [ ] S Detail strip edits; Ctrl-click opens the inspector
- [ ] Inspector pin, move, resize; pinned follows the selection
- [ ] Pad/Pocket template: Sides, Type dropdown, second column, Direction, Start, Profile
- [ ] Inspector edits during a Pad task move the handles and survive OK
- [ ] Dropdown that changes the form does not freeze the panel
- [ ] Helix template and task: axis list, each Mode's fields, Turning, OK writes them
- [ ] Add/Cut/Keep common in a task (new and edited feature, each kind): OK keeps the switch, Cancel undoes it all
- [ ] Switching kind relinks what follows (fillet, sketch on a face, Tip) and keeps a custom label
- [ ] Switching kind from the inspector, outside a task: one undo step
- [ ] Primitives (each kind, add and cut): cards replace the parameters box, Nxt's attachment replaces FreeCAD's (new and edited), attaching moves it and Cancel undoes it, OK keeps typed sizes, Prism sides

## 3D editing aids
- [ ] S Floating value fields: type, Tab, wheel, expression with suggestions placed by the field
- [ ] Face snapping while dragging a length (Alt releases)
- [ ] New Pad starts at an offset with the start handle shown
- [ ] Undo toast after reorder, tip move, rename
- [ ] Sketch repair and attach-by-three-points

## Overlay
- [ ] FreeCAD's overlay and Nxt's own overlay; colours follow the 3D background
