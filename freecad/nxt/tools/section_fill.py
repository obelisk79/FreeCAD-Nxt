"""A section's quick fill while its plane moves, on the GPU.

Slicing the solids takes too long to follow a drag, so meanwhile each
solid's mesh is drawn again into the stencil buffer only, inverting a
bit at every surface: an odd count marks where the plane passes through
material. A lit quad on the plane is drawn only there, in the solid's
cap colour and depth tested like any face. Once the plane rests, the
exact hatched cap (section_cap.py) takes over. Only GL render passes
touch GL.

The hatch is drawn over the fill as it is over the exact cap: a 32 px
tile in the plane, lines in the cap colour darkened, so moving the
plane shows the same picture it settles on.
"""

from __future__ import annotations

import ctypes
from collections.abc import Callable
from typing import Any

from ..core import opengl
from .section_cap import CAP_FACTOR, CAP_UNITS, face_index

GL_DEPTH_TEST = 0x0B71
GL_STENCIL_TEST = 0x0B90
GL_CULL_FACE = 0x0B44
GL_STENCIL_BUFFER_BIT = 0x0400
GL_ALWAYS = 0x0207
GL_NOTEQUAL = 0x0205
GL_KEEP = 0x1E00
GL_INVERT = 0x150A
GL_CLIP_PLANE0 = 0x3000
GL_LESS = 0x0201
GL_LEQUAL = 0x0203
GL_COLOR_MATERIAL = 0x0B57
GL_FRONT_AND_BACK = 0x0408
GL_AMBIENT = 0x1200
GL_DIFFUSE = 0x1201
GL_SPECULAR = 0x1202
GL_EMISSION = 0x1600
GL_SHININESS = 0x1601
#: Coin's shininess runs 0 to 1; GL's specular exponent 0 to 128.
GL_SHININESS_SCALE = 128.0
GL_LIGHTING = 0x0B50
GL_TEXTURE_2D = 0x0DE1
GL_POLYGON = 0x0009
GL_MAX_CLIP_PLANES = 0x0D32
GL_POLYGON_OFFSET_FILL = 0x8037
GL_ALL_ATTRIB_BITS = 0x000FFFFF
GL_ALPHA_TEST = 0x0BC0
GL_GREATER = 0x0204
GL_RGBA = 0x1908
GL_UNSIGNED_BYTE = 0x1401
GL_TEXTURE_WRAP_S = 0x2802
GL_TEXTURE_WRAP_T = 0x2803
GL_TEXTURE_MIN_FILTER = 0x2801
GL_TEXTURE_MAG_FILTER = 0x2800
GL_REPEAT = 0x2901
GL_NEAREST = 0x2600
GL_TEXTURE_ENV = 0x2300
GL_TEXTURE_ENV_MODE = 0x2200
GL_MODULATE = 0x2100

Vec3 = tuple[float, float, float]

_gl: Any = None
#: GL clip planes switched off for counting and filling, to restore.
_unclipped: list[int] = []
_plane_count: list[int] = []
#: GL texture names per (view's GL context, hatch), made on first use.
_textures: dict[tuple[int, str], int] = {}


def _texture(g: Any, context: int, name: str, mask: bytes) -> int:
    key = (context, name)
    if key not in _textures:
        tex = ctypes.c_uint(0)
        g.glGenTextures(1, ctypes.byref(tex))
        g.glBindTexture(GL_TEXTURE_2D, tex)
        for param, value in ((GL_TEXTURE_WRAP_S, GL_REPEAT),
                             (GL_TEXTURE_WRAP_T, GL_REPEAT),
                             (GL_TEXTURE_MIN_FILTER, GL_NEAREST),
                             (GL_TEXTURE_MAG_FILTER, GL_NEAREST)):
            g.glTexParameteri(GL_TEXTURE_2D, param, value)
        g.glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, 32, 32, 0, GL_RGBA,
                       GL_UNSIGNED_BYTE, mask)
        _textures[key] = tex.value
    return _textures[key]


def gl() -> Any:
    global _gl
    if _gl is None:
        _gl = opengl.library()
    return _gl


def _is_render(action: Any) -> bool:
    from pivy import coin
    return bool(action.isOfType(coin.SoGLRenderAction.getClassTypeId()))


def _unclip_all(g: Any) -> None:
    """Switch off every GL clip plane, whichever index Coin gave it."""
    if not _plane_count:
        most = ctypes.c_int(0)
        g.glGetIntegerv(GL_MAX_CLIP_PLANES, ctypes.byref(most))
        _plane_count.append(most.value or 6)
    for plane in range(GL_CLIP_PLANE0, GL_CLIP_PLANE0 + _plane_count[0]):
        if g.glIsEnabled(plane):
            _unclipped.append(plane)
            g.glDisable(plane)


def _restore_clips(g: Any) -> None:
    while _unclipped:
        g.glEnable(_unclipped.pop())


def _count_begin(_data: Any, action: Any) -> None:
    """Before the mesh is drawn again: invert a stencil bit per surface.

    Every other plane is off: the count is against this section alone;
    its own plane follows as a node and Coin turns it on.
    """
    if not _is_render(action):
        return
    g = gl()
    # All GL state is put back as it was once the fill is drawn: Coin
    # keeps its own idea of the material, texture and offset, and would
    # draw the caps and parts after it with ours.
    g.glPushAttrib(GL_ALL_ATTRIB_BITS)
    _unclip_all(g)
    g.glClearStencil(0)
    g.glClear(GL_STENCIL_BUFFER_BIT)
    g.glEnable(GL_STENCIL_TEST)
    g.glStencilFunc(GL_ALWAYS, 0, 0xFF)
    g.glStencilOp(GL_KEEP, GL_KEEP, GL_INVERT)
    g.glColorMask(0, 0, 0, 0)
    g.glDepthMask(0)
    g.glDisable(GL_DEPTH_TEST)
    g.glDisable(GL_CULL_FACE)


def _rgba(rgb: Vec3, scale: float = 1.0) -> Any:
    return (ctypes.c_float * 4)(*(c * scale for c in rgb), 1.0)


def _drawer(fill: QuickFill, look: Any, ink: float, hatch: str,
            mask: bytes, name: str) -> Callable[[Any, Any], None]:
    """A render callback filling one solid where its count is odd.

    Lit with the same material as the cap that replaces it.
    """
    diffuse, darker = _rgba(look.diffuse), _rgba(look.diffuse, ink)
    ambient, ambient_ink = _rgba(look.ambient), _rgba(look.ambient, ink)
    specular, emissive = _rgba(look.specular), _rgba(look.emissive)
    shininess = ctypes.c_float(look.shininess * GL_SHININESS_SCALE)
    f = ctypes.c_float

    def material(g: Any, colour: Any, glow: Any) -> None:
        g.glMaterialfv(GL_FRONT_AND_BACK, GL_DIFFUSE, colour)
        g.glMaterialfv(GL_FRONT_AND_BACK, GL_AMBIENT, glow)
        g.glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, specular)
        g.glMaterialfv(GL_FRONT_AND_BACK, GL_EMISSION, emissive)
        g.glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, shininess)

    def quad(g: Any, textured: bool) -> None:
        g.glBegin(GL_POLYGON)
        for corner in fill.corners_of.get(name, fill.corners):
            if textured:
                g.glTexCoord2f(*(f(t) for t in fill.hatch_at(corner)))
            g.glVertex3f(*(f(c) for c in corner))
        g.glEnd()

    def draw(_data: Any, action: Any) -> None:
        if not _is_render(action):
            return
        g = gl()
        g.glColorMask(1, 1, 1, 1)
        g.glDepthMask(1)
        g.glEnable(GL_DEPTH_TEST)
        g.glDepthFunc(GL_LEQUAL)
        g.glEnable(GL_STENCIL_TEST)
        g.glStencilFunc(GL_NOTEQUAL, 0, 0x01)
        g.glStencilOp(GL_KEEP, GL_KEEP, GL_KEEP)
        _unclip_all(g)
        g.glEnable(GL_POLYGON_OFFSET_FILL)
        g.glPolygonOffset(ctypes.c_float(CAP_FACTOR),
                          ctypes.c_float(CAP_UNITS))
        if fill.corners_of.get(name, fill.corners):
            lit = g.glIsEnabled(GL_LIGHTING)
            textured = g.glIsEnabled(GL_TEXTURE_2D)
            g.glDisable(GL_TEXTURE_2D)
            g.glDisable(GL_COLOR_MATERIAL)
            g.glEnable(GL_LIGHTING)
            material(g, diffuse, ambient)
            g.glNormal3f(*(f(c) for c in fill.normal))
            quad(g, False)
            if fill.hatched:
                g.glEnable(GL_TEXTURE_2D)
                g.glBindTexture(GL_TEXTURE_2D,
                                _texture(g, fill.context, hatch, mask))
                g.glTexEnvi(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE,
                            GL_MODULATE)
                g.glEnable(GL_ALPHA_TEST)
                g.glAlphaFunc(GL_GREATER, f(0.5))
                material(g, darker, ambient_ink)
                quad(g, True)
                g.glDisable(GL_ALPHA_TEST)
                g.glBindTexture(GL_TEXTURE_2D, 0)
                g.glDisable(GL_TEXTURE_2D)
            g.glEnable(GL_COLOR_MATERIAL)
            (g.glEnable if textured else g.glDisable)(GL_TEXTURE_2D)
            (g.glEnable if lit else g.glDisable)(GL_LIGHTING)
        g.glDisable(GL_POLYGON_OFFSET_FILL)
        g.glDepthFunc(GL_LESS)
        g.glDisable(GL_STENCIL_TEST)
        _restore_clips(g)
        g.glPopAttrib()

    draw.kept = (diffuse, darker, ambient, ambient_ink,  # type: ignore[attr-defined]
                 specular, emissive)
    return draw


def _callback(function: Any) -> Any:
    from pivy import coin
    node = coin.SoCallback()
    node.setCallback(function)
    return node


def _mesh(points: Any, triangles: Any) -> Any:
    from pivy import coin
    node = coin.SoSeparator()
    coords = coin.SoCoordinate3()
    coords.point.setValues(0, len(points), points.tolist())
    node.addChild(coords)
    faces = coin.SoIndexedFaceSet()
    index = face_index(triangles)
    faces.coordIndex.setValues(0, len(index), index)
    node.addChild(faces)
    return node


class QuickFill:
    """Each solid filled where the plane passes through it."""

    def __init__(self) -> None:
        from pivy import coin
        self.switch = coin.SoSwitch()
        self.root = coin.SoSeparator()
        # Never culled or cached: a box wholly on the clipped side would
        # skip the stencil set-up and leave the fill everywhere.
        self.root.renderCulling = coin.SoSeparator.OFF
        self.root.renderCaching = coin.SoSeparator.OFF
        unpickable = coin.SoPickStyle()
        unpickable.style = coin.SoPickStyle.UNPICKABLE
        self.root.addChild(unpickable)
        self.solids = coin.SoGroup()
        self.root.addChild(self.solids)
        self.switch.addChild(self.root)
        self.switch.whichChild = -1
        #: The plane's quad, trimmed by the view's other sections.
        self.corners: list[Vec3] = []
        #: Per solid, by name: its quad, less the sections that cut it.
        self.corners_of: dict[str, list[Vec3]] = {}
        self.normal: Vec3 = (0.0, 0.0, 1.0)
        #: The hatch: on or off, its tile's size and axes in the plane,
        #: and the GL context its textures belong to.
        self.hatched = True
        self.tile = 1.0
        self.u: Vec3 = (1.0, 0.0, 0.0)
        self.v: Vec3 = (0.0, 1.0, 0.0)
        self.context = 0
        # pivy keeps callbacks by a borrowed reference.
        self._kept: list[Any] = []
        self._switches: list[Any] = []
        self._crossing: list[bool] | None = None
        self._looks: list[tuple[Any, str, bytes, str]] = []
        self._mesh_of: Callable[[int], Any] = lambda _i: None
        self._clip: Any = None
        self._ink = 1.0

    def hatch_at(self, p: Vec3) -> tuple[float, float]:
        u, v, t = self.u, self.v, self.tile
        return ((p[0] * u[0] + p[1] * u[1] + p[2] * u[2]) / t,
                (p[0] * v[0] + p[1] * v[1] + p[2] * v[2]) / t)

    def build(self, looks: list[tuple[Any, str, bytes, str]],
              mesh_of: Callable[[int], Any], clip: Any, ink: float) -> None:
        """Get ready to count and fill each solid.

        Each look is (cap material, hatch name, hatch mask, the solid's name);
        `mesh_of(i)` gives solid i's (points, triangles) or None. A
        solid's nodes are made the first time the plane crosses it.
        """
        from pivy import coin
        self.solids.removeAllChildren()
        self._kept = []
        self._switches = []
        self._crossing = None
        self._looks = looks
        self._mesh_of = mesh_of
        self._clip = clip
        self._ink = ink
        for _look in looks:
            switch = coin.SoSwitch()
            switch.whichChild = -1
            self._switches.append(switch)
            self.solids.addChild(switch)

    def _make(self, index: int) -> None:
        from pivy import coin
        mesh = self._mesh_of(index)
        if mesh is None:
            return
        look, hatch, mask, name = self._looks[index]
        node = coin.SoSeparator()
        node.renderCulling = coin.SoSeparator.OFF
        count = coin.SoSeparator()
        count.renderCulling = coin.SoSeparator.OFF
        count.addChild(_callback(_count_begin))
        count.addChild(self._clip)
        count.addChild(_mesh(*mesh))
        node.addChild(count)
        draw = _drawer(self, look, self._ink, hatch, mask, name)
        self._kept.append(draw)
        node.addChild(_callback(draw))
        self._switches[index].addChild(node)

    def only(self, crossing: Any) -> None:
        """Count and fill only the solids the plane crosses.

        The rest can show no fill (their surfaces pair up in front of
        the plane), so they are switched off, not counted every frame.
        """
        was = self._crossing
        for i, (switch, on) in enumerate(zip(self._switches, crossing)):
            if was is not None and bool(was[i]) == bool(on):
                continue
            if on and switch.getNumChildren() == 0:
                self._make(i)
            switch.whichChild = -3 if on else -1
        self._crossing = [bool(c) for c in crossing]

    def show(self, on: bool) -> None:
        self.switch.whichChild = -3 if on else -1
