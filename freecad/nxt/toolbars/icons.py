"""Command icons as data URLs, so QML draws them with a plain Image.

PySide6's QQuickImageProvider gave blank images in FreeCAD (phase 0);
an embedded PNG works everywhere. Each icon is encoded once.
"""

from __future__ import annotations

from ..core.qt import QtCore, QtGui

#: Rendered at twice the drawn size, for high-density screens.
OVERSAMPLE = 2

_cache: dict[tuple[int, int], str] = {}


def url(icon: QtGui.QIcon, size: int) -> str:
    """A data URL of `icon` for drawing at `size` pixels; "" if none."""
    if icon.isNull():
        return ""
    key = (icon.cacheKey(), size)
    found = _cache.get(key)
    if found is None:
        data = QtCore.QByteArray()
        buffer = QtCore.QBuffer(data)
        buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
        side = size * OVERSAMPLE
        icon.pixmap(side, side).save(buffer, "PNG")
        found = "data:image/png;base64," + bytes(
            data.toBase64().data()).decode("ascii")
        _cache[key] = found
    return found


def forget() -> None:
    """Drop the cache, after an icon theme or size change."""
    _cache.clear()
