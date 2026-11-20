"""Relationship hints: the words beside rows the dependency arrows reach.

Each kind of link ("geometry", "attachment", "expression", "link") is
explained in words until the user has learned it: seen it, lingering on
the selection, enough times over enough separate FreeCAD sessions. Then
only its line sample stays. Counted per kind, in Nxt's own settings.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from typing import Any

from ..core import settings

SETTING = "RelationHints"
#: A kind is learned once seen this many times...
SIGHTINGS = 12
#: ...over at least this many FreeCAD sessions.
SESSIONS = 3
#: A selection counts as a sighting once it has shown this long.
DWELL_MS = 1500

#: This FreeCAD session: the time this module was first imported.
_SESSION = repr(time.time())


def _read() -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(str(settings.get(SETTING) or "{}"))
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def learned() -> list[str]:
    """The kinds whose words no longer show."""
    return sorted(kind for kind, seen in _read().items()
                  if isinstance(seen, dict)
                  and int(seen.get("count", 0)) >= SIGHTINGS
                  and int(seen.get("sessions", 0)) >= SESSIONS)


def seen(kinds: Iterable[str]) -> bool:
    """Count one sighting of each kind; True if one is now learned."""
    before = set(learned())
    data = _read()
    for kind in set(kinds) - before:
        entry = data.setdefault(kind, {})
        entry["count"] = int(entry.get("count", 0)) + 1
        if entry.get("session") != _SESSION:
            entry["session"] = _SESSION
            entry["sessions"] = int(entry.get("sessions", 0)) + 1
    settings.put(SETTING, json.dumps(data, sort_keys=True))
    return set(learned()) != before


def reset() -> None:
    """Show every kind's words again."""
    settings.put(SETTING, "")
