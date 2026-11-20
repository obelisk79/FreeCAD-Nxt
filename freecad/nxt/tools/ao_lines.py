"""The model's lines and points, drawn again over the ambient occlusion.

The occlusion is blended over the finished picture, so it darkens edges
and vertices too: in Flat Lines they lose contrast just where they are
picked. Right after the composite, a second render action draws only the
paths to the model's line and point sets, against the view's depth
buffer, which still holds the scene: hidden lines stay hidden, visible
ones land exactly on themselves. Switches still apply along the paths, so
display modes and hidden objects draw nothing, and selection highlighting
lives in the view providers' own selection roots, which the paths keep.

The paths start at a group of our own (the view's camera, then the
model's mirror), never at the view's scene graph: closing a document
frees that graph, and nothing here may hold on to it.
"""

from __future__ import annotations

from typing import Any

from ..core import opengl

#: Node types whose subclasses draw FreeCAD's edges and vertices
#: (SoBrepEdgeSet, SoBrepPointSet) and Sketcher's lines and markers.
LINE_TYPES = ("SoLineSet", "SoIndexedLineSet", "SoPointSet")
GL_ALL_ATTRIB_BITS = 0x000FFFFF
GL_DEPTH_TEST = 0x0B71
GL_LEQUAL = 0x0203
GL_TRUE = 1
GL_MODELVIEW = 0x1700
GL_PROJECTION = 0x1701


class LinesOnTop:
    """One view's model lines, and the node that draws them again."""

    def __init__(self) -> None:
        from pivy import coin
        self.root = coin.SoSeparator()
        self.root.ref()
        # in Coin's state too, or the second action would set its default
        self.depth = coin.SoDepthBuffer()
        self.depth.function = coin.SoDepthBuffer.LEQUAL
        self.paths = coin.SoPathList()
        self.key: tuple[int, int, int] = (0, 0, -1)
        self.node = coin.SoCallback()
        self.node.setCallback(self._render, None)

    def follow(self, camera: Any, model: Any, version: int,
               address: Any) -> None:
        """Find the model's lines again if the camera or model changed."""
        key = (address(camera), address(model), version)
        if key == self.key:
            return
        from pivy import coin
        self.key = key
        self.paths.truncate(0)
        self.root.removeAllChildren()
        self.root.addChild(self.depth)
        self.root.addChild(camera)
        self.root.addChild(model)
        for name in LINE_TYPES:
            search = coin.SoSearchAction()
            search.setType(coin.SoType.fromName(name), True)
            search.setInterest(coin.SoSearchAction.ALL)
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
        redraw = coin.SoGLRenderAction(action.getViewportRegion())
        redraw.setCacheContext(action.getCacheContext())
        redraw.setTransparencyType(action.getTransparencyType())
        gl = opengl.library()
        gl.glPushAttrib(GL_ALL_ATTRIB_BITS)
        for mode in (GL_PROJECTION, GL_MODELVIEW):
            gl.glMatrixMode(mode)
            gl.glPushMatrix()
        # the annotation phase drew with depth testing off, behind Coin's
        # back; LEQUAL lets each line pass where it is already drawn
        gl.glEnable(GL_DEPTH_TEST)
        gl.glDepthFunc(GL_LEQUAL)
        gl.glDepthMask(GL_TRUE)
        try:
            redraw.apply(self.paths, True)
        finally:
            for mode in (GL_PROJECTION, GL_MODELVIEW):
                gl.glMatrixMode(mode)
                gl.glPopMatrix()
            gl.glPopAttrib()
