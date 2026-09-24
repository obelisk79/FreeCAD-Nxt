"""The Qt binding, and the few places Qt's API needs smoothing over.

At runtime this is FreeCAD's `PySide` compatibility shim, which keeps the
addon working across whatever Qt the host was built with; outside FreeCAD
(the tests, an IDE) it is PySide6 directly. Type checkers always see
PySide6. The addon is Qt 6 only, as FreeCAD itself now is: there is no
PySide2 path.

QtQuick lives in `qtquick.py`, imported only when a QML surface is built.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PySide6 import QtCore, QtGui, QtWidgets
else:
    try:
        from PySide import QtCore, QtGui, QtWidgets
    except ImportError:     # outside FreeCAD: the tests, an IDE
        from PySide6 import QtCore, QtGui, QtWidgets

__all__ = ["QtCompat", "QtCore", "QtGui", "QtWidgets"]


class QtCompat:
    """Everything that differs between Qt builds or bindings, in one place."""

    @staticmethod
    def enum_int(value: Any) -> int:
        """A Qt enum as a plain int, for storing.

        PySide6 exposes Qt enums as enum.Enum rather than IntEnum, so
        int() refuses them; the stored form has to be a plain number.
        """
        return int(value.value if isinstance(value, Enum) else value)

    @staticmethod
    def version() -> str:
        return str(QtCore.qVersion())
