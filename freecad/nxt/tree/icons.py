"""Serve ViewObject icons to QML.

FreeCAD composes an object's icon in C++ (base icon plus overlays for tip
markers, links, errors and touched state), so redrawing it in QML would mean
reimplementing that composition. Instead we hand QML a URL and render the
real QIcon on demand:

    image://nxticon/<document>/<object>/<revision>[/gray]

The revision segment exists purely to defeat QML's image cache: when an
object changes in a way that alters its overlay, the model bumps the number
and the URL becomes a cache miss.

A trailing `gray` asks for the same icon desaturated. That is done here
rather than in QML on purpose: Qt's own desaturate effect lives in modules
this build may not ship, and a shader per chip would be paid for on every
frame. Here it is paid once, and QML's image cache keeps it.
"""

from __future__ import annotations

import traceback

import FreeCAD as App
import FreeCADGui as Gui

# Imported only when the panel builds its QML (see qtquick.py).
from PySide6.QtQuick import QQuickImageProvider

from ..qt import QtCore, QtGui, QtWidgets

_IMAGE_TYPE = QQuickImageProvider.ImageType.Pixmap

PROVIDER_ID = "nxticon"
VIRTUAL_PREFIX = "~"      # scene.VIRTUAL_PREFIX; no scene import here
DEFAULT_ICON_PX = 16


def url_for(doc_name: str, obj_name: str, revision: int = 0,
            gray: bool = False) -> str:
    url = "image://%s/%s/%s/%d" % (PROVIDER_ID, doc_name, obj_name, revision)
    return url + "/gray" if gray else url


class IconProvider(QQuickImageProvider):
    """Pixmap provider backed by live ViewObject icons."""

    def __init__(self) -> None:
        super().__init__(_IMAGE_TYPE)
        self._fallback: QtGui.QIcon | None = None

    # QQuickImageProvider
    def requestPixmap(self, image_id: str, size: QtCore.QSize | None,
                      requested_size: QtCore.QSize) -> QtGui.QPixmap:
        width = requested_size.width() or DEFAULT_ICON_PX
        height = requested_size.height() or DEFAULT_ICON_PX
        pixmap = self._render(image_id, width, height)
        if size is not None:
            size.setWidth(pixmap.width())
            size.setHeight(pixmap.height())
        return pixmap

    # internals
    def _render(self, image_id: str, width: int,
                height: int) -> QtGui.QPixmap:
        try:
            parts = (image_id or "").split("/")
            if len(parts) < 2:
                return self._blank(width, height)
            doc_name, obj_name = parts[0], parts[1]
            gray = parts[-1] == "gray"
            if obj_name.startswith(VIRTUAL_PREFIX):
                return self._folder().pixmap(width, height)
            doc = App.getDocument(doc_name)
            obj = doc.getObject(obj_name) if doc is not None else None
            vo = getattr(obj, "ViewObject", None)
            icon = getattr(vo, "Icon", None) if vo is not None else None
            if icon is None:
                return self._blank(width, height)
            if isinstance(icon, str):
                icon = (Gui.getIcon(icon) if hasattr(Gui, "getIcon")
                        else QtGui.QIcon(icon))
            pixmap = icon.pixmap(width, height)
            if pixmap.isNull():
                return self._blank(width, height)
            return self._desaturate(pixmap) if gray else pixmap
        except Exception:
            App.Console.PrintError(
                "Nxt: icon render failed for %r\n" % image_id)
            App.Console.PrintError(traceback.format_exc())
            return self._blank(width, height)

    @staticmethod
    def _folder() -> QtGui.QIcon:
        """A panel-only group draws as a Std_Group does."""
        icon = QtGui.QIcon(":/icons/folder.svg")
        if icon.isNull():
            icon = QtWidgets.QApplication.style().standardIcon(
                QtWidgets.QStyle.StandardPixmap.SP_DirIcon)
        return icon

    @staticmethod
    def _desaturate(pixmap: QtGui.QPixmap) -> QtGui.QPixmap:
        """The same icon, drained of colour, alpha intact.

        Via ARGB rather than Format_Grayscale8, which has no alpha channel
        and would fill every transparent pixel with black.
        """
        image = pixmap.toImage().convertToFormat(
            QtGui.QImage.Format.Format_ARGB32)
        for y in range(image.height()):
            for x in range(image.width()):
                colour = image.pixelColor(x, y)
                if colour.alpha() == 0:
                    continue
                grey = QtGui.qGray(colour.rgb())
                image.setPixelColor(x, y, QtGui.QColor(grey, grey, grey,
                                                       colour.alpha()))
        return QtGui.QPixmap.fromImage(image)

    def _blank(self, width: int, height: int) -> QtGui.QPixmap:
        pixmap = QtGui.QPixmap(max(width, 1), max(height, 1))
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)
        return pixmap
