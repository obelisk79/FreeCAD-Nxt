# Inspector templates and task panels

A **template** (`resources/inspector/<workbench>.toml`) lays out an
object's properties as cards in the Property Inspector. The same template
replaces the parameters box of FreeCAD's task dialog for that feature, so
editing in either place looks and works the same. The format is documented
at the top of `partdesign.toml`; read it before writing one.

## Principles

- **Consistent structure.** Model new templates on `pd-extrude` (Pad and
  Pocket): a heading-less card per step of the operation, in the order a
  user thinks about it:
  1. *Profile / Path*: what is used (sketch, spine, sections).
  2. *Extent / Sections / Orientation*: how far, how it travels, with the
     shape-changing choice as a `segmented` editor at the top.
  3. *Start / options*: the less common controls, shown only when relevant.
  4. *Result*: `Refine` as "Merge faces" (switch), operation choices.
- **Show only what applies.** Use `show_if` so a field appears only in the
  modes that use it. Properties the feature inherits but doesn't use (the
  wiki marks them N/A) go in `hide`. Superseded properties go in `hide_if`.
  Rarely changed ones go to "Everything else" with `group_as`.
- **Nothing goes missing.** Every property the template doesn't name is
  still listed under "Everything else" in the inspector.
- **Friendly words for FreeCAD's values.** `choices` maps raw enumeration
  values to short labels ("ThroughAll" → "Through all"). Map *every*
  value a user sees, including ones like `SideType`'s, or they won't
  translate. Use `omit_if` to drop values that don't work (the wiki says
  so) or are superseded.
- **Short labels**: "Taper", "Up to", "Merge faces". Hints for the rare
  sentence.
- **One template, several FreeCAD versions**: names a version lacks are
  skipped; write for both old and new property sets.
- `couple` when one mode is another at zero (Profile plane = Offset 0), so
  the 3D handle stays available.
- `whole = true` on links where picking an edge should mean the whole
  sketch.
- **One template per additive/subtractive pair.** `variants` names the
  two TypeIds; a first heading-less card holds `:variant`, one segmented
  choice of Add / Cut / Keep common. Across kinds it replaces the feature
  with the other type (`tools/variant.py`); inside a task the switch joins
  the edit's undo step, so Cancel takes it back.

## Adding a task panel for a feature

1. Read the feature's wiki page and FreeCAD's `Task<Feature>Parameters.ui`.
   List its properties, which are N/A, and which modes show which fields.
2. Write the template (above). Keep card titles and labels consistent with
   the existing templates.
3. **Field map** in `tools/task_sync.py`: property → (`.ui` object name,
   how it's set: `QUANTITY`, `CHECK`, `INDEX`, `MODE`, `COMBO`). While the
   task is open the dialog owns the feature (OK writes every field back),
   so edits must go through its widgets, never straight to the property.
4. Register the box class in `tools/task_layout.py`: `REPLACED` for the
   box the cards replace, `FOLDED` for secondary FreeCAD boxes kept but
   collapsed.
5. Tests: template parsing and shaping (`tests/test_inspector_templates.py`),
   field sync (`tests/test_task_sync.py`), one class per feature
   (`LoftTests`).
6. A local test document in `local/` from a generator script, covering
   every mode and the edge cases, including ones known to fail in FreeCAD
   itself (note which).
7. Translations: `python scripts/i18n.py update` for every locale, then
   translate the new strings (see [i18n](i18n.md)).

## Pitfalls seen in this area

- Setting a `QuantitySpinBox` by text only changes what it shows; set
  `rawValue`.
- `Type`'s deprecated `TwoLengths` must be omitted where `SideType` exists.
- The editor that opened a choice list can be rebuilt by the choice; close
  the list before emitting.
- A property read straight from the object while the task is open is the
  value before the dialog's edits.
