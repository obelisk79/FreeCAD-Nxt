# The tree context menu: inventory

What FreeCAD's tree menu offers today, where it comes from, and where each
item goes in Nxt's menu. This is the evidence the menu definition file is
built from; the file's format follows from it, not the other way round.

Source: FreeCAD `main` at 3471328 (2026-09-24). Line references are to that
revision.

## How FreeCAD builds the menu today

`TreeWidget::contextMenuEvent` (`src/Gui/Tree.cpp:1187`) stacks four layers,
none of which knows about the others:

1. **The view provider's edit actions**, inserted at the top
   (`ViewProvider*::setupContextMenu`): "Edit Sketch", "Edit Pad", "Set Face
   Colors", "Active Body", "Select Group Contents", link configuration. The
   first becomes the default (bold) action. "Finish Editing" is added while
   the object is being edited. These are plain QActions, not commands: most
   carry an edit mode in `data()` and run as `setEdit(obj, mode)`; a few
   (Active Body, Select Group Contents, link options) run a C++ lambda.
2. **The active workbench's items** (`Workbench::setupContextMenu`, recipient
   `"Tree"`), then any workbench manipulators. Python workbenches add theirs
   in `ContextMenu()` with `appendContextMenu`.
   - `StdWorkbench` (every workbench): Toggle Suppressed (if suppressible),
     Toggle Freeze, Toggle Visibility, Show Selection, Hide Selection, Toggle
     Selectability, Select All Instances, Random Color, Toggle Transparency,
     Cut, Copy, Paste, Delete, Send to Python Console, and for one object with
     an editable Placement, Transform and Placement… (`Workbench.cpp:634`).
   - Part Design, before those: Set Tip, Move Object to Other Body, Move
     Object After Other Object, Create MultiTransform
     (`PartDesign/Gui/Workbench.cpp:79`).
   - Draft: a Utilities submenu of 12 commands on every selection, plus
     Hyperlink and Update Shape2DView when they apply.
   - Assembly: Select Joints of Component, for a component of the active
     assembly.
   - Sketcher and Part add nothing.
3. **Fixed items**: Properties, Expressions, and a Link Actions submenu
   (Make Link Group, Make Link, then whichever of Make Relative Link, Unlink,
   Replace, Import, Import All, Select Linked, Select Deepest Linked, Select
   All Links is active).
4. **The tree's own actions**: Show Items Hidden in Tree View, Toggle
   Visibility in Tree View, Create Group (on a group), Add Dependent Objects
   to Selection, Mark to Recompute, Recompute Object, Rename (one object),
   then Activate Document (two or more documents open) and Tree Settings
   (Show Description, Show Internal Name).

For a Pad in the Part Design workbench that comes to about 30 items and two
submenus. Three things make it feel unorganized:

- **It follows the workbench, not the object.** The same Pad gets Set Tip in
  Part Design and not in Part; a sketch gets Draft's Utilities if Draft is
  active.
- **The order is the order of the code**, not of use: Freeze and Suppress
  lead the workbench block, Rename is near the bottom, Delete sits between
  Paste and Send to Python Console.
- **Document and tree settings share the menu with object actions**
  (Activate Document, Tree Settings, Show Items Hidden).

Nxt keys the menu to the object instead. Every command FreeCAD would offer is
still reachable, from the sections or from More.

## The shape Nxt will use

- **Action bar**: a fixed row of icons with labels, identical for every
  object; an action that doesn't apply is dimmed, never removed.
- **Lead**: the object's own action in bold, what FreeCAD makes default.
- **State rows**: what the object's condition calls for, tinted, under the
  lead.
- **Sections**, always in this order, each shown only if it has items: Model,
  Organize, Relations, Inspect.
- **Delete**, apart, at the bottom of the list.
- **More ›**: the rarely used, grouped by the workbench that supplies it,
  including anything FreeCAD offers that no definition mentions.

## The action bar

Candidates, judged by "applies to nearly everything, used often":

| Action | Source | Applies to | Verdict |
|---|---|---|---|
| Hide / Show | `Std_ToggleVisibility` | anything shown in 3D | yes |
| Isolate | `nxt:isolate` (exists: `bridge.isolate`) | anything shown | yes |
| Fit in view | `Std_ViewFitSelection` | anything with a shape | yes |
| Appearance | `Std_SetAppearance` | anything shown | yes |
| Property Inspector | `nxt:inspector` (exists) | everything | yes |
| Rename | `nxt:rename` (exists: `bridge.rename`, F2) | one object | maybe: already F2 and double-click-slow |
| Delete | `Std_Delete` | everything | no: a one-click destructive action next to Hide invites accidents; keep it in the list |
| Transform | `Std_TransformManip` | editable Placement only | no: dimmed on every Part Design feature, sketch and datum |

**Decided**: Hide, Isolate, Fit, Appearance, Inspector: five, no sixth.
Rename stays in Organize and on F2.

## Every object

Items that apply to any object, whatever its type.

| FreeCAD item | Command or action | Nxt slot | Condition |
|---|---|---|---|
| Toggle Visibility | `Std_ToggleVisibility` | bar | shown in 3D |
| Show Selection / Hide Selection | `Std_ShowSelection`, `Std_HideSelection` | dropped: the bar's toggle covers both; with a mixed selection it hides all if any is shown (as Space does) | |
| — | `nxt:isolate` | bar | |
| — | `Std_ViewFitSelection` | bar | has a shape |
| Random Color | `Std_RandomColor` | More | |
| Toggle Transparency | `Std_ToggleTransparency` | More | |
| — | `Std_SetAppearance` | bar | shown in 3D |
| Toggle Selectability | `Std_ToggleSelectability` | More | |
| Rename | tree action | Organize (and F2) | one object |
| — | `Std_DuplicateSelection` | Organize | |
| Cut / Copy / Paste | `Std_Cut`, `Std_Copy`, `Std_Paste` | More, under Clipboard (keyboard shortcuts remain) | |
| Delete | `Std_Delete` | Delete slot | |
| Recompute Object | tree action | Model | |
| Mark to Recompute | tree action | More | |
| Toggle Freeze | `Std_ToggleFreeze` | More | |
| Toggle Suppressed | `Std_ToggleSuppress` | Model | suppressible |
| Add Dependent Objects to Selection | tree action | Relations, as "Select what uses it" | has dependents |
| — | `nxt:select_support` | Relations, "Select what it's built from" | has inputs |
| Select All Instances | `Std_TreeSelectAllInstances` | Relations | object appears more than once (linked) |
| Properties | `Std_Properties` | replaced by the Inspector in the bar | |
| Expressions | `Std_Expressions` | Inspect | |
| Send to Python Console | `Std_SendToPythonConsole` | Inspect | |
| Transform | `Std_TransformManip` | Model | editable Placement |
| Placement… | `Std_Placement` | Model | editable Placement |
| Link Actions › | `Std_Link*` | Organize, "Make link" ›; the rest in More | |

## Sketch (`Sketcher::SketchObject`)

| Item | Command or action | Slot | Condition |
|---|---|---|---|
| Edit Sketch | edit mode Default | lead | |
| — | `nxt:show_solver_issues` | state | solver reports conflicts, redundancy or malformed constraints |
| — | `nxt:reveal_failure` | state | failed to recompute |
| — | `Sketcher_MapSketch` | Model | |
| — | `Sketcher_ValidateSketch` | More (Sketcher) | |
| — | `Sketcher_MirrorSketch`, `Sketcher_MergeSketches` | More (Sketcher) | |
| — | `nxt:select_consumers` | Relations, with the consumers' names | used by a feature |

Sketcher's workbench adds nothing to the tree menu today, so the Model and
More entries here are new: they are sketch commands that live only in the
Sketcher menu bar.

## Part Design feature (`PartDesign::*` except Body)

| Item | Command or action | Slot | Condition |
|---|---|---|---|
| Edit Pad (Pocket, Fillet…) | edit mode Default | lead | |
| Set Face Colors | edit mode Color | More (Part Design) | |
| Set Tip | `PartDesign_MoveTip` | Model, as "Roll back to here" | not the tip |
| — | `nxt:roll_forward` | Model | past the rollback bar |
| — | `nxt:reveal_failure`, `Std_Recompute` | state | failed |
| Move Object to Other Body | `PartDesign_MoveFeature` | Organize, "Move to" › | another Body exists |
| Move Object After Other Object | `PartDesign_MoveFeatureInTree` | Organize, "Move to" › | |
| Create MultiTransform | `PartDesign_MultiTransform` | Model | one transform feature |
| — | `nxt:select_support`, `nxt:select_consumers` | Relations | |

Placement and Transform don't appear: a feature's Placement is read-only.

## Body (`PartDesign::Body`)

| Item | Command or action | Slot | Condition |
|---|---|---|---|
| Active Body | view provider lambda | lead, as "Make active" / "Make inactive" | |
| — | `PartDesign_NewSketch` | Model | |
| Toggle Freeze | `Std_ToggleFreeze` | Model (Part Design adds it for Bodies) | |
| Transform, Placement… | `Std_TransformManip`, `Std_Placement` | Model | |
| — | `nxt:reveal_first_problem` (exists) | state | any feature failed |

## Datum (`PartDesign::Plane`, `Line`, `Point`, `CoordinateSystem`)

| Item | Command or action | Slot |
|---|---|---|
| Edit Datum | edit mode Default | lead |
| — | `nxt:select_consumers` | Relations |

## Group (`App::DocumentObjectGroup`)

| Item | Command or action | Slot | Condition |
|---|---|---|---|
| Select Group Contents | view provider lambda | lead | not empty |
| Create Group | tree action | Organize, "New group inside" | |
| Expand all / Collapse all | `nxt:expand_all`, `nxt:collapse_all` (exist) | Organize | has children |

## Part primitives and booleans (`Part::*`)

| Item | Command or action | Slot | Condition |
|---|---|---|---|
| Edit Cylinder (etc.) | edit mode Default | lead | primitive |
| Appearance per Face | edit mode Color | More (Part) | |
| Transform, Placement… | `Std_TransformManip`, `Std_Placement` | Model | editable Placement |

## Links and binders

| Item | Command or action | Slot |
|---|---|---|
| Edit Shape Binder | edit mode Default | lead |
| Synchronize | view provider action | state, when out of date; else Model |
| Select Bound Object | view provider action | Relations |
| Select Linked / Deepest Linked / All Links | `Std_LinkSelect*` | Relations |
| Unlink, Replace, Import, Make Relative | `Std_Link*` | More |
| Copy on Change, Tracking, Configurable Object | view provider actions | More |

## Draft objects

Objects whose proxy comes from Draft (`proxy_module = "draftobjects.*"`)
get Draft's Utilities (`Draft_SetStyle`, `Draft_ApplyStyle`, layers, groups,
construction) under More › Draft, plus Hyperlink and Update Shape2DView when
they apply. Nothing of Draft's appears on other objects, whichever workbench
is active.

## Addon and other Python objects

Nxt knows nothing about them in advance. The lead is the view provider's
default edit action; everything the object's workbench or view provider adds
goes to More under that workbench's name, until the addon ships a definition
file of its own. Spreadsheet's "Show Spreadsheet" is the lead for a
spreadsheet.

## Several objects

- The bar acts on all of them; labels carry the count ("Hide 3").
- There is no lead unless every object shares one; the Inspector leads
  instead.
- Sections keep only items that apply to every selected object (FreeCAD's
  own `isActive()` already reports this for commands).
- Rename and the view-provider actions drop out: FreeCAD only builds those
  for a single object.

## The document row and the panel

These leave the object menu:

| FreeCAD item | Where it goes |
|---|---|
| Activate Document ›, Close, Reload, Open File Location, Skip Recomputes, Allow Partial Recompute | the document row's own menu |
| Tree Settings ›, Show Items Hidden in Tree View | Nxt's panel settings |
| Toggle Visibility in Tree View | More |
| Search Objects | Nxt's search box |

## Nxt actions the definitions will need

Existing (a bridge slot already does the work): `isolate`, `inspector`,
`rename`, `set_tip` (`setTip`), `expand_all`, `collapse_all`,
`reveal_first_problem`, `highlight_related`.

New: `select_support`, `select_consumers`, `roll_forward`,
`show_solver_issues`, `reveal_failure`, `make_active` (wrapping the Body's
Active Body action).

## The condition vocabulary this implies

Everything above is expressible with:

- `type`: a TypeId, with `*` wildcards (`PartDesign::*`), or a list of them.
- `count`: `1`, `"2+"`, `"any"`.
- `in_body`: true or false.
- `proxy_module`: the module a Python object's proxy class comes from, with
  wildcards (`draftobjects.*`).
- `flags`: `failed`, `past_tip`, `is_tip`, `solver_issues`, `has_expression`,
  `has_dependents`, `has_inputs`, `out_of_date`, `editable_placement`,
  `suppressible`, `has_shape`, `shown_in_3d`, `editing`.

Commands also pass through FreeCAD's `isActive()`, so a definition never has
to restate what the command already checks.

## Carrying over what we don't declare

Two routes, both needing a probe on your FreeCAD before we rely on them:

1. **Commands** (layers 2 and 3): each QAction a command adds has the
   command's name as its `objectName` (`Action.cpp:76`). Nxt can open
   FreeCAD's own tree menu for the object without showing it, read the names,
   and file every one it doesn't declare under More, by workbench. Running
   one later is `Gui.runCommand(name)`.
2. **View provider actions** (layer 1): those with an edit mode replay as
   `setEdit(obj, mode)`. The few that run a lambda (Active Body, Select Group
   Contents, link options) can't be replayed from a list; choosing one
   re-opens FreeCAD's menu invisibly and triggers the action with that text.

If the probe shows the hidden menu can't be read reliably, the fallback is a
last item, "FreeCAD's menu…", that opens the native one for the object.

## Probe results

`probe.context_menu()` on a Pad in your FreeCAD 26.3 build, compared with
the source reading above:

- **Reading the native menu works.** All 23 command entries carried their
  command name. The object's edit actions carried their edit mode (Edit Pad
  0, Set Face Colors 3), so they replay with `setEdit`.
- **Std_SetMaterial** (Material) is in this build and wasn't in the source
  read. It goes to More › Display beside Random Color.
- **Two commands are submenus**: Std_Expressions (Copy Selected, Copy
  Active Document, Copy All Documents, Paste) and Std_LinkMakeGroup (Simple
  Group, Group With Links, Group With Transform Links). Their entries have
  no names of their own; they run as `Gui.runCommand(name, index)`.
- **Commands left out on purpose** are listed as `drop` so the carry-over
  doesn't put them back in More: Show Selection, Hide Selection, Properties,
  and Part Design's Set Tip (replaced by `nxt:set_tip`).
- On a **sketch**, Part Design offers Move Object To and Move Feature
  After too: they apply to anything inside a Body, not only features. They
  now sit in an `in-body` menu that covers sketches and datums.
- A sketch also has **Edit Attachment**, from Part's attachment extension.
  It runs code rather than a command, so Nxt has its own
  `nxt:edit_attachment`, offered on any attachable object; Sketcher's
  older Map Sketch moves to More › Sketcher.
- On a **Body**, Active Body is the lambda-type action expected, covered by
  `nxt:make_active`; nothing is left over.
- On Wayland the hidden menu can't be faded out, so it may flash for one
  frame while the probe reads it. The real menu won't use this path for
  commands; only for view-provider actions that run code, which re-open
  the native menu to trigger them.

## Where this lives

- `resources/menus/default.toml`: these tables as Nxt's definition file.
- `menus/definitions.py`: reading, checking, merging and resolving.
- `menus/facts.py`: the facts a condition is tested against, read from the
  tree's snapshot and the object.
- `menus/labels.py`: every label, marked for translation.
- `menus.explain()`: why the selection's menu is what it is.
- `tree/probe.py`, `context_menu()`: reads FreeCAD's own menu for the
  selection and lists what Nxt's definitions would leave to More.

## Drawing and running it

- The menu is Qt Quick Controls' `Menu` with `popupType: Popup.Window`
  (Qt 6.8+; FreeCAD 26.3 ships 6.11): a popup window of its own, the kind
  QMenu uses, so it reaches past the dock and over the 3D view, closes on
  a click anywhere else or on Escape, opens More on hover as a cascading
  submenu, and is walked with the arrow keys - all Qt's behaviour, not
  Nxt's. `resources/qml/Nxt/ContextMenu.qml` builds it from the menu data
  and draws every part in the panel's theme, importing the Basic style by
  name so FreeCAD's widget style cannot reach in. The panel opens it
  (`NxtTree.qml`); nothing else in the panel uses Qt Quick Controls.
- **Placement under Wayland.** Qt hands the compositor the rectangle of
  the item a window-type menu opens from, in that item's window's
  coordinates, and the menu opens at its bottom-left - the requested
  position is not used. The panel's items live in a QQuickWidget, whose
  window is offscreen, so opened from the panel the menu sat at the
  panel's bottom-left. It now opens from a one-pixel item moved to the
  click, shifted under Wayland by the panel's position in FreeCAD's
  window (`host.menuAnchorOffset()`). Confirmed on Joe's Wayland session.
- It opens at the pointer on right-click, and under the selected row from
  the keyboard with the Menu key or Shift+F10. Up and Down walk the rows,
  Right on More opens it and Left closes it, Enter runs, Escape closes.
  The icon bar is a keyboard stop too, as one row: Down from the top
  reaches it, Left and Right move between its buttons, Enter runs the one
  marked.
- **Expressions.** FreeCAD's Std_Expressions crashes FreeCAD when run
  from anywhere but a menu FreeCAD has built itself: its isActive(),
  called before every run, updates its own submenu's entries, which do
  not exist yet. The menu never offers or runs it (`runner.UNSAFE`).
  Inspect has an Expressions submenu of Nxt's own actions instead - copy
  selected, copy active document, copy all documents, paste - writing and
  reading FreeCAD's clipboard format, so copies go both ways between them.
  They handle ExpressionEngine only; a spreadsheet's cells are left to
  FreeCAD's command. Definition files can now hold submenus:
  `{ label = "...", submenu = [items] }`.
- `menus/present.py` turns a resolved menu into the plain data the QML
  reads; `menus/runner.py` asks FreeCAD about commands and runs them;
  `tree/menu_actions.py` runs Nxt's own actions.
- FreeCAD commands keep FreeCAD's labels, shortcuts and icons, and are
  drawn disabled when FreeCAD says they cannot run, as in its own menu. A
  workbench's commands are imported on first use (Sketcher's do not exist
  until it has been loaded once); a command that still is not registered
  is left out.
- **No automatic carry-over yet.** Reading FreeCAD's menu on every
  right-click would flash it on Wayland, and the probe found nothing to
  carry over for Part Design. Instead More ends with "FreeCAD's menu…",
  which opens the native one for the selection. The probe stays the way to
  find anything a definition should add.
- It is kept on the screen, and scrolls only when taller than the screen.

## Decisions

- The action bar has five icons: Hide, Isolate, Fit, Appearance, Inspector.
- Cut, Copy and Paste go to More, under Clipboard.
- Show Selection and Hide Selection are dropped in favour of the toggle.
- Draft's Utilities appear only on Draft objects.
