"""Property Inspector templates: a layout for one family of objects.

Templates (resources/inspector/*.toml) never hide a property: unnamed ones
stay under "Everything else", and missing names are skipped.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, replace
from fnmatch import fnmatchcase
from importlib.resources import files
from pathlib import Path
from typing import Any

import FreeCAD as App

from ..core import units
from . import variables

#: Editors a template may request for a property.
EDITORS = frozenset({"", "dropdown", "segmented", "switch"})


@dataclass(frozen=True)
class Item:
    prop: str
    label: str = ""
    wide: bool | None = None
    editor: str = ""
    show_if: tuple[tuple[str, tuple[Any, ...]], ...] = ()
    #: (value, property): omit value when the object has property.
    omit_if: tuple[tuple[str, str], ...] = ()
    labels: tuple[str, ...] = ()
    #: An enumeration shown inside the field, before the value.
    lead: str = ""
    #: A yes/no shown as a glyph button after the editor.
    trail: str = ""
    glyph: str = ""
    #: Half the editor column.
    narrow: bool = False
    #: No label: the row's other items say enough.
    bare: bool = False
    #: Items laid on the same line, after this one's editor.
    beside: tuple["Item", ...] = ()

    def names(self) -> list[str]:
        return [self.prop, *(n for n in (self.lead, self.trail) if n),
                *(n for item in self.beside for n in item.names())]


@dataclass(frozen=True)
class Column:
    """Items stacked one above another, beside the card's other columns."""

    title: str
    items: tuple[Item, ...]
    show_if: tuple[tuple[str, tuple[Any, ...]], ...] = ()


@dataclass(frozen=True)
class Card:
    title: str
    items: tuple[Item, ...]
    hint: str = ""
    columns: tuple[Column, ...] = ()
    after: tuple[Item, ...] = ()
    #: Shown with no heading, and always open.
    heading: bool = True
    #: Closed, with a summary, while every one of these tests holds.
    closed_when: tuple[tuple[str, tuple[Any, ...]], ...] = ()
    #: Every property the object added (a VarSet's variables), whatever
    #: their names; editable, and more can be added, for one object.
    variables: bool = False

    def all_items(self) -> list[Item]:
        return [*self.items, *(i for c in self.columns for i in c.items),
                *self.after]


@dataclass(frozen=True)
class Couple:
    """A mode equal to another at zero; only `nonzero` is ever written.

    Keeps the offset's 3D handle visible even at zero.
    """

    value: str
    mode: str
    zero: str
    nonzero: str


@dataclass(frozen=True)
class Template:
    id: str
    types: tuple[str, ...]
    cards: tuple[Card, ...]
    choices: dict[str, str] = field(default_factory=dict)
    #: (hidden, superseding property), e.g. Midplane by SideType.
    hide_if: tuple[tuple[str, str], ...] = ()
    couples: tuple[Couple, ...] = ()
    #: (property, group): left out, but shown under another group.
    group_as: tuple[tuple[str, str], ...] = ()

    def matches(self, type_id: str) -> bool:
        return any(fnmatchcase(type_id, pattern) for pattern in self.types)

    def matches_object(self, obj: Any) -> bool:
        return any(self.matches(kind) for kind in kinds_of(obj))

    def item(self, prop: str) -> Item:
        """The first item naming `prop`, for its settings elsewhere."""
        for card in self.cards:
            for item in card.all_items():
                if item.prop == prop:
                    return replace(item, beside=(), lead="", trail="")
        return Item(prop)

    def names(self) -> set[str]:
        return {name for card in self.cards
                for item in card.all_items() for name in item.names()}


def kinds_of(obj: Any) -> list[str]:
    """Its TypeId, and for a Python feature "Nxt::<its proxy's class>"."""
    kinds = [str(getattr(obj, "TypeId", ""))]
    proxy = getattr(obj, "Proxy", None)
    if proxy is not None and not isinstance(proxy, str):
        kinds.append("Nxt::%s" % type(proxy).__name__)
    return kinds


def _tests(raw: Any) -> tuple[tuple[str, tuple[Any, ...]], ...]:
    return tuple(
        (name, tuple(value) if isinstance(value, list) else (value,))
        for name, value in dict(raw or {}).items())


def _item(raw: Any) -> Item:
    if isinstance(raw, str):
        return Item(raw)
    if isinstance(raw, list):
        first, *rest = [_item(r) for r in raw]
        return replace(first, beside=tuple(rest))
    show_if = _tests(raw.get("show_if"))
    omit_if = tuple((str(value), str(prop)) for value, prop
                    in dict(raw.get("omit_if", {})).items())
    editor = str(raw.get("editor", ""))
    if editor not in EDITORS:
        raise ValueError("%s: unknown editor %r" % (raw["prop"], editor))
    return Item(str(raw["prop"]), str(raw.get("label", "")),
                raw.get("wide"), editor, show_if, omit_if,
                tuple(str(label) for label in raw.get("labels", ())),
                str(raw.get("lead", "")), str(raw.get("trail", "")),
                str(raw.get("glyph", "")), bool(raw.get("narrow", False)),
                bool(raw.get("bare", False)))


def parse(data: dict[str, Any]) -> list[Template]:
    out = []
    for raw in data.get("template", ()):
        cards = tuple(
            Card(str(card["title"]),
                 tuple(_item(item) for item in card.get("items", ())),
                 str(card.get("hint", "")),
                 tuple(Column(str(col.get("title", "")),
                              tuple(_item(i) for i in col.get("items", ())),
                              _tests(col.get("show_if")))
                       for col in card.get("column", ())),
                 tuple(_item(item) for item in card.get("after", ())),
                 bool(card.get("heading", True)),
                 _tests(card.get("closed_when")),
                 bool(card.get("variables", False)))
            for card in raw.get("card", ()))
        hide_if = tuple((str(hidden), str(by)) for hidden, by
                        in dict(raw.get("hide_if", {})).items())
        couples = tuple(Couple(str(c["value"]), str(c["mode"]),
                               str(c["zero"]), str(c["nonzero"]))
                        for c in raw.get("couple", ()))
        group_as = tuple((str(prop), str(group)) for prop, group
                         in dict(raw.get("group_as", {})).items())
        out.append(Template(str(raw["id"]), tuple(raw.get("types", ())),
                            cards, dict(raw.get("choices", {})), hide_if,
                            couples, group_as))
    return out


def load(path: Path) -> list[Template]:
    try:
        return parse(tomllib.loads(path.read_text(encoding="utf-8")))
    except (OSError, tomllib.TOMLDecodeError, KeyError, TypeError,
            ValueError) as exc:
        App.Console.PrintWarning("Nxt inspector template %s: %s\n"
                                 % (path.name, exc))
        return []


_cache: list[Template] | None = None


def loaded() -> list[Template]:
    global _cache
    if _cache is None:
        folder = Path(str(files("freecad.nxt.resources") / "inspector"))
        _cache = [t for path in sorted(folder.glob("*.toml"))
                  for t in load(path)]
    return _cache


def invalidate() -> None:
    global _cache
    _cache = None


def for_objects(objects: list[Any],
                templates: list[Template] | None = None
                ) -> Template | None:
    """The template every one of `objects` matches, or None."""
    if not objects:
        return None
    for template in loaded() if templates is None else templates:
        if all(template.matches_object(o) for o in objects):
            return template
    return None


def _same(value: Any, wanted: Any) -> bool:
    if isinstance(wanted, bool):
        return bool(value) is wanted
    if isinstance(wanted, (int, float)):
        return _magnitude(value) == float(wanted)
    return str(value) == str(wanted)


def _magnitude(value: Any) -> float | None:
    """A number or quantity's number, in its shown unit."""
    if hasattr(value, "Value"):
        return float(value.Value)
    text = str(getattr(value, "UserString", value))
    try:
        return float(units.split_number_and_unit(text)[0].replace(",", "."))
    except ValueError:
        return None


def holds_all(tests: tuple[tuple[str, tuple[Any, ...]], ...],
              objects: list[Any]) -> bool:
    """Whether every test holds for every object; none never holds."""
    return bool(tests) and all(
        any(_same(getattr(o, name, None), w) for w in values)
        for name, values in tests for o in objects)


def shown(item: Item | Column, objects: list[Any]) -> bool:
    """Whether any of `item`'s tests holds; untestable items show."""
    tests = [(name, values) for name, values in item.show_if
             if all(hasattr(o, name) for o in objects)]
    if not tests:
        return True
    for name, values in tests:
        current = [getattr(o, name) for o in objects]
        if any(any(_same(v, w) for w in values) for v in current):
            return True
    return False


def apply(template: Template, objects: list[Any],
          groups: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Move the template's properties out of `groups` into its cards."""
    found: dict[str, dict[str, Any]] = {}
    for name, entries in groups.items():
        for entry in entries:
            found[entry["name"]] = entry
    own = (
        [n for n in variables.added(objects[0]) if n in found]
        if objects and any(card.variables for card in template.cards)
        else [])
    placed = template.names() | set(own) | {
        hidden for hidden, by in template.hide_if
        if all(hasattr(o, by) for o in objects)}
    moved = dict(template.group_as)
    for name in list(groups):
        kept = []
        for entry in groups[name]:
            if entry["name"] in placed:
                continue
            group = moved.get(entry["name"], name)
            if group == name:
                kept.append(entry)
            else:
                groups.setdefault(group, []).append(entry)
        groups[name] = kept
    for name in list(groups):
        if not groups[name]:
            del groups[name]

    def one(item: Item) -> dict[str, Any] | None:
        generic = found.get(item.prop)
        if generic is None or not shown(item, objects):
            return None
        entry = _shaped(template, item, generic, objects)
        if item.lead and item.lead in found:
            entry["lead"] = _shaped(template, template.item(item.lead),
                                    found[item.lead], objects)
        if item.trail and item.trail in found:
            entry["trail"] = dict(found[item.trail],
                                  glyph=item.glyph or "\u21c5")
        entry["beside"] = [e for e in map(one, item.beside) if e]
        entry["narrow"] = item.narrow
        if item.bare:
            entry["label"] = ""
        return entry

    def laid_out(items: tuple[Item, ...]) -> list[dict[str, Any]]:
        return [e for e in map(one, items) if e]

    cards = []
    for card in template.cards:
        if card.variables:
            cards.append(_variables_card(card, template, objects,
                                         [found[n] for n in own]))
            continue
        items = laid_out(card.items)
        columns: list[dict[str, Any]] = [
            {"title": column.title, "items": laid_out(column.items)}
            for column in card.columns if shown(column, objects)]
        columns = [c for c in columns if c["items"]]
        if len(columns) == 1:
            columns[0]["title"] = ""
        after = laid_out(card.after)
        count = (len(items) + len(after)
                 + sum(len(c["items"]) for c in columns))
        if count:
            closed = holds_all(card.closed_when, objects)
            every: list[dict[str, Any]] = [
                *items, *(i for c in columns for i in c["items"]), *after]
            cards.append({"name": card.title,
                          "open": not closed or not card.heading,
                          "heading": card.heading,
                          "items": items, "columns": columns, "after": after,
                          "count": count, "first": True, "hint": card.hint,
                          "summary": summary(every) if closed else "",
                          "template": template.id})
    return cards


def _variables_card(card: Card, template: Template, objects: list[Any],
                    entries: list[dict[str, Any]]) -> dict[str, Any]:
    """The variables, by their own names; shown even with none."""
    def type_of(prop: str) -> str:
        try:
            return str(objects[0].getTypeIdOfProperty(prop))
        except Exception:
            return ""
    rows = [dict(entry, label=entry["name"], variable=True,
                 typeLabel=variables.type_label(type_of(entry["name"])))
            for entry in entries]
    return {"name": card.title, "open": True, "heading": card.heading,
            "items": [], "columns": [], "after": [], "variables": rows,
            "editable": len(objects) == 1, "count": len(rows),
            "first": True, "hint": card.hint, "summary": "",
            "template": template.id}


def _said(entry: dict[str, Any]) -> str:
    """One entry in a few words, for a closed card's summary."""
    kind = entry["kind"]
    if kind == "enum":
        options, labels = entry["options"], entry.get("optionLabels") or []
        index = options.index(entry["text"]) if entry["text"] in options \
            else -1
        return labels[index] if 0 <= index < len(labels) else entry["text"]
    if kind == "quantity":
        return ("%s %s" % (entry["text"], entry["unit"])).strip()
    if kind == "link":
        return ", ".join(entry["links"])
    if kind == "bool":
        return entry["label"] if entry["checked"] else ""
    return str(entry["text"])


def summary(entries: list[dict[str, Any]]) -> str:
    """The values of a card's entries, and those beside them."""
    out = []
    for entry in entries:
        for one in (entry, *entry.get("beside", ())):
            said = _said(one)
            if said:
                out.append(said)
    return " · ".join(out)


def _shaped(template: Template, item: Item, generic: dict[str, Any],
            objects: list[Any]) -> dict[str, Any]:
    """The generic entry for a property, as the template asks for it."""
    entry = dict(generic)
    if item.label:
        entry["label"] = item.label
    if item.wide is not None:
        entry["wide"] = bool(item.wide)
    if item.editor:
        entry["editor"] = item.editor
    if entry["kind"] == "bool" and item.labels:
        entry["optionLabels"] = list(item.labels)
    for couple in template.couples:
        if item.prop == couple.mode and couple.zero in entry["options"]:
            entry["options"] = [o for o in entry["options"]
                                if o != couple.zero]
            if entry["text"] == couple.zero:
                entry["text"] = couple.nonzero
        elif item.prop == couple.value and all(
                str(getattr(o, couple.mode, "")) == couple.zero
                for o in objects):
            # FreeCAD locks the value at zero's mode; typing unlocks it.
            entry["readOnly"] = False
    if entry["kind"] == "enum":
        omitted = {value for value, prop in item.omit_if
                   if all(hasattr(o, prop) for o in objects)}
        options = [o for o in entry["options"]
                   if o not in omitted or o == entry["text"]]
        entry["options"] = options
        entry["optionLabels"] = (
            list(item.labels) if len(item.labels) == len(options)
            else [template.choices.get(o, o) for o in options])
    return entry


def coupled(template: Template | None, objects: list[Any], prop: str,
            value: Any) -> list[tuple[str, Any]] | None:
    """The edits setting `prop` to `value` makes, or None if uncoupled."""
    if template is None or not objects:
        return None
    for couple in template.couples:
        modes = {str(getattr(o, couple.mode, "")) for o in objects}
        if prop == couple.mode and value == couple.nonzero:
            return [] if modes == {couple.nonzero} else [(prop, value)]
        if prop == couple.value and couple.zero in modes:
            return [(couple.mode, couple.nonzero), (prop, value)]
    return None
