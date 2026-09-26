# Nxt model panel — the timeline tree

Status: implemented in this directory. The timeline rebuild is verified headlessly (`tests/test_scene.py`, `tests/test_qml.py`) and not yet exercised on a large model in a running FreeCAD.

## The paradigm

Keep the collapsible hierarchy. Draw a container's children **in the order they were made**, and lift whatever an operation *reads* out of that operation so it stands beside it rather than under it.

    Body
      Sketch          drawn first
      Pad             consumes Sketch
      Sketch001       drawn on the face the Pad made
      Pocket          consumes Sketch001

The stock tree nests a sketch under whichever feature claimed it first, which is wrong twice over. A sketch driving a Pad, a Pocket and a Pipe appears exactly once — under the Pad — and is invisible from the other two. And a sketch is built on the geometry that existed at the moment it was drawn, so filing it at the point of first use hides the one fact that explains what it is allowed to reference.

It was never really about sketches. A Boolean's tool, a datum a feature is attached to, the shapes a MultiTransform transforms — the stock tree nests all of them under the operation that reads them, and every one is the same claim: that the operation owns the thing. It is false the moment a second operation uses it, and it files the thing at the point of first use rather than when it was made. So the rule is stated about consumption rather than about type, and sketches are simply its most common case.

Read in sequence, a Body is a record of the work. The draggable bar that sets its tip is then a position in that record rather than a pointer at a row: roll it back and you are looking at the model as it stood.

### What this replaced, and why

The first version of this panel put the sketches in a **shelf**: a flat, always-visible list below the tree, disjoint from it. The argument was reuse — the profile is the stable thing, and consumption is an annotation on it.

The shelf was right about reuse and wrong about everything else. Pulling sketches out of the sequence destroyed the one relationship a history-based modeller is built on, which is *when*. A sketch on the shelf tells you nothing about which geometry it could reference, and a Body's tree became a list of operations with their inputs deleted. User feedback on the prototype said as much.

So: sequence won, and reuse moved to annotations. A feature carries a chip per profile it reads; a profile's detail strip names every feature that depends on it. Nothing was lost except a pane.

The lesson worth keeping is not "the shelf was wrong". It is that **two true things about an object can want opposite layouts**, and the one that wins is the one the rest of the application already assumes. PartDesign is a history modeller. The history had to be the spine.

### Rules

1. **Lifting.** An object is lifted when something *uses* it: it is claimed by a non-container that also links to it through a property that is not containment. It leaves that claimer's child list and is re-homed onto the container it belongs to — its `Group` owner first, falling back to the nearest container ancestor of whoever claimed it — with a chip left behind on the user. Something with no container at all becomes a root, which is what a loose sketch or an orphaned tool solid actually is.

    Holding is not using. A Body lists its members through `Group` and an Origin reaches its planes through `OriginFeatures`; both are containment, both are filtered out, and lifting on them would empty every tree in the document.

    Sketches are the exception that proves the rule: anything derived from `Sketcher::SketchObject` is lifted whether or not something reads it yet, because an unused sketch is either the next operation's input or leftover rubbish and both belong in the timeline where they were drawn. An optional `widen` flag extends that to `Part::Part2DObject` (Draft wires, circles, b-splines), which are reused the same way.

    **Part workbench operations nest exclusively.** A `Part::` operation (Cut, Fuse, Common, Extrusion, …) owns what it combines: its operands exist to be consumed, so they stay nested under it and the tree reads as the CSG structure it is. Profiles are still lifted, so sketches keep their place in the timeline; the operation that reads one always carries a chip naming it (a *pinned* reference, shown whatever its severity), and the sketch lists its users in its detail strip rather than growing chips of its own. PartDesign features keep the ordinary lifting rule.

    **Expression layout (the default; `PartLayout` = `expression`).** Each Part model is headed by its latest operation — one that nothing else reads — and every step it was built from is listed flat beneath it, oldest first, each operation chipping every input it reads. A file of five models has five roots. Order is a topological sort with creation order breaking ties, because a property can be repointed at something newer. An input two models share stays with the model created first; the other chips it. `PartLayout` = `nested` gives the exclusive-nesting layout above instead.

    **Free sketches and datums are filed, not nested.** Sketches and datums outside any Body are collected into panel-only groups titled "Sketches" and "Datum Objects", expanded, sorted by label number-aware, at the bottom of the document — or at the bottom of their App::Part, so nothing is shown away from the part it belongs to. Panel-only because a real Std_Group would restructure the document, add undo steps nobody made, and shift a sketch in space when it left an App::Part. They are named with a `~` prefix, which no FreeCAD object name can contain, and every bridge path that reaches the document skips them. Binders (`PartDesign::ShapeBinder`, `SubShapeBinder`) are PartDesign types but outside a Body are treated as ordinary Part inputs, nesting as a step of the model that first reads them. Body sketches stay in the Body timeline; a sketch the user put in a group of their own stays there; Origin planes and axes stay with their Origin. A model's steps no longer list its sketches, but `sources` still includes them, so scrubbing back before an Extrude still shows its sketch, and the Extrude's chip still reaches it.

    **Part models get a history bar.** Part operations never alter their inputs, so every intermediate result already exists and rolling back is visibility only: at step N, show whatever in the first N steps nothing else in them has consumed. No recompute, so scrubbing is cheap. The bar below the last step means the finished model, so the state immediately before the final operation is not a separate stop. There is no Tip property, so the panel remembers the position; it is a viewing position, not an insertion point, and when a model gains a step the bar snaps back to the finished model and its visibility is restored. Cancelling a drag restores visibility explicitly, since undo does not cover view state.

    `is_profile` and `is_lifted` are therefore different questions and are asked separately. Only a sketch has a solver to report on; anything lifted has a list of what depends on it.
2. **Order comes from `Group`.** `Group` is the container's own record of what was added and when, and it survives renaming, re-tipping and reordering. Members it does not mention — a Body's Origin — have no timeline position, so they keep claim order and lead. With no `Group` to read, claim order is the backbone and a lifted profile slots in just ahead of the first sibling created after it, so it still lands where it was drawn rather than at the end. This was checked against a real model with `probe.timeline()` rather than assumed; the fallback exists because "checked on one build" is not "true everywhere".
3. **A profile is a leaf.** Anything a profile claims is re-homed onto the profile's nearest non-profile ancestor. A timeline row that can be expanded is a timeline row with a depth, which is the nesting this paradigm exists to remove — and it stops a Draft array whose only claimer is a sketch from vanishing.
4. **A chip on a row means something is wrong with what it names.** Not "this row has a reference" — every row has references, and a marker on every row is a marker nobody reads, the same mistake the per-row staleness dot and the open-sketch count made. What a feature reads is worth knowing and lives one click away in its detail strip; what is *broken* is worth interrupting for, and only that interrupts.

    The filter is the severity of the thing referenced, not of the row. A feature with four references and one bad sketch shows one chip, which is the one worth looking at. The row's own gutter mark already says this row has a problem; the chip says whose fault it is — so a feature that failed because its sketch is broken reddens the *chip naming the sketch* and leaves its own label normal. Blaming the feature would light five rows for one fault.

    This replaced chipping every reference. That version was considered and built, and seeing it on a real model settled it: the chips had become a catalogue, and a catalogue is read once and then ignored. Clicking a chip selects and scrolls to what it names; double-clicking opens it for editing.

    **Every reference gets a chip, including a reference to part of something.** A pocket built up to a selected face of an earlier pad is reading that pad, and the chip says so — `Pad:Face3`. That case used to show nothing at all, and the reason is worth recording: references were read *backwards*, from each lifted object's `InList`, so only something the timeline had lifted could have a chip pointing at it. The owner of a face is a solid in the Body, claimed by a container, and therefore never lifted. Read forwards from each object's own link table instead, every reference is found the same way and the "used by" list falls out as the inverse for free.

    Sub-elements were also being dropped by the link reader: a `LinkSub` value was flattened to its object and the element names discarded as not-an-object. `link_entries` now returns `(object, [sub-elements])` for all five shapes FreeCAD uses. The `LinkList`/`LinkSub` ambiguity is the trap — both arrive as a two-item sequence, so the *shape* has to be checked rather than the length.

    Adjacency earns no exception. The row above a feature is often the sketch it reads, but not always, and if an absent chip could mean either "no reference" or "the reference is right there" it would stop meaning anything.

    **Two references are true and not worth saying, and both are filtered.** A feature attached to a face of the Body it lives in is telling you which Body it is in — which you can see, because the row is inside it. So a reference *upwards*, to any ancestor of the referring row, gets no chip; reading every link forwards turned that into a chip on almost every row that said nothing on any of them. Sideways references are untouched, and those are what the chips exist for.

    And a sketch reference names no sub-element. A feature reads a sketch, whole; the edge index an attachment happens to land on is a detail of *how* it is attached rather than something anybody chose, and `Sketch:Edge3` reads as though it mattered.

5. **A row spends the width it has.** One chip is named. Two or more collapse to their own FreeCAD icons, about a sixth of the width each, with a small badge where the reference is to a sub-element rather than the whole object.

    So does a single chip whose name will not fit — past 16 characters, or on a panel narrower than 240px, it falls back to its icon too. **Whole name or clean icon, never a fragment**: an elided `Mounting_Brack…` costs the width *and* still makes you hover, which is the worst of both. Measured in `tests/test_qml.py`: a named chip is 51px, two icon chips are 28px, and a 29-character name draws a 14px icon rather than a truncation.

    The icons are worth more than a generic glyph once the label is gone — a sketch, a datum plane and a solid are three different pictures, and telling them apart is most of what the label was doing. The names are one click away: a row whose chips collapsed always has a detail strip, and that strip lists every reference in full, with the part it names.

    They are served **desaturated**, and dimmer still until pointed at. A chip names something the row depends on rather than something about the row, and FreeCAD's icon palette is saturated enough that a cluster of them outshouts the labels beside it. Grey keeps the silhouette, which is the part doing the work. The desaturation happens in the image provider rather than in QML: Qt's own effect lives in modules this build may not ship, and a shader would be paid for on every frame where this is paid once and then cached. Transparency survives it because the conversion goes through ARGB and recolours — `Format_Grayscale8` has no alpha channel, and the direct route fills every transparent pixel with black.
6. **Forward references do not.** A lifted row carries no "used by" chips, deliberately. A sketch used by six features would grow a row six chips wide and the timeline would stop being scannable, which is the whole reason the sketches came back into it. That list lives in the lifted row's detail strip, where it costs nothing until asked for — and a lifted row always has a detail strip for that reason, even when there is nothing wrong with it. Sequence usually puts a sketch next to its consumer anyway; the cases where it does not are exactly the reused ones, and those are worth one click.
7. **Consumption vs containment.** A Body links its sketches through `Group`; that is not a use. Link properties named `Group`, `Origin`, `OriginFeatures`, `Tip`, `BaseFeature` are filtered out, so a use count means what it says.
8. **One consumer per object, not per link.** `InList` carries an entry per link, so a feature reaching its sketch through two properties appears twice. Consumers are merged by object and the property names collected, which is what keeps a Pad from reporting itself as two users of the same sketch. A sketch using another sketch's external geometry *is* a genuine consumer, so a count can legitimately exceed the number of features involved.
9. **Reciprocal highlight.** Pointing at a row marks the rows related to it: hover a profile and every feature consuming it is outlined; hover a feature and the profiles it reads are outlined. Both directions now land in the one list. Outline plus a half-strength fill, deliberately weaker than hover and unrelated to selection, which belongs to FreeCAD rather than to the panel.
10. **The bar is a boundary, not a pointer.** PartDesign exposes history through the Tip: the Body shows the state at the tip, and new features are inserted after it. So a Body gets one draggable bar sitting in the gap *between* two rows — everything above it is built, everything below it has not happened yet.

    This went bar → arrow → bar. The arrow was right while the panel drew only features and the marker pointed at the one the Body was showing. Once sketches came back into the sequence the boundary reading is the one that matches what the user sees, and a bar says "everything below here is different" where an arrow says "this row".

    Only a solid feature can be a tip, so the bar travels freely over the sketches in between and the Python side decides what a resting place sets: the last feature at or before it. Parking under a sketch is not an error and does not move the bar. Above the first feature the bar cannot go, because there is no feature to roll back to and `Tip = None` is not a state worth risking on someone's model.

    **Where the bar rests is not the same fact as which feature it sets**, and conflating the two is what made dropping it between two consecutive sketches feel wrong: it would set the feature above them, then snap back to that feature's row, moving away from where the user had just let go of it for no reason they could see. The bridge records the resting place as the *object* whose row the bar sits under — an index would not survive a branch being expanded — and honours it only while it still resolves to the current tip. Any other route to moving the tip clears it and the bar returns to the tip's own row, so nothing has to know this exists.

    **Where it is drawn and which slot it is in are separate answers.** The slot has to quantise — it decides which feature gets set, and that cannot be a fraction — but quantising the drawing too made the bar jump a whole row at a time under a smoothly moving hand, which reads as the panel stuttering rather than as the bar snapping. Held, it follows the pointer continuously, offset by wherever in its height it was taken hold of so it does not leap to centre itself on the first press; released, it animates onto the boundary. The preview still fires once per row crossed rather than once per mouse move, because that is the expensive half.

    The bar is a rule with a knob at each end and nothing else. It carries no label and no step counter: a bar that says "9 / 14" is answering a question nobody asked mid-drag, and the rows it is moving through already say where it is. The knobs are the affordance — a line on its own says "boundary" but not "grab me", and this one has to say both. The whole strip drags, not only the knobs; they mark where to take hold of it rather than restricting it to two small targets.

    In overlay mode the bar stops 12px past whichever of its two neighbours reaches furthest right, rather than spanning the list. Docked there is a full-width row under it and a rule across the panel reads as a divider; in overlay there is no row, only two pills, and a line running off past both of them reads as something drawn on the 3D view.

    Everything past the bar goes inert. Two cues, on purpose: the rows dim, **and** the vertical spine down the Body's children switches from solid to dashed. Dimming alone is a brightness difference, which is the cue that survives worst; solid and dashed are different shapes and stay different in greyscale, at a glance, and for anyone whose colour vision would flatten the rest. A sketch past the bar is dimmed too — at that moment it had not been drawn.

    The spine moves in overlay mode rather than disappearing with the other rules. There is no continuity to draw — the rows are separate pills over the model — so it sits just inside the pill's left edge and appears only on the rows past the bar, where it is saying something. Dropping it entirely, as the ancestor guides are dropped, would leave the rolled-back state carried by dimming alone in exactly the mode where the background behind it is least predictable.

    Everything that is *not* a stack member keeps its eye: the Body itself, datums, binders, groups, loose Part objects. Two controls for one piece of state would disagree the moment either was used. The eye keeps its slot on feature rows even though it is never shown there, so the gutter mark to its right lands at the same x on every row.
11. **The tree is searched, not filtered.** Filtering a tree to show a match throws away the context that makes the match meaningful — a Pad found under a Body appears at a depth with nothing above it — and leaves the user to undo the search before they can carry on. So the search box returns somewhere to *go*: hits appear in a list under the field, and choosing one opens the path to it, selects it and scrolls it in. The tree itself is never touched. Labels rank ahead of internal names, and a prefix hit ahead of one in the middle. There is one list now, so there is one destination; the shelf's separate filter went with the shelf.
12. **Rename edits `Label`, never `Name`.** `Name` is the immutable identifier every link in the document is written against, and the panel addresses rows by it. F2 does it from the keyboard.

    By mouse it is a **single click on the name of a row that is already the selection** — the file-manager gesture. It cannot fire on the click that *made* the selection, or a row could never be selected by its name without dropping into an edit box, and it is hit-tested against the label's *glyphs* rather than its box, which runs most of the width of the row: clicking the empty space beside a short name is not clicking the name.

    It is armed rather than immediate, on a timer set from the platform's own double-click interval, because the first half of a double click is indistinguishable from it until the second half arrives. A double click, a drag, or losing the selection all cancel it.

    **A double click anywhere on the row opens the object for editing.** That is what a double click means everywhere else in FreeCAD, and the earlier arrangement — renaming on the glyphs, editing elsewhere — split one gesture across two invisible zones of the same row.
13. **Status lives in a gutter, detail lives under the row.** Two different sources meet here: `obj.State` carries the document's view — Touched, Invalid, Error — while a redundant constraint leaves State completely clean, because such a sketch solves and recomputes fine. Solver findings come from *properties* on `SketchObject` — `RedundantConstraints`, `ConflictingConstraints`, `MalformedConstraints`, `PartiallyRedundantConstraints`, plus `DoF` — read rather than solved; solving thirty sketches per snapshot rebuild is the same per-rebuild cost that made the tip drag unsafe. `getStatusString()` is the fallback where the typed properties are absent, since that is the string the stock tree puts in its own tooltip and using it verbatim keeps the panel from drifting from the rest of the application.

    Getting here took two wrong guesses at a `getLast*` *method* family that does not exist, both of which failed silently — every accessor was `getattr`-guarded, so a build without them reported a clean document that had a redundant constraint in it. That is the worst failure mode available: it looks like it works. Two things came out of it. Absence of information is distinguished from absence of findings and recorded once on the snapshot (`solver_findings`) rather than per row. And `probe.sketch(name)` dumps every attribute on an object *and its view provider*, calling only what is unambiguously a getter — several names matching "redundant" are the ones that *remove* redundant constraints — because a keyword filter only finds names someone already thought of.

    The mark itself is a fixed-width gutter at the row's right edge, and **shape carries the meaning**: a hollow ring is under-constrained, a triangle with a bang warns, a disc with a bang errors. The disc once carried an x, but a round mark with an x is a close button's shape, and without the red that is what it read as; the two filled marks now share the bang and differ in outline, which the preview at twelve and fourteen pixels showed is enough. Colour reinforces and never carries. Clicking the mark opens a detail strip under the row with the finding in the solver's own words, the constraint state in words rather than a bare number, and the list of features that depend on the sketch.

    Constraint state is a state, not a fault, so it gets the quietest mark and the body text colour. In the document this was built against, 18 of 30 sketches have degrees of freedom left; a warning for that would flag the majority and cheapen the marks that mean something is wrong — the mistake the per-row staleness dot made. A clean sketch shows no mark at all, but its gutter slot stays clickable and shows a faint ring on hover, so the detail strip is reachable without inventing a permanent indicator for "fine".

    The header counts problems and goes to the first one when clicked, opening its detail strip on arrival. The plain profile count that sat beside it is gone: it was large, stable, and had nothing for the user to do about it.
14. **Keyboard actions work on the selection, not on a list's current index.** F2 and Space ask the bridge which single object is selected and act on that, so the panel agrees with what the 3D view and the rest of FreeCAD consider current. Handled at the root of the QML tree, which means a focused `TextInput` — the search box, a rename field — consumes them first and typing a space toggles nothing. Space shows or hides everything selected as one undo step — all the same way: if any is shown they are all hidden, otherwise shown. Up and Down move the selection to the row above or below, from the last row clicked or stepped to; Shift extends it. Shift+click selects every row from the anchor (the last row clicked without Shift) to the one clicked. The list's own key navigation is off, so these keys belong to the panel.
15. **A drag opens the space it is going to land in.** While an object or the bar is being dragged, the row it would land under grows by about half a row height, animated. A drop-target outline says *which* row; the gap says where the thing in your hand ends up, which is the question actually being asked mid-drag. For a reparent that space opens *under* the target, because that is where a new child goes. Two sources feed it — an object drag and a bar drag — kept as separate properties on the list because they can never both be active and neither should have to clear the other's state.

    Note that this indicates a *destination*, not a reorder: dropping an object still reparents it rather than moving it within its Body's history. Reordering the timeline itself is a separate piece of work.
16. **The active container is marked.** Which Body an operation lands in is not a detail you should have to guess at, and the stock tree says it with bold text and a tinted background. Bold is already taken here — every container row is bold — so the mark is a rule down the left of the row, with the tint reinforcing it rather than carrying it. A rule because a background tint is the first thing to go in a greyscale screenshot.

    It is read through `ActiveView.getActiveObject`, trying `pdbody` before `part` — a Body inside a Part is the more specific answer and the one an operation would actually land in — and the result is unwrapped rather than assumed, since some builds answer with a tuple. `probe.active()` prints what this build returns for each key.

    It is **polled**, every half second, which is the one piece of polling in the panel. Activating a Body is a Gui action and emits no document signal, so there is nothing to observe; one attribute read twice a second is far below the noise floor of everything else here, and the alternative is an indicator that silently goes stale, which is worse than no indicator.

17. **Accessibility is a constraint, not a pass at the end.** Every state the panel expresses has a non-colour cue: severity is a silhouette before it is amber or red, rollback is a dashed spine before it is a dimming, hidden is an italic label and a faded icon before it is anything else, and the detail strip says in words what the mark says in shape. The test is whether a greyscale screenshot still reads.

## Properties: the strip and the inspector

The Property view is retired in two tiers. The detail strip opens with the few values that define an object (`properties.KEY_PROPERTIES`, per type), editable in place: a field for quantities and numbers (Return applies, Escape reverts, a leading `=` binds an expression, a plain value clears one), a box for yes/no, chips for a choice. A type not in the table shows no values rather than a guess. Every strip ends with "All properties · N…", which opens the Property Inspector.

The inspector's contents are QML (`Inspector.qml`), laid out with no per-type templates by `inspector.py`: groups are FreeCAD's own (`getGroupOfProperty`), in FreeCAD's order with the group named after the object's type first; each property gets the editor for its kind (quantity, number, text, bool, enum, colour, vector, placement, link), not for its object's type, so addon objects work unchanged; compact editors take half a row and pair up, wide ones a full row; labels split CamelCase as the native panel does; Base, Attachment and the view's style groups start collapsed unless something in them is an expression. Several selected objects show only properties they share by name and kind, differing values as "mixed", and an edit applies to all as one undo step. A kind with no editor, and links, which want picking rather than typing, show "Edit…", which switches the inspector to FreeCAD's own editor; "←" returns. The inspector follows the selection and the undo stack by polling both. Templates, when written, only refine this.

Behind the QML, the inspector (`property_inspector.py`) borrows FreeCAD's own `Gui::PropertyView` and puts it back exactly where it was — dock, splitter, tab, box or grid layout; the Property view dock uses a grid. Borrowing rather than rebuilding keeps every editor FreeCAD has, editing several objects at once, and property types other addons register. It is a QWidget frame, not QML: a QWidget cannot be hosted inside a QtQuick scene. It is a child of the main window, not a window, because Wayland lets no application place its own windows. Unpinned it opens level with the row, beside the dock's border in both modes, and a click elsewhere closes it. Opening beside the row's pill in overlay mode was tried and dropped: the inspector is a plain child of the main window, so an overlaid panel — whose QtQuick view composites above everything else in the window — drew over it. Making the inspector a native window of its own fixed the stacking but fought FreeCAD's overlay manager: moving and resizing the inspector, and rearranging docks, became nearly impossible. Beside the dock, nothing overlaps. Pinned, it follows the selection and reopens where it was left; position, size and pin state live under `Mod/Nxt`. A failed return detaches the editor rather than leave it inside an inspector a reload would destroy.

## Architecture

Dock-hosted first (`QQuickWidget` in a `QDockWidget`, tabbed beside the stock Model tree), with nothing below `panel.py` aware of the dock.

| Layer | Module | Note |
|---|---|---|
| Snapshot | `scene.py` | Pure Python, no Qt. Hierarchy from `claimChildren()`, profile lifting, timeline order, consumer index. |
| Icons | `icons.py` | `QQuickImageProvider` over live `ViewObject.Icon` — keeps FreeCAD's C++ overlay composition instead of reimplementing it. |
| Theme | `theme.py` | Colours mixed from the live `QPalette`, so the panel works in whatever style the host runs. |
| Models | `models.py` | One flat `QAbstractListModel`, `depth` as a role. |
| Commands | `bridge.py` | The only thing QML may call. Owns transactions. |
| Sync | `observers.py` | App + Gui + Selection observers. |
| Host | `panel.py` | Dock and engine wiring. |
| View | `qml/` | `NxtTree.qml` plus the `Nxt` component module. |

The rollback bar is an overlay over the tree list, not a row in the model. Keeping it out of the model means expanding a Body or scrolling never has to reshuffle the row sequence, and several Bodies each get their own bar for free. `TreeRowModel.rowsRefreshed` tells the bridge to recompute bar positions, because an expand/collapse moves them without the document changing at all.

Rows are **no longer a uniform height** — an open detail strip makes that one delegate taller — so the bar asks the list where a row is (`itemAtIndex`) and which gap a pointer is in (`indexAt`) rather than multiplying an index by a row height. The arithmetic survives only as the fallback for a row the list has not realised, which is off screen and clipped anyway. That turned out to be simpler than the arithmetic it replaced, not harder: `indexAt` is one call where the old code had a division and a clamp.

Row detail is a property of the row, not a second model row. A synthetic row would have to be diffed, named and addressed like a real one, and every index-based caller would need to know which kind it had.

The stack is *the chain through the Tip*, not the contents of `Group`. Every PartDesign feature points at its predecessor through `BaseFeature`, so walking back from the tip and forward from it recovers the linear history exactly; with no tip to anchor on, the longest chain wins. Anything in the Body that is off that chain is excluded rather than guessed at, because the tip can only ever move along the chain and offering any other row as a target is a lie.

That rule is what keeps a MultiTransform's sub-transformations out. They derive from `PartDesign::Feature` and carry a `BaseFeature` property, so a type filter does not exclude them and neither does requiring that property; only their absence from the chain does. The MultiTransform itself stays — it is a genuine history step, and rolling back to it is as meaningful as rolling back to a Pad. Datums and shape binders are excluded earlier, by the `BaseFeature` requirement.

Dragging the marker rolls the model live, under one transaction. `beginTipDrag` opens it, `previewTipRow` applies each feature as the bar passes it, `endTipDrag` commits — so a rollback across six features is one undo step, not six, and dragging back to where you started aborts rather than leaving an empty entry. Two things make this survivable:

- **The marker descriptors are frozen during a drag.** `Repeater` rebuilds every delegate when its model changes, so emitting `tipBarsChanged` mid-drag would destroy the marker under the cursor and drop the mouse grab. The signal is held until the drag ends. Row `dataChanged` is unaffected, which is how rows dim live while the bar passes them.
- **Live preview yields on slow documents.** The first applied step is timed; if a recompute costs more than ~120ms the drag stops applying and falls back to commit-on-release, with a line in the report view saying so. Better an honest non-live drag than a stuttering one.
- **The apply never runs on the mouse handler's stack.** `previewTipRow` records where the marker has got to and returns; a zero-timer does the work from the event loop. Qt's contract is that an exception must not propagate out of an event handler — it terminates the process rather than unwinding — and a recompute on an old or damaged model is exactly where a feature throws. Off the handler, the exception has a Python frame to be caught in. Queuing also collapses a burst of moves, so crossing four features during one recompute applies only the last.
- **A recompute can re-enter the drag.** FreeCAD's progress indicator calls `processEvents`, so a mouse move — or a mouse *release* — can arrive in the middle of an apply. The drain loop is re-entrant by design rather than by accident: a guard turns a mid-apply move into another lap instead of a nested recompute on a document already inside one, and a release sets a flag and defers its commit rather than closing the transaction in the middle of the change it is meant to contain.
- **Only the Body is recomputed.** Moving the tip touches the Body and nothing else — the features are already up to date — so `doc.recompute([body])` rather than the whole document. That is also the difference between a recompute fast enough to pass unnoticed and one slow enough to raise the progress indicator in the first place.

Moving the tip is two operations, not one. Setting `Body.Tip` alone leaves the Body drawing its old state, because FreeCAD shows a Body through exactly one visible feature; the stock Move-tip command also hides every other stack member, and so does `bridge.setTip`.

Tests live at `../../tests/`. `test_scene.py` stubs FreeCAD, so the ordering
and rollback logic runs headlessly with no GUI and no install. `test_qml.py`
loads the real QML in an offscreen `QQuickView` against stub context objects
generated from `theme.py`, `models.py` and `bridge.py` themselves, so it
cannot drift into testing an interface the panel does not have. It checks
what `qmllint` cannot: that every delegate is created, that no binding loops,
and — the reason it exists — that the bar still lands on the right boundary
when a row above it is taller than the others.

Two things that harness taught, both of which had it passing while testing
nothing. Items outside a window are never polished, so a `ListView` in a bare
`QQmlComponent` realises no delegates at all; it needs a real `QQuickView`.
And real time has to pass, not just event turns: the bar animates into
position, so a `Behavior` that never advances leaves it where it started,
which looks exactly like a positioning bug.

### Four decisions worth recording

**Flat list models, not `QAbstractItemModel` + Qt Quick `TreeView`.** A Python item model has to hand out stable internal pointers for every index; getting that wrong in a document mutating underneath is a segfault, not an exception. And indentation here is presentation, not structure — a `depth` role is what lets profiles be lifted out without the tree knowing they were ever there.

**Rebuild and diff, not incremental mutation.** Every document signal calls `invalidate()`, which coalesces a burst into one rebuild on the next event-loop turn. The new row sequence is diffed against the old with `SequenceMatcher` and applied as insert/remove, so the ListView keeps scroll position and delegate identity instead of flashing on every recompute.

**No `QtQuick.Controls`.** The panel is embedded in a host whose Qt style is not ours. The few primitives needed (scroll indicator, text field, the drawn glyphs) are cheaper to draw than to restyle.

**Colours come from the stock tree, not from `QApplication`.** A Qt stylesheet and the platform palette are different things: `QApplication.palette()` follows the desktop theme and knows nothing about a stylesheet, so FreeCAD's light stylesheet on a dark desktop paints this panel in colours nothing around it shares. `QStyleSheetStyle` does resolve its rules into each widget's own palette when it polishes that widget, so `theme.py` reads a *reference widget* — the stock tree view, whose stylesheet rules are the ones written for trees — and takes background roles from its viewport, where `QTreeView { background-color: ... }` actually lands. `StyleChange` / `PaletteChange` on the dock re-reads it, deferred a tick because the dock may be polished before the widget it borrows from.

## v1 scope

In: selection sync both ways, visibility toggles, sketch health in the row gutter with an expandable detail strip, the PartDesign rollback bar, drag-drop reparenting, expand/collapse, inline rename (double-click or F2), search, reference navigation, isolate.

Out for now: context menus, multi-document tabs, arrow-key navigation, cross-Body `SubShapeBinder` creation.

Custom context menus are wanted and are the next piece of work on this panel. The stock tree's actions are C++ `QAction`s, so the choice is between rebuilding the menu in QML over `bridge.py` slots, or bridging to the existing `QAction`s and losing control of presentation. That decision is not made yet.

## Overlay mode

The panel can drop its own background and float over the 3D view. Toggled by `Nxt_ModelPanelOverlay`, independent of where the dock actually is — this changes what the panel *paints*, not where it lives, so FreeCAD's own overlay commands stay in charge of docking, auto-hide and edge strips. That split is the point: the host keeps the window behaviour it already knows how to do, and the panel supplies the appearance.

**The backdrop is per-row, not panel-wide.** A translucent sheet over an arbitrary model is unreadable in one half of the frame or the other — a pale scrim dies over a light background, a dark one dies over a dark model. Instead each tree row draws a rounded pill sized to its own content, so the scrim exists exactly where the text is and nowhere else. Disclosure arrows fall outside the pills, on bare transparency, which is what makes the result read as floating labels rather than as a translucent panel. The idea is lifted from FreeCAD's OpenTheme addon, which solves the same problem the same way.

Everything right of a row's label lives in one container, `tail`, positioned by assigning `x` rather than by anchoring: pinned to the right edge when docked, following the label in overlay mode. Docked, the label measures to the tail's *width*; in overlay, the tail measures to the label's width.

That first clause used to say the tail's *position*, on the reasoning that the dependency ran one way in each mode and so could never cycle. True in each mode, false across a switch: every theme property shares one `changed` signal, so a mode switch re-evaluates the label and the tail in the same pass and each can catch the other still in the old mode — one binding-loop report per row. A second path hid behind it: in overlay the label read its own `implicitWidth`, which an elided `Text` re-emits on every width change. It now measures with a separate `TextMetrics`. `tests/test_qml.py` flips the mode live and fails on any loop, because a fresh load in either mode never exercises the switch.

Two earlier shapes were both wrong, in opposite directions. Switching anchors on the mode change left items holding stale geometry, which showed up as root rows stuck at the wrong pill width: only a delegate rebuild cleared it, so expanding a branch fixed its children while a childless root stayed wrong for the session. Replacing that with a single width binding that subtracted `chips.width` closed the loop the other way, because the chips were anchored to the label's right edge — `title.width → chips.width → chips.x → title.right → title.width`, which Qt reports as a binding loop on `width`. Neither the anchors nor the arithmetic was the problem; having the label and the things beside it measure *each other* was. Ancestor guide lines are suppressed — a rule drawn across the 3D view reads as part of the model.

Pill colours come from the palette like everything else (`pill`, `pillHover`, `pillBorder`), so the backdrop inverts with a dark stylesheet instead of being a hard-coded white.

**A `QQuickWidget` is opaque until told otherwise.** It renders into its own composited surface with an opaque clear colour, so overlay mode sets `WA_TranslucentBackground`, `WA_AlwaysStackOnTop` and a transparent clear colour together — the attributes and the clear colour have to agree, or the scene graph composites over black rather than over what is behind it. This combination is known to be fragile on some drivers; if it fails, the fallback is a `QQuickView` in a container window, at the cost of new stacking problems against the Coin3D viewport.

**Scene graph resources do not survive a reparent.** Dragging the dock to another edge puts the widget in a new top-level window and therefore on a new QRhi, while the scene graph still holds textures created on the old one — Qt says so, once per frame: *"Texture … belongs to QRhi …, but client code attempted to use it with QRhi …"*. `QQuickWindow.releaseResources()` on `ParentChange` forces them to be recreated against the rendering context the widget actually has now.

**Scrolling strands the previous frame.** `WA_AlwaysStackOnTop` is what lets a translucent `QQuickWidget` show widgets underneath at all, and it is also documented to cause rendering artifacts — moving content does not ask the surface behind to redraw, so old pills linger in the transparent gaps until something unrelated repaints the area. The list calls back into the panel on `contentYChanged`, and on every other signal that can move content, which updates the widget and its parent. It is a nudge rather than a fix; the underlying behaviour is Qt's.

**The dock detects its own overlay state.** FreeCAD's overlay manager offers no API for this — it reparents the dock into a container of its own — so the panel walks its parent chain looking for a class name containing `Overlay`, on a deferred check after reparent, show, move and resize. A name match is a heuristic, so it only ever switches the panel's own painting; nothing load-bearing depends on it being right. When the host has overlaid us the dock's title bar is hidden, because the overlay manager supplies its own chrome and its own way back out, and a solid bar above a background-less panel looks like a mistake. A *hand-toggled* overlay keeps its title bar — otherwise there would be no way to toggle back.

The title bar is ours now, carrying an overlay toggle. Replacing it costs the dock's stock float and close buttons, so those are rebuilt rather than quietly lost.

Known gap: the panel still captures mouse events across its whole rectangle, including the transparent gaps between pills, so there is no click-through to the 3D view the way FreeCAD's own transparent overlay mode offers. Fixing it properly means masking the widget to the union of the visible pill rectangles and updating that mask on every scroll and relayout.

## Startup and persistence

The panel opens itself when FreeCAD starts, from `init_gui`'s deferred setup — deferred because the main window does not exist while `InitGui` runs.

State lives in FreeCAD's own parameter store (`BaseApp/Preferences/Mod/Nxt`) rather than a file of ours, so it travels with the user's configuration and needs no migration of ours. Reads never raise: a corrupt or absent preference gives a working panel, not a stack trace at startup.

What is persisted is what nothing else will restore for us. The main window's saved state restores dock geometry, but only for docks that exist when it is read back — and this one is created by an addon long afterwards. So the panel records whether it was open, whether it was floating and where, its dock area, the divider position, and the overlay state.

Overlay was initially left out on the reasoning that FreeCAD's overlay manager persists its own docks. It does — for docks that exist when it runs, which ours does not, for exactly the same reason Qt cannot restore its geometry. The same argument applied and I did not apply it.

Restoring the two kinds of overlay is not the same operation, so which it was is recorded separately. A hand-toggled overlay is just a painting mode and is set directly. A host overlay has to be asked for through FreeCAD's command, which takes no argument and acts on whichever dock it considers current — so *when* it is asked decides whether it lands.

The first attempt asked from `apply_saved_state`, which runs before `show()` and `raise_()`. The dock was neither visible nor focused, so no reading of "current dock" could have selected it; the command was always going to miss. The restore is now deferred: `apply_saved_state` only records the intent, and `show()` schedules `restore_host_overlay`, which shows, raises, activates and focuses the dock first and then issues the command.

The request is still verified rather than assumed: if detection has not confirmed the overlay a beat later, the painting is turned back off and the report view says so. Pills over an ordinary dock background look broken rather than overlaid, and silently leaving the panel in that state would be worse than not restoring at all. What the message does *not* do any more is assert why it missed — the first version confidently blamed the cursor, which was a guess dressed as a diagnosis while the real cause was our own sequencing. It now points at `probe.overlay()`, which lists the overlay commands this build registers, the overlay-related attributes on `Gui`, and any overlay keys in the parameter tree. If FreeCAD stores overlay membership as a list of dock object names, writing `NxtModelPanel` into it is a far better route than aiming a command that takes no target, and the probe is what will show that.

Writes are coalesced, because a drag emits move and resize continuously and the parameter store is not where that traffic belongs. Closing writes immediately instead — there may be no further event-loop turn if the application is quitting.

Tabbing beside the stock tree is a first-run courtesy, recorded by a `Configured` flag. After that the user's arrangement is the arrangement; re-tabbing on every start would quietly undo it.

One startup ordering problem is worth naming: the panel takes its colours from the stock tree, which may not exist yet when the panel opens. `find_reference_widget` returns `None` rather than falling back to the main window, because something that merely works is something the panel would settle for forever; `None` means "ask again later". The panel re-asks at 400ms, 1.5s and 4s, and upgrades when a real item view appears.

## Performance

The panel rebuilds a snapshot of the whole document on every document signal, and until recently a tip drag triggered one of those per feature the bar crossed. That made the drag stutter on a large model. The work below came out of a review with performance as the first priority; the numbers are from a synthetic 408-object document shaped like a real one (eight Bodies of alternating sketch/feature pairs, sketches reused, containers linking their members through `Group`).

**Metrics are cached like the colours are.** `theme.rowHeight` derived itself from a `QFontMetrics` on *every read*, and `tipGutter` called it again — while `rowHeight` is read about a dozen times per row. A relayout of twenty visible rows therefore constructed a few hundred `QFontMetrics` objects, sixty times a second while the bar was moving. `theme.py`'s own docstring had already said colours must not be computed per read; the metrics sitting underneath it were doing exactly that. This was the single largest contributor to the jitter.

**A drag patches the snapshot instead of rebuilding it.** Moving the tip writes `Tip`, writes visibilities and recomputes, and every one of those reaches an observer — so each step re-walked the document, re-read every sketch's solver state and rebuilt every row, to learn a handful of facts the bridge had just written itself. `invalidate()` now remembers the staleness without acting on it while a drag is live, and `Snapshot.retip()` derives the new state from what the snapshot already holds. `retip` is tested against a full rebuild of the same document, because a drag showing one thing and the release showing another would be worse than the cost it saves.

**Only the visibilities that differ are written.** A Body shows through exactly one feature, so a move changes two of them. Writing all of them touched the document once per stack member and woke an observer for each — on a long history, most of the cost of a step.

**One pass, not one pass per pair.** Three costs in the snapshot walk were shaped the same way: asking a question per pair that could be answered once per thing.

| | before | after |
|---|---|---|
| `getTypeIdOfProperty` | 10,072 | 2,952 |
| `claimChildren` | 816 | 408 |
| parent comparisons | 166,464 | 408 |

Typing a property is a call into C++, and working out *which* property of a consumer points at a profile meant typing every property that consumer has. Asked per (profile, consumer) edge, one container answered it once per sketch it holds — a Body in the `InList` of thirty sketches retyped its whole property table thirty times, and every answer was then discarded, because `Group` is containment rather than use. `_link_table` reads each holder once. `claimChildren` goes through the view provider and allocates a fresh list of wrappers, and it was being called once in the claim pass and again while ordering children; the first result is kept and passed down. And bucketing children by parent was a nested scan over every object for every object.

**`getStatusString()` is not called for healthy sketches.** It was the fallback when no typed solver finding fired — which is the normal case — so a thirty-sketch document formatted thirty status strings per rebuild to produce text that only an open detail strip displays. It now runs only where the typed accessors are absent or something is actually wrong.

**`dataChanged` names the rows that moved.** A blanket `dataChanged` over every row makes the view re-read every role of every visible row, and one recompute fires several signals. The model now compares the displayed fields of each node against the previous snapshot and announces only what changed — except when the icon revision moved, which changes every row's icon URL and honestly does mean everything.

**Deferrals go through timers owned by the bridge.** `QTimer.singleShot` is static: it holds a bound method and outlives the object it was scheduled for, so on reload it fires into a deleted C++ wrapper and raises from a callback with nothing to catch it. That lesson was already recorded and already applied to `panel.py`; `bridge.py` had seven of them left.

One finding from the review was deliberately not acted on: `data()` is a linear chain of `if role ==` comparisons, and the roles read most often sit at the end. A dispatch table would save a couple of dozen integer comparisons per role read, which is real but is three orders of magnitude below the C++ calls around it — and it would make the one place that says what every role means harder to read. Left alone on purpose.

`probe.benchmark()` times a capture, a retip, a solver read and a flatten on whatever document is open, so the next round of this targets whatever is actually slow here rather than whatever looks slow from outside.

## What the addon changes outside itself

Two things reached beyond the panel and are now scoped to the feature that needs them.

`QSG_RHI_BACKEND=opengl` was set at `InitGui` import, so installing the addon changed the scenegraph backend for every QtQuick surface in the process whether or not the panel was ever opened. It is process-wide by nature — Qt reads it once, before the first `QQuickWidget` — but it does not have to be *early*. `qtquick.use_shared_graphics_api()` is called when the panel builds its view, still `setdefault` so a deliberate choice in the environment wins, and a FreeCAD session where the panel never opens is now indistinguishable from one without the addon.

What remains, and should: the panel adds a dock to the main window and tabs it beside the stock tree on first run; the Property Inspector borrows FreeCAD's Property editor and always puts it back; overlay mode calls `update()` on the widget behind the panel. All are the addon's purpose rather than side effects, and all are reversible.

The experimental chrome shell (hiding menus, toolbars and docks for a future QML shell, with F12 as its escape hatch) has been removed from this addon, with its saved-window-state machinery; it may return as an addon of its own.

## Gotchas that have already bitten

**Never animate a colour to or from `"transparent"`.** That value is transparent *black*, so `ColorAnimation` interpolates through semi-opaque black — a hover fading in over a light background flashes a grey bar, on two rows at once while one fades in and the other fades out. Row and inspector fills are solid colours animated by `opacity`; anything that needs to stay visible while the fill is faded out (the drop-target border, the `unused` outline) lives on its own item.

**Assign state before emitting `dataChanged`.** The view re-reads `data()` synchronously, so emitting first hands every affected row its previous value and the panel runs one selection behind.

**`InList` is per link, not per object.** See rule 5.

**`TapHandler.tapped` fires again as the second half of a double tap.** A chip that ran its single-click action from `tapped` would re-run it on the way to the double-click one. `singleTapped` and `doubleTapped` separate them.

**Loading the QML calls straight back into the host.** The root component reads the saved divider position on completion, so `setWidget(self._build_body())` re-enters the panel mid-construction. Every attribute a QML-reachable slot touches has to be assigned *before* that call; anything set afterwards is, from QML's point of view, set too late and raises `AttributeError` on the first load.

**PySide6 Qt enums are `enum.Enum`, not `IntEnum`.** `int(someQtEnum)` raises `TypeError` outright, so anything that has to be stored as a number goes through `.value`. Coming back the other way is guarded too — a parameter file outlives the code that wrote it, so an unrecognised dock area falls back to the left rather than being handed to `addDockWidget` as-is.

**`QTimer.singleShot` outlives the object it was scheduled for.** A static single-shot holds a bound method, so on reload it fires into a deleted C++ wrapper and raises `RuntimeError` from a callback with nothing to catch it — which is what filled the console with save-state errors. Every deferred call the panel makes now goes through a `QTimer` parented to the dock, so it dies with it. Restarting one debounces for free, which is what the hand-rolled pending flags were doing.

**Never clear a context property to tear a QML view down.** Setting `nxt` or `theme` to null re-evaluates every binding that reads them, against null — and delegates outlive `setSource(QUrl())`, so the console fills with a TypeError per binding, dozens per reload. There is no correct ordering of "clear the properties" and "drop the object tree"; the properties should not be cleared at all. Deleting the `QQuickWidget` takes its engine, its object tree and every binding with it, in one step and in silence.

**Never destroy a QML object from inside its own signal handler — it is fatal, not merely unsupported.** `QQmlData::destroyed` calls `qFatal`, which aborts the process; the console message says "This behavior is NOT supported!" and then the process is gone. A `Repeater` destroys and rebuilds every delegate when its model changes, so any bridge slot reached from a delegate's handler must not synchronously emit a signal that repopulates the list that delegate lives in. This crashed the tip drag — `endTipDrag`, called from the marker's `onReleased`, emitted `tipBarsChanged` and destroyed the marker underneath itself — and the same shape was latent in the search results, where choosing a hit cleared the query and emptied the list from inside the hit's own tap handler. Both now defer by one turn of the event loop. The rule generalises to anything that can nest an event loop from a handler: `setEdit`, which opens a task dialog, and any `recompute`, which can raise FreeCAD's progress indicator.

**A child property with its parent's name shadows it.** `property color ink: root.ink` on a `Canvas` inside an item that also has `ink` reads as a binding loop, because inside that scope the unqualified name resolves to the child's own property. Repaints are driven from the owning item instead, and the `onPaint` reads `root.ink` explicitly.

**A guard that runs before the code it guards is not a guard.** `_break_parent_cycles()` was called straight off the claim pass, and two re-homing passes then rewrote every profile's parent underneath it — so a cycle introduced by the re-homing was never cut, and the objects in it would have vanished from the panel with nothing to say why (every node in a cycle has a parent, so none of them is a root). Found by review, not by a bug report, which is the good case. It now runs after the passes it protects, and the other guard next to it was renamed to `_drop_self_children`, which is what it actually does.

**A command that takes no argument acts on some implicit target, and "implicit" is a thing to establish, not assume.** `Std_DockOverlayToggle` has no parameter, so it picks a dock by itself. Calling it during startup restore — before the dock was shown, raised or focused — could not have worked under any rule it might use, and the failure message I wrote asserted a specific cause (the cursor) that I had never checked. Two separate errors, one of them the same guess-instead-of-inspect that cost two rounds on the sketch solver API. Sequence first so the call has a chance, verify the result, and when it still fails, dump what the build actually offers instead of narrating a theory.

**A component is not dead weight just because its name no longer fits.** `FilterField.qml` was the shelf's filter box and was deleted with the shelf — while `SearchBox` was still built out of it. Nothing caught it until an audit script cross-checked every component reference against `qmldir`, because QML resolves types at load time and there was no load between the deletion and the audit. The file came back as `TextField.qml`, which is what it always was. The check is now part of `tests/audit_qml_refs.py`, along with every `nxt.*`, `theme.*` and `host.*` name the QML uses and every `required property` on `TreeRow`, matched against the Python that has to supply them.

**A field that fades out loses its border with everything else.** The overlay pass set the search field's background rectangle to `opacity: 0`, which took the border with it and left a placeholder floating in the header with nothing to say it was a target. Fill and border are separate decisions: in overlay the fill steps down to the chip colour and the border stays at full strength.

**Moving something that is not in the list still strands the frame behind it.** The overlay repaint nudge was wired to every signal the *list* emits, so the timeline bar — which is an overlay item, not a row — left a black rule painted across the model at its previous position every time it moved. Anything that moves in a translucent `QQuickWidget` needs the nudge, not just the thing that scrolls.

**Deleting a visual element by its span deletes whatever was sitting in that span.** Replacing the bar's grip and counter meant replacing the block between two landmarks in the file, and a function that happened to live in that block — `slotAt`, which every drag calls — went with it. Nothing in the file referenced it above the deletion point, so it read as complete. The offscreen harness caught it because it calls the function; an audit of names would not have, because the call site and the definition disappeared into the same hole. Replace by *what a thing is* rather than by where it sits.

**Two places deciding the same thing will eventually disagree.** The gutter mark asked "does this row have anything to show?" and the detail strip asked it again, separately — and the answers differed for an ordinary feature that something else was built on: the mark counted its consumers, while the strip would only list consumers for a *lifted* row, and a feature is never lifted. The result was a mark that opened an empty box. Each section of the strip now states its condition once, the strip exposes `hasContent`, and the mark reads that. The regression test is the general form rather than that row: no row may offer a detail strip and then open an empty one.

**The same control in two places must behave the same way in both.** Chips in the detail strip were click-to-reveal only, while chips on a row were click-to-reveal *and* double-click-to-open. Nobody decided that; the strip was written later and the second handler was simply not carried over, so a sketch reached through the strip could not be opened while the same sketch reached from the row could. They now share both gestures and the hover highlight.

**A results popup must outlive the focus loss that a click on it causes.** Closing the list the moment the search field loses focus dismisses it before the tap reaches a result. A short timer defers the close.

**A row-wide `MouseArea` must sit below the row's own controls.** A `MouseArea` that accepts a press takes an exclusive grab, and delivery runs topmost-first, so one declared last at the default `z` silently kills every `TapHandler` beneath it — the expander, the reference chips and the visibility dot all looked decorative because of this. Plain `Rectangle` and `Text` do not accept mouse events, so `z: -1` on the `MouseArea` costs nothing and revives the controls.

**Small icons are drawn, not glyphed or shipped.** The eye toggle and the disclosure arrow sit at roughly 14 logical pixels, where a font glyph is at the mercy of hinting and a bitmap at the mercy of the display scale factor. A `Canvas` redraws at whatever size and colour it is handed, which also means it follows the host stylesheet through an `ink` property without a second asset for light and dark. Proportions were tuned by rendering the shape at its real size — the first pass had a pupil large enough to fill the almond, and the open eye collapsed into a blob.

The same applies when matching an asset from the host theme. The disclosure dart is redrawn from the proportions measured off the stylesheet's `branch_closed.svg` rather than loading the file: one shape covers both states, because the open branch icon is the closed one rotated a quarter turn, and nothing gets resampled at another row height or scale factor. Its colour is pinned to the theme's own `#495057` rather than following the palette — the one deliberate exception to the rule above, and the one thing in the panel that will not track a dark stylesheet.

Size has a floor here that the eye toggle does not: below about 8px the notch in the dart's back edge stops resolving and the glyph degrades into a plain triangle, which is precisely the shape it exists not to be.

**The visibility control appears on hover only.** In PartDesign everything below the tip is hidden, so an always-on state indicator becomes a column of things that read as radio buttons. Hidden-ness is already carried by the dimmed icon and the italic label, so the control shows up when it is actionable.

**A command that takes no argument acts on some implicit target, and "implicit" is a thing to establish.** See the startup section: `Std_DockOverlayToggle` was being called before the dock was shown or raised, which no reading of "current dock" could have made work.

## Unverified assumptions

The sandbox this was written in has no FreeCAD, so these are guarded in code but unconfirmed. `from freecad.nxt.tree import probe; probe.run()` reports on all of them.

- `ViewObject.claimChildren()` reachable from Python for C++ view providers. Falls back to `Proxy.claimChildren()`, then to `Group` containment.
- `canDragObject` / `dragObject` / `canDropObject` / `dropObject` exposed on view providers.
- `QtQuick` / `QtQuickWidgets` importable from FreeCAD's PySide6.
- `QSG_RHI_BACKEND=opengl` (already set in `InitGui.py`) is enough to keep the scenegraph off Vulkan alongside the Coin3D viewport.
- `Body.Group` lists every member, sketches included, in creation order. Confirmed on one model with `probe.timeline()`; the code falls back to claim order plus document order where it is absent or empty, and `probe.timeline()` prints both side by side so a disagreement is visible rather than silent.

## Open questions

- Should dropping an object between two rows reorder the timeline, rather than only reparenting onto a row? The gap animation already draws the destination; the operation behind it does not exist yet.
- Should the bar be draggable past the last feature, into the trailing sketches? It currently can be, and "everything is built" is the same state wherever it rests down there. Harmless, or confusing?
- Should more than one detail strip be open at a time? One at a time keeps the panel short; several would let two sketches be compared without scrolling between them.
- Does the reference chip scale? A Body with a dozen pads each showing chips may need the chips to move to a hover-reveal.
- Should a container other than a Body — an `App::Part`, a group — get a spine too? It has an order but no tip, so the line would say "sequence" without saying "rollback".
