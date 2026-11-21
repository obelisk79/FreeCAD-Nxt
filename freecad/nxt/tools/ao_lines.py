"""The model's lines and points, as a mask the AO leaves undarkened.

The occlusion is blended over the solid model, so it would darken its
edges and vertices too: in Flat Lines they lose contrast, and picked or
preselected ones lose their highlight. The mask pass of the effect
(ao_pipeline.py) runs this node in a scene texture of its own: a second
render action draws only the paths to the model's line and point sets,
as eye depths, and the composite skips the pixels they cover.

The paths start at a group of our own (the view's camera, the mask's
draw style and shader, then the model's mirror), never at the view's
scene graph: closing a document frees that graph, and nothing here may
hold on to it. They are searched through every switch child, so a
display mode change needs no new search: switches still apply along the
paths when they are drawn.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import FreeCAD as App

from ..core import opengl

#: Node types whose subclasses draw FreeCAD's edges and vertices
#: (SoBrepEdgeSet, SoBrepPointSet) and Sketcher's lines and markers.
LINE_TYPES = ("SoLineSet", "SoIndexedLineSet", "SoPointSet")
#: FreeCAD's own line width and point size, in pixels, and the margin the
#: mask adds so a line's antialiased rim stays clear too.
VIEW_PARAMS = "User parameter:BaseApp/Preferences/View"
LINE_WIDTH = ("DefaultShapeLineWidth", 2)
POINT_SIZE = ("DefaultShapePointSize", 2)
MARGIN_PX = 1
GL_ALL_ATTRIB_BITS = 0x000FFFFF
GL_MODELVIEW = 0x1700
GL_PROJECTION = 0x1701


def widths() -> tuple[float, float]:
    """The mask's line width and point size, in pixels."""
    params = App.ParamGet(VIEW_PARAMS)
    line = params.GetInt(*LINE_WIDTH)
    point = params.GetInt(*POINT_SIZE)
    return float(max(line, 1) + MARGIN_PX), float(max(point, 1) + MARGIN_PX)


class LineMask:
    """One view's model lines, and the node that draws them as a mask.

    Lives with its view, across rebuilds of the effect.
    """

    def __init__(self) -> None:
        from pivy import coin
        self.root = coin.SoSeparator()
        self.root.ref()
        self.paths = coin.SoPathList()
        self.key: tuple[Any, ...] = ()
        self.version = -1
        self.size = (1, 1)
        self.node = coin.SoCallback()
        self.node.setCallback(self._render, None)

    def follow(self, key: tuple[Any, ...], size: tuple[int, int],
               nodes: Callable[[], list[Any]]) -> Any:
        """Draw the lines under new state nodes if `key` changed.

        `nodes()` makes the camera, the mask's state nodes and, last, the
        model's mirror; `size` is the mask texture's. Returns the node to
        place in the mask's scene.
        """
        self.size = size
        if key != self.key:
            self.key = key
            self.root.removeAllChildren()
            for node in nodes():
                self.root.addChild(node)
            self.search()
        return self.node

    def refresh(self, version: int) -> None:
        """Search the lines again if the model changed (`version`)."""
        if version != self.version:
            self.version = version
            self.search()

    def search(self) -> None:
        from pivy import coin
        self.paths.truncate(0)
        for name in LINE_TYPES:
            search = coin.SoSearchAction()
            search.setType(coin.SoType.fromName(name), True)
            search.setInterest(coin.SoSearchAction.ALL)
            search.setSearchingAll(True)
            search.apply(self.root)
            found = search.getPaths()
            for i in range(found.getLength()):
                self.paths.append(found[i])
        self.paths.sort()
        self.paths.uniquify()

    def release(self) -> None:
        self.paths.truncate(0)
        self.root.removeAllChildren()
        self.root.unref()

    def _render(self, data: Any, action: Any) -> None:
        from pivy import coin
        render = coin.SoGLRenderAction.getClassTypeId()
        if not self.paths.getLength() or not action.isOfType(render):
            return
        # pivy hands callbacks the base SoAction wrapper
        action = coin.cast(action, "SoGLRenderAction")
        redraw = coin.SoGLRenderAction(coin.SbViewportRegion(*self.size))
        redraw.setCacheContext(action.getCacheContext())
        gl = opengl.library()
        gl.glPushAttrib(GL_ALL_ATTRIB_BITS)
        for mode in (GL_PROJECTION, GL_MODELVIEW):
            gl.glMatrixMode(mode)
            gl.glPushMatrix()
        try:
            redraw.apply(self.paths, True)
        finally:
            for mode in (GL_PROJECTION, GL_MODELVIEW):
                gl.glMatrixMode(mode)
                gl.glPopMatrix()
            gl.glPopAttrib()
