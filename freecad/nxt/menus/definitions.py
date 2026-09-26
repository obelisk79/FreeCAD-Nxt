"""Context menu definitions: read, checked, merged, and resolved.

A definition file is TOML. It names FreeCAD commands, Nxt's own actions and
view-provider edit modes, and says where each goes and when it applies; it
holds no code. See `resources/menus/default.toml` for the full shape and
`tree/CONTEXT_MENU.md` for why the menu is laid out as it is.

This module knows nothing of FreeCAD. What the menu is resolved against is
a list of `ObjectFacts`, one per selected object, which `facts.py` reads
from the document; the tests build them by hand.

A bad entry is reported and skipped, never fatal: one addon's typo must not
take the menu away from everything else.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, replace
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

#: The sections, in the order they are drawn. Sections an addon names that
#: are not listed here follow Inspect, in the order they are first seen.
SECTIONS = ("Model", "Organize", "Relations", "Inspect")

#: Every flag a condition may test. `facts.py` sets them; an unknown flag in
#: a file is an error rather than a condition that silently never holds.
FLAGS = frozenset({
    "failed", "past_tip", "is_tip", "solver_issues", "has_expression",
    "has_dependents", "has_inputs", "out_of_date", "editable_placement",
    "suppressible", "has_shape", "shown_in_3d", "editing", "attachable",
})

#: The view provider edit modes an `edit:` item may name (FreeCAD's
#: ViewProvider::EditMode).
EDIT_MODES = {"default": 0, "transform": 1, "cutting": 2, "color": 3}

_CONDITION_KEYS = {"type", "count", "in_body", "proxy_module", "flags"}
_ITEM_KEYS = {"command", "label", "before", "after", "submenu"}

#: The command of an item that only holds a submenu.
SUBMENU = "@submenu"
_MENU_KEYS = {"id", "when", "lead", "state", "section", "more", "delete",
              "hide", "drop"}


@dataclass(frozen=True)
class ObjectFacts:
    """What the menu may ask of one selected object."""

    #: The object's TypeId followed by the TypeIds it derives from.
    types: tuple[str, ...]
    proxy_module: str = ""
    in_body: bool = False
    flags: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Condition:
    """When a menu or item applies; every stated test must hold.

    `type`, `proxy_module`, `in_body` and `flags` must hold for every
    selected object; `count` is tested against the selection's size.
    """

    types: tuple[str, ...] = ()
    count: str = "any"
    in_body: bool | None = None
    proxy_modules: tuple[str, ...] = ()
    flags: frozenset[str] = frozenset()
    #: Flags that must *not* hold, written `"!name"` in a file.
    absent: frozenset[str] = frozenset()

    def holds(self, selection: list[ObjectFacts]) -> bool:
        if not selection or not _count_holds(self.count, len(selection)):
            return False
        return all(self._holds_for(obj) for obj in selection)

    def _holds_for(self, obj: ObjectFacts) -> bool:
        if self.types and not any(fnmatchcase(t, pattern)
                                  for t in obj.types
                                  for pattern in self.types):
            return False
        if self.proxy_modules and not any(
                fnmatchcase(obj.proxy_module, pattern)
                for pattern in self.proxy_modules):
            return False
        if self.in_body is not None and obj.in_body != self.in_body:
            return False
        return self.flags <= obj.flags and not self.absent & obj.flags


ALWAYS = Condition()


@dataclass(frozen=True)
class Item:
    """One entry: what runs, and optionally its label and placement.

    `command` is a FreeCAD command name (`Std_Delete`), an Nxt action
    (`nxt:isolate`) or a view provider edit mode (`edit:default`). A label
    left empty is taken at display time from the FreeCAD command, or for an
    Nxt action from `labels.ACTIONS`.

    An item with `items` is a submenu of them, labelled `label`; its
    command is `SUBMENU`, and it is left out if none of its items apply.
    """

    command: str
    label: str = ""
    when: Condition = ALWAYS
    before: str = ""
    after: str = ""
    items: tuple[Item, ...] = ()


@dataclass
class Menu:
    """One `[[menu]]` table: what it adds when its condition holds."""

    id: str
    source: str
    when: Condition = ALWAYS
    lead: Item | None = None
    state: list[Item] = field(default_factory=list)
    sections: dict[str, list[Item]] = field(default_factory=dict)
    more: dict[str, list[Item]] = field(default_factory=dict)
    delete: Item | None = None
    hide: frozenset[str] = frozenset()
    #: FreeCAD commands this menu leaves out on purpose, or replaces with
    #: an Nxt action; they are not carried over into More.
    drop: frozenset[str] = frozenset()


@dataclass
class Definitions:
    """Everything read from one or more files, in the order read."""

    bar: list[Item] = field(default_factory=list)
    menus: list[Menu] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def extend(self, other: Definitions) -> None:
        """Add a later file's menus; only the first file sets the bar."""
        if not self.bar:
            self.bar = other.bar
        self.menus.extend(other.menus)
        self.errors.extend(other.errors)


@dataclass
class Resolved:
    """The menu for one selection, ready to draw.

    `trace` records why each command is where it is, or why it was left
    out, for `explain()`.
    """

    bar: list[Item] = field(default_factory=list)
    dimmed: set[str] = field(default_factory=set)
    lead: Item | None = None
    state: list[Item] = field(default_factory=list)
    sections: list[tuple[str, list[Item]]] = field(default_factory=list)
    delete: Item | None = None
    more: list[tuple[str, list[Item]]] = field(default_factory=list)
    #: FreeCAD commands the applying menus deliberately leave out.
    dropped: set[str] = field(default_factory=set)
    trace: list[str] = field(default_factory=list)

    def commands(self) -> list[str]:
        """Every command placed, in drawing order, submenus opened out."""
        def flat(items: list[Item] | tuple[Item, ...]) -> list[str]:
            out: list[str] = []
            for item in items:
                out += flat(item.items) if item.items else [item.command]
            return out

        out = flat(self.bar)
        out += flat([self.lead]) if self.lead else []
        out += flat(self.state)
        out += [c for _n, items in self.sections for c in flat(items)]
        out += flat([self.delete]) if self.delete else []
        out += [c for _n, items in self.more for c in flat(items)]
        return out


# -------------------------------------------------------------------------- #
# reading
# -------------------------------------------------------------------------- #

def load(path: Path) -> Definitions:
    """Read one definition file. Errors are collected, not raised."""
    out = Definitions()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        out.errors.append("%s: %s" % (path.name, exc))
        return out
    return parse(data, path.name)


def parse(data: dict[str, Any], source: str) -> Definitions:
    """Check and convert one file's parsed TOML."""
    out = Definitions()
    report = _Reporter(source, out.errors)
    if data.get("version", 1) != 1:
        report("version %r is not supported" % data.get("version"))
        return out
    bar = data.get("bar", {})
    if bar:
        out.bar = _items(bar.get("items", []), report.at("bar"))
    for index, raw in enumerate(data.get("menu", [])):
        where = report.at("menu %s" % raw.get("id", index + 1)
                          if isinstance(raw, dict) else index + 1)
        menu = _menu(raw, source, index, where)
        if menu is not None:
            out.menus.append(menu)
    return out


class _Reporter:
    """Collects errors, each prefixed with where it was found."""

    def __init__(self, prefix: str, sink: list[str]) -> None:
        self.prefix, self.sink = prefix, sink

    def __call__(self, message: str) -> None:
        self.sink.append("%s: %s" % (self.prefix, message))

    def at(self, where: str | int) -> _Reporter:
        return _Reporter("%s, %s" % (self.prefix, where), self.sink)


def _menu(raw: Any, source: str, index: int,
          report: _Reporter) -> Menu | None:
    if not isinstance(raw, dict):
        report("a menu must be a table")
        return None
    for key in sorted(set(raw) - _MENU_KEYS):
        report("unknown key %r" % key)
    when = _condition(raw.get("when", {}), report.at("when"))
    if when is None:
        return None     # a menu whose condition cannot be read never shows
    menu = Menu(id=str(raw.get("id", "%s#%d" % (source, index + 1))),
                source=source, when=when)
    if "lead" in raw:
        menu.lead = _item(raw["lead"], report.at("lead"))
    if "delete" in raw:
        menu.delete = _item(raw["delete"], report.at("delete"))
    menu.state = _items(raw.get("state", []), report.at("state"))
    for key in ("section", "more"):
        groups = raw.get(key, {})
        if not isinstance(groups, dict):
            report("%s must be a table of lists" % key)
            continue
        target = menu.sections if key == "section" else menu.more
        for name, items in groups.items():
            target[name] = _items(items, report.at("%s.%s" % (key, name)))
    for key in ("hide", "drop"):
        names = raw.get(key, [])
        if isinstance(names, list) and all(isinstance(n, str) for n in names):
            setattr(menu, key, frozenset(names))
        else:
            report("%s must be a list of command names" % key)
    return menu


def _items(raw: Any, report: _Reporter) -> list[Item]:
    if not isinstance(raw, list):
        report("expected a list")
        return []
    items = [_item(entry, report) for entry in raw]
    return [i for i in items if i is not None]


def _item(raw: Any, report: _Reporter) -> Item | None:
    if isinstance(raw, str):
        raw = {"command": raw}
    if isinstance(raw, dict) and "submenu" in raw:
        return _submenu(raw, report)
    if not isinstance(raw, dict) or not isinstance(raw.get("command"), str):
        report("an item is a command name or a table with `command`")
        return None
    command = raw["command"]
    for key in sorted(set(raw) - _ITEM_KEYS - _CONDITION_KEYS):
        report("%s: unknown key %r" % (command, key))
    if command.startswith("edit:") and command[5:] not in EDIT_MODES:
        report("%s: edit mode must be one of %s"
               % (command, ", ".join(EDIT_MODES)))
        return None
    # An item's condition keys sit in the item itself, which keeps it on
    # one line: TOML inline tables cannot break across lines.
    when = _condition({k: v for k, v in raw.items() if k in _CONDITION_KEYS},
                      report.at(command))
    if when is None:
        return None
    return Item(command=command, label=str(raw.get("label", "")),
                when=when, before=str(raw.get("before", "")),
                after=str(raw.get("after", "")))


def _submenu(raw: dict[str, Any], report: _Reporter) -> Item | None:
    """`{ label = "...", submenu = [items] }`: a submenu within a section."""
    label = raw.get("label")
    if not isinstance(label, str) or not label:
        report("a submenu needs a `label`")
        return None
    for key in sorted(set(raw) - _ITEM_KEYS - _CONDITION_KEYS - {"command"}):
        report("%s: unknown key %r" % (label, key))
    items = _items(raw["submenu"], report.at(label))
    when = _condition({k: v for k, v in raw.items() if k in _CONDITION_KEYS},
                      report.at(label))
    if when is None or not items:
        return None
    return Item(command=SUBMENU, label=label, when=when,
                before=str(raw.get("before", "")),
                after=str(raw.get("after", "")), items=tuple(items))


def _condition(raw: Any, report: _Reporter) -> Condition | None:
    if not isinstance(raw, dict):
        report("a condition must be a table")
        return None
    ok = True
    for key in sorted(set(raw) - _CONDITION_KEYS):
        report("unknown condition %r" % key)
        ok = False
    types = _strings(raw.get("type", []))
    proxies = _strings(raw.get("proxy_module", []))
    flags = _strings(raw.get("flags", []))
    if types is None or proxies is None or flags is None:
        report("type, proxy_module and flags take a string or a list")
        return None
    wanted = {f for f in flags if not f.startswith("!")}
    absent = {f[1:] for f in flags if f.startswith("!")}
    for flag in sorted((wanted | absent) - FLAGS):
        report("unknown flag %r" % flag)
        ok = False
    count = raw.get("count", "any")
    count = str(count)
    if not _count_valid(count):
        report("count must be a number, \"N+\" or \"any\"")
        ok = False
    in_body = raw.get("in_body")
    if in_body is not None and not isinstance(in_body, bool):
        report("in_body must be true or false")
        ok = False
    if not ok:
        return None
    return Condition(types=tuple(types), count=count, in_body=in_body,
                     proxy_modules=tuple(proxies), flags=frozenset(wanted),
                     absent=frozenset(absent))


def _strings(value: Any) -> list[str] | None:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return list(value)
    return None


def _count_valid(count: str) -> bool:
    return count == "any" or count.rstrip("+").isdigit()


def _count_holds(count: str, size: int) -> bool:
    if count == "any":
        return True
    if count.endswith("+"):
        return size >= int(count[:-1])
    return size == int(count)


# -------------------------------------------------------------------------- #
# resolving
# -------------------------------------------------------------------------- #

def resolve(definitions: Definitions,
            selection: list[ObjectFacts]) -> Resolved:
    """The menu for `selection`, from every menu whose condition holds.

    Menus apply in the order read (Nxt's own file first, then addons, each
    in file order). A later menu's lead or delete replaces an earlier one;
    sections and More groups accumulate. A command is placed once, at the
    first place it reaches, bar first; `hide` in any applying menu removes
    it everywhere.
    """
    out = Resolved()
    if not selection:
        return out
    applying = [m for m in definitions.menus if m.when.holds(selection)]
    out.trace += ["menu %s (%s) applies" % (m.id, m.source)
                  for m in applying]
    hidden = frozenset().union(*(m.hide for m in applying))
    out.dropped = set().union(*(m.drop for m in applying))
    out.trace += ["%s: dropped on purpose" % name
                  for name in sorted(out.dropped)]
    placed: set[str] = set()

    def keep(item: Item | None, where: str) -> Item | None:
        if item is None:
            return None
        if item.items:
            return keep_submenu(item, where)
        if item.command in hidden:
            out.trace.append("%s: hidden" % item.command)
            return None
        if item.command in placed:
            out.trace.append("%s: already placed; not repeated in %s"
                             % (item.command, where))
            return None
        if item.command.startswith("edit:") and len(selection) > 1:
            out.trace.append("%s: edit modes act on one object"
                             % item.command)
            return None
        if not item.when.holds(selection):
            out.trace.append("%s: its condition does not hold" % item.command)
            return None
        placed.add(item.command)
        out.trace.append("%s: %s" % (item.command, where))
        return item

    def keep_submenu(item: Item, where: str) -> Item | None:
        """A submenu keeps whichever of its items apply, or goes."""
        if not item.when.holds(selection):
            out.trace.append("%s ›: its condition does not hold" % item.label)
            return None
        inside = "%s › %s" % (where, item.label)
        children = [c for c in (keep(i, inside) for i in item.items) if c]
        if not children:
            out.trace.append("%s ›: none of its items apply" % item.label)
            return None
        return replace(item, items=tuple(children))

    # The bar never changes shape: an action that does not apply is dimmed
    # where it stands, and `hide` does not reach it.
    for item in definitions.bar:
        placed.add(item.command)
        out.bar.append(item)
        if not item.when.holds(selection):
            out.dimmed.add(item.command)
            out.trace.append("%s: bar, dimmed" % item.command)
        else:
            out.trace.append("%s: bar" % item.command)

    lead = next((m.lead for m in reversed(applying) if m.lead), None)
    out.lead = keep(lead, "lead")
    for menu in applying:
        out.state += [i for i in (keep(s, "state") for s in menu.state) if i]

    delete = next((m.delete for m in reversed(applying) if m.delete), None)
    out.delete = keep(delete, "delete")

    out.sections = _groups(applying, "sections", keep, SECTIONS)
    out.more = _groups(applying, "more", keep, ())
    return out


def _groups(menus: list[Menu], attr: str, keep: Any,
            order: tuple[str, ...]) -> list[tuple[str, list[Item]]]:
    """Merge named groups across menus, honouring before/after."""
    merged: dict[str, list[Item]] = {name: [] for name in order}
    for menu in menus:
        for name, items in getattr(menu, attr).items():
            target = merged.setdefault(name, [])
            for item in items:
                kept = keep(item, "%s %s" % (attr.rstrip("s"), name))
                if kept is not None:
                    _insert(target, kept)
    return [(name, items) for name, items in merged.items() if items]


def _insert(items: list[Item], item: Item) -> None:
    names = [i.command for i in items]
    if item.before in names:
        items.insert(names.index(item.before), item)
    elif item.after in names:
        items.insert(names.index(item.after) + 1, item)
    else:
        items.append(item)
