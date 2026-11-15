"""Expression editing for value fields: suggestions and a live result.

Fields name their owner as "Document#Name" or "Name"; parsing is pure
string work and only `Expressions` reads the document.
"""

from __future__ import annotations

import contextlib
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from ..core.qt import QtCore
from ..ui import quick_host

FUNCTIONS: tuple[str, ...] = (
    "abs", "acos", "asin", "atan", "atan2", "cath", "ceil", "cos", "cosh",
    "exp", "floor", "hypot", "log", "log10", "max", "min", "mod", "pow",
    "round", "sin", "sinh", "sqrt", "tan", "tanh", "trunc",
    "average", "count", "stddev", "sum",
    "create", "list", "matrix", "placement", "rotation", "vector",
)
CONSTANTS: tuple[str, ...] = ("pi", "e")
LIMIT = 12

#: Names, <<labels>>, dots and "#"; anything else ends a reference.
_REFERENCE = re.compile(r"(?:<<[^>]*>>|<<[^>]*$|[\w#.])*$")
_IDENTIFIER = re.compile(r"[A-Za-z_]\w*$")


@dataclass(frozen=True)
class Token:
    """The reference at the cursor: "Pad.Le" -> owner "Pad", prefix "Le"."""

    start: int
    owner: str
    prefix: str


@dataclass(frozen=True)
class Suggestion:
    """One completion entry."""

    label: str
    insert: str
    kind: str           # "object", "property", "function", "constant"
    detail: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"label": self.label, "insert": self.insert,
                "kind": self.kind, "detail": self.detail}


def token_at(text: str, cursor: int) -> Token:
    """The reference being typed just before `cursor`."""
    before = text[:max(0, min(cursor, len(text)))]
    match = _REFERENCE.search(before)
    start = match.start() if match else len(before)
    fragment = before[start:]
    if fragment.startswith("="):
        fragment, start = fragment[1:], start + 1
    owner, dot, prefix = fragment.rpartition(".")
    if not dot:
        return Token(start, "", fragment)
    return Token(start + len(owner) + 1, owner, prefix)


def reference(name: str, label: str) -> str:
    """How an expression names an object: its Name, or <<its Label>>."""
    if label and label != name:
        return "<<%s>>" % label
    return name


def unreference(text: str) -> str:
    """A reference as written, back to a name or a label."""
    text = text.split("#")[-1]
    if text.startswith("<<") and text.endswith(">>"):
        return text[2:-2]
    return text


def _matches(prefix: str, *names: str) -> int:
    """0 prefix match, 1 substring match, -1 none."""
    want = prefix.lower()
    best = -1
    for name in names:
        low = name.lower()
        if low.startswith(want):
            return 0
        if want and want in low:
            best = 1
    return best


def _ranked(found: Iterable[tuple[int, int, Suggestion]]
            ) -> list[Suggestion]:
    return [s for _rank, _order, s in sorted(found, key=lambda f: f[:2])]


def suggest(token: Token, objects: Sequence[tuple[str, str]],
            owner_properties: Sequence[str],
            properties_of: Any) -> list[Suggestion]:
    """Suggestions for the token, best first."""
    found: list[tuple[int, int, Suggestion]] = []
    if token.owner:
        props = properties_of(unreference(token.owner))
        for order, prop in enumerate(props or ()):
            rank = _matches(token.prefix, prop)
            if rank >= 0:
                found.append((rank, order, Suggestion(
                    prop, prop, "property", unreference(token.owner))))
        return _ranked(found)[:LIMIT]

    for order, prop in enumerate(owner_properties):
        rank = _matches(token.prefix, prop)
        if rank >= 0 and token.prefix:
            found.append((rank, order, Suggestion(prop, prop, "property")))
    base = len(found)
    for order, (name, label) in enumerate(objects):
        rank = _matches(token.prefix, name, label)
        if rank >= 0:
            shown = label if label and label != name else name
            found.append((rank, base + order, Suggestion(
                shown, reference(name, label) + ".", "object",
                name if shown != name else "")))
    base = len(found)
    for order, name in enumerate(FUNCTIONS):
        rank = _matches(token.prefix, name)
        if rank >= 0 and token.prefix:
            found.append((rank, base + order,
                          Suggestion(name, name + "(", "function")))
    for order, name in enumerate(CONSTANTS):
        if token.prefix and name.startswith(token.prefix):
            found.append((0, base + len(FUNCTIONS) + order,
                          Suggestion(name, name, "constant")))
    return _ranked(found)[:LIMIT]


def apply_suggestion(text: str, token: Token, cursor: int,
                     insert: str) -> tuple[str, int]:
    """The text with the token replaced by `insert`, and the new cursor."""
    end = cursor
    while end < len(text) and re.match(r"[\w]", text[end]):
        end += 1
    new = text[:token.start] + insert + text[end:]
    return new, token.start + len(insert)


def strip_marker(text: str) -> str:
    """An expression as typed, without the leading "=" that marks it."""
    text = text.strip()
    return text[1:].strip() if text.startswith("=") else text


def describe_value(value: Any) -> str:
    """A result, as the field would show it."""
    shown = getattr(value, "UserString", None)
    if isinstance(shown, str):
        return shown
    if isinstance(value, float):
        return "%g" % value
    return str(value)


# -- document side --

def _owner(path: str) -> Any:
    """Resolve "Document#Name" or "Name"."""
    import FreeCAD as App
    doc_name, _hash, name = path.rpartition("#")
    try:
        doc = App.getDocument(doc_name) if doc_name else App.ActiveDocument
    except Exception:
        return None
    return doc.getObject(name) if doc is not None and name else None


def _visible_properties(obj: Any) -> list[str]:
    out = []
    for prop in getattr(obj, "PropertiesList", ()):
        with contextlib.suppress(Exception):
            if "Hidden" in obj.getPropertyStatus(prop):
                continue
        out.append(prop)
    return out


class Expressions(QtCore.QObject):
    """QML helper for expression fields."""

    @QtCore.Slot(str, str, int, result="QVariantList")
    def suggest(self, owner: str, text: str,  # noqa: N802
                cursor: int) -> list[dict[str, str]]:
        obj = _owner(owner)
        if obj is None:
            return []
        doc = obj.Document
        objects = [(o.Name, o.Label) for o in doc.Objects if o is not obj]

        def properties_of(name: str) -> list[str] | None:
            found = doc.getObject(name)
            if found is None:
                labelled = doc.getObjectsByLabel(name)
                found = labelled[0] if labelled else None
            return _visible_properties(found) if found is not None else None

        token = token_at(text, cursor)
        return [s.as_dict() for s in suggest(
            token, objects, _visible_properties(obj), properties_of)]

    @QtCore.Slot(str, int, str, result="QVariantMap")
    def complete(self, text: str, cursor: int,  # noqa: N802
                 insert: str) -> dict[str, Any]:
        """Insert a suggestion: {text, cursor}."""
        new, at = apply_suggestion(text, token_at(text, cursor), cursor,
                                   insert)
        return {"text": new, "cursor": at}

    @QtCore.Slot(QtCore.QObject, result=QtCore.QPointF)
    def anchorOffset(self, item: Any) -> QtCore.QPointF:  # noqa: N802
        """Popup offset; the Wayland workaround lives in quick_host."""
        return quick_host.popup_offset(item)

    @QtCore.Slot(QtCore.QObject, result=QtCore.QRectF)
    def popupRoom(self, item: Any) -> QtCore.QRectF:  # noqa: N802
        """Where a popup may go; empty when no view holds `item`."""
        return quick_host.popup_room(item)

    @QtCore.Slot(str, str, result="QVariantMap")
    def evaluate(self, owner: str, text: str) -> dict[str, Any]:  # noqa: N802
        """{ok, text}: the value, or the first line of the error."""
        expression = strip_marker(text)
        obj = _owner(owner)
        if obj is None or not expression:
            return {"ok": False, "text": ""}
        try:
            value = obj.evalExpression(expression)
        except Exception as exc:
            message = str(exc).strip().splitlines()
            return {"ok": False, "text": message[0] if message else ""}
        return {"ok": True, "text": describe_value(value)}


_helper: Expressions | None = None


def helper() -> Expressions:
    """The shared Expressions instance."""
    global _helper
    if _helper is None:
        _helper = Expressions()
    return _helper


def register(context: Any) -> None:
    """Expose `expressions` to a QML context."""
    context.setContextProperty("expressions", helper())
