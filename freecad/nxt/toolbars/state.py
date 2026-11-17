"""Where FreeCAD's toolbars sit: area, row and order, from Qt's record.

Covered toolbars have no useful position on screen, but the main
window's saveState() still lists, for each toolbar area, its rows and
the toolbars on each in order. The toolbar section ends the stream:
a 0xFC marker byte, the row count, then per row its area and toolbars,
each as name, flags, position, size and two further sizes.
"""

from __future__ import annotations

import struct

TOP, LEFT, RIGHT = "top", "left", "right"
AREAS = (TOP, LEFT, RIGHT)
#: Qt's dock positions; the bottom area is folded into the top.
_AREA_OF = {0: LEFT, 1: RIGHT, 2: TOP, 3: TOP}
MARKER = 0xFC
_INT = struct.Struct(">i")
_NULL_STRING = 0xFFFFFFFF
#: After a toolbar's name and flags: position, size, two more sizes.
_ITEM_TAIL = 16

Rows = list[tuple[str, list[str]]]


class _Reader:
    def __init__(self, data: bytes, at: int) -> None:
        self.data, self.at = data, at

    def integer(self) -> int:
        value = _INT.unpack_from(self.data, self.at)[0]
        self.at += _INT.size
        return int(value)

    def text(self) -> str:
        length = self.integer() & 0xFFFFFFFF
        if length == _NULL_STRING:
            return ""
        value = self.data[self.at:self.at + length].decode("utf-16-be")
        self.at += length
        return value

    def skip(self, count: int) -> None:
        self.at += count


def _parse_from(data: bytes, at: int) -> Rows | None:
    reader = _Reader(data, at)
    try:
        rows: Rows = []
        for _row in range(reader.integer()):
            area = _AREA_OF.get(reader.integer())
            names = []
            for _toolbar in range(reader.integer()):
                names.append(reader.text())
                reader.skip(1 + _ITEM_TAIL)
            if area is None:
                return None
            rows.append((area, names))
    except (struct.error, UnicodeDecodeError):
        return None
    return rows if reader.at == len(data) else None


def rows(state: bytes) -> Rows | None:
    """Each toolbar row as (area, toolbar names in order); None if unread.

    Qt stores the areas left, right, top, bottom: the bottom's rows follow
    the top's.
    """
    for at in range(len(state) - 1, -1, -1):
        if state[at] == MARKER:
            found = _parse_from(state, at + 1)
            if found is not None:
                return found
    return None
