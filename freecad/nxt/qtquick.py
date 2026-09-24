"""QtQuick, imported only when a QML surface is built.

Kept apart from `qt.py` so the lazy boundary is explicit: QtQuick pulls in
the scenegraph and is missing from some minimal Qt packagings, and nothing
at FreeCAD startup should depend on it. FreeCAD's `PySide` shim does not
carry these modules, so they come from PySide6 directly.
"""

from __future__ import annotations

import os
from types import ModuleType

#: Keeps the QtQuick scenegraph on the same graphics API as the Coin3D
#: viewport, instead of letting Qt 6's RHI pick Vulkan.
SCENEGRAPH_BACKEND = "opengl"


def use_shared_graphics_api() -> None:
    """Ask Qt for the viewport's graphics API, before any QML exists.

    Process-wide, so it is done by the first thing that needs QtQuick
    rather than at FreeCAD startup: a session where the panel never opens
    should be indistinguishable from one without the addon. `setdefault`
    leaves a deliberate choice in the environment alone.
    """
    os.environ.setdefault("QSG_RHI_BACKEND", SCENEGRAPH_BACKEND)


def modules() -> tuple[ModuleType, ModuleType, ModuleType]:
    """(QtQml, QtQuick, QtQuickWidgets), or ImportError at the point of use."""
    from PySide6 import QtQml, QtQuick, QtQuickWidgets
    return QtQml, QtQuick, QtQuickWidgets


def available() -> bool:
    try:
        modules()
    except ImportError:
        return False
    return True
