"""A section's clip on each solid it cuts, and its cap as real faces.

Each solid cut is clipped in its own view provider, so nothing else in
the scene is touched: sketches, datums, dimensions and other aids stay
whole. The cap is the exact cut (the solid sliced by the plane) drawn
as faces in the solid's own material, the hatch as their texture: lit
as the part is, highlighted with it, and hiding only what is behind it.
While the plane moves only the cut's outline is drawn, from the solid's
mesh; the faces follow once it rests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import FreeCAD as App

from ..core import log

#: Tessellation tolerance of the cap, as a share of the part's diagonal.
CAP_TOLERANCE = 2e-4
#: Tessellation tolerance of the mesh the moving outline is cut from.
#: FreeCAD's own mesh rule: deflection = the box's sides / 300 x Deviation.
DEVIATION_SPAN = 300.0
VIEW_DEVIATION = 0.5
#: A touch coarser than the view asks, so the view's own mesh is reused.
MESH_REUSE = 1.25
EDGES = ((0, 1), (1, 2), (2, 0))
#: The hatch tile's texture, square, in texels.
TILE = 32
#: The cap is drawn this far toward the viewer (polygon offset units),
#: clear of the plane's own fill lying on it.
CAP_FACTOR = -2.0
CAP_UNITS = -8.0
OUTLINE_COLOUR = (0.1, 0.1, 0.1)
OUTLINE_WIDTH = 2.0
VIEW_PARAMS = "User parameter:BaseApp/Preferences/View"
SELECTION_DEFAULT = 0x1CAD1CFF
HIGHLIGHT_DEFAULT = 0xE1E114FF


def _numpy() -> Any:
    """numpy, untyped: its stubs need a newer Python than some checks."""
    import importlib
    return importlib.import_module("numpy")


def view_root(obj: Any) -> Any:
    """The scene node that draws `obj`, or None."""
    view = getattr(obj, "ViewObject", None)
    try:
        return view.RootNode if view is not None else None
    except Exception:
        return None


def local_plane(normal: App.Vector, point: App.Vector,
                parent: Any) -> tuple[App.Vector, App.Vector]:
    """A world plane in the space a solid is drawn in, under `parent`."""
    inverse = parent.inverse()
    local_point = inverse.multVec(point)
    local_normal = inverse.Rotation.multVec(normal)
    return local_normal, local_point


def tile_image(mask: bytes, ink: float) -> bytes:
    """The hatch tile, grey: white paper, lines at `ink`.

    Multiplied into the cap's lit colour, so lines are the part's own
    colour darkened. `mask` is a 32x32 RGBA tile, its lines opaque.
    """
    paper = b"\xff\xff\xff\xff"
    level = round(ink * 255)
    lines = bytes((level, level, level, 255))
    out = bytearray()
    for i in range(TILE * TILE):
        out += lines if mask[i * 4 + 3] else paper
    return bytes(out)


def _packed(name: str, default: int) -> tuple[float, float, float]:
    packed = App.ParamGet(VIEW_PARAMS).GetUnsigned(name, default)
    return (((packed >> 24) & 0xFF) / 255.0, ((packed >> 16) & 0xFF) / 255.0,
            ((packed >> 8) & 0xFF) / 255.0)


def selection_colours() -> tuple[tuple[float, float, float],
                                 tuple[float, float, float]]:
    """FreeCAD's selection and preselection colours."""
    return (_packed("SelectionColor", SELECTION_DEFAULT),
            _packed("HighlightColor", HIGHLIGHT_DEFAULT))


@dataclass
class Look:
    """How a solid's faces are lit: its material, the cap's diffuse."""

    diffuse: tuple[float, float, float]
    ambient: tuple[float, float, float] = (0.2, 0.2, 0.2)
    specular: tuple[float, float, float] = (0.0, 0.0, 0.0)
    emissive: tuple[float, float, float] = (0.0, 0.0, 0.0)
    shininess: float = 0.2


def look_of(obj: Any, diffuse: tuple[float, float, float]) -> Look:
    """The object's own material, with the cap's colour."""
    look = Look(diffuse)
    try:
        material = obj.ViewObject.ShapeAppearance[0]
    except Exception:
        return look
    for name in ("AmbientColor", "SpecularColor", "EmissiveColor"):
        try:
            value = getattr(material, name)
            setattr(look, name[:-5].lower(),
                    (float(value[0]), float(value[1]), float(value[2])))
        except Exception:
            pass
    try:
        look.shininess = float(material.Shininess)
    except Exception:
        pass
    return look


@dataclass
class Clipped:
    """One solid's clip node, where it sits, and what places it."""

    root: Any
    clip: Any
    parent: Any


@dataclass
class CapPiece:
    """One solid's cut faces as a mesh, and its texture coordinates."""

    name: str
    node: Any
    material: Any
    coords: Any
    diffuse: tuple[float, float, float]
    points: Any = None


class Clips:
    """The section's clip, put into each solid's own view provider."""

    def __init__(self) -> None:
        self.items: list[Clipped] = []

    def attach(self, solids: list[Any]) -> None:
        from pivy import coin
        self.detach()
        for solid in solids:
            root = view_root(solid.obj)
            if root is None:
                continue
            clip = coin.SoClipPlane()
            root.insertChild(clip, 0)
            self.items.append(Clipped(root, clip, solid.parent))

    def place(self, normal: App.Vector, point: App.Vector) -> None:
        from pivy import coin
        for item in self.items:
            n, p = local_plane(normal, point, item.parent)
            item.clip.plane = coin.SbPlane(coin.SbVec3f(n.x, n.y, n.z),
                                           coin.SbVec3f(p.x, p.y, p.z))

    def detach(self) -> None:
        for item in self.items:
            try:
                if item.root.findChild(item.clip) >= 0:
                    item.root.removeChild(item.clip)
            except Exception:  # noqa: BLE001 - its object is gone
                pass
        self.items = []


def view_deflection(solid: Any) -> float:
    """The deflection the view meshed `solid` with, give or take."""
    view = getattr(solid.obj, "ViewObject", None)
    deviation = getattr(view, "Deviation", VIEW_DEVIATION)
    box = solid.shape.BoundBox
    sides = box.XLength + box.YLength + box.ZLength
    return max(sides / DEVIATION_SPAN * deviation * MESH_REUSE, 1e-6)


def _mesh_of(solid: Any, numpy: Any) -> tuple[Any, Any] | None:
    points, triangles = solid.shape.tessellate(view_deflection(solid))
    if not triangles:
        return None
    return (numpy.array([(p.x, p.y, p.z) for p in points], dtype=float),
            numpy.array(triangles, dtype=int))


def _key(solid: Any) -> Any:
    try:
        return (solid.name, solid.shape.hashCode(), view_deflection(solid))
    except Exception:  # noqa: BLE001 - not cached
        return None


def _segments(points: Any, triangles: Any, n: Any, distance: float) -> Any:
    """Where the plane at `distance` along `n` crosses the triangles."""
    numpy = _numpy()
    heights = (points @ n - distance)[triangles]
    above = heights > 0
    crossed = above.any(axis=1) & ~above.all(axis=1)
    heights, above = heights[crossed], above[crossed]
    corners = points[triangles[crossed]]
    ends = []
    for a, b in EDGES:
        cross = above[:, a] != above[:, b]
        t = heights[:, a] / numpy.where(cross, heights[:, a] - heights[:, b],
                                        1)
        where = corners[:, a] + (corners[:, b] - corners[:, a]) * t[:, None]
        ends.append(numpy.where(cross[:, None], where, numpy.nan))
    stacked = numpy.stack(ends, axis=1)                 # (k, 3, 3)
    # Each triangle's two crossings, in edge order.
    order = numpy.argsort(numpy.isnan(stacked[:, :, 0]), axis=1,
                          kind="stable")[:, :2]
    pairs = numpy.take_along_axis(stacked, order[:, :, None], axis=1)
    return pairs.reshape(-1, 3)


class Meshes:
    """Each solid's triangles, meshed the first time the plane crosses it.

    The view's own triangulation is reused, so the outline lies on the
    surfaces as drawn; unchanged solids keep their meshes across reads.
    """

    def __init__(self) -> None:
        self.solids: list[Any] = []
        self._keys: list[Any] = []
        self._cache: dict[Any, tuple[Any, Any] | None] = {}
        #: Meshes of solids with no cache key, by index; dropped on read.
        self._loose: dict[int, tuple[Any, Any] | None] = {}
        #: Per solid, for one normal: its triangles sorted by their lowest
        #: height along it, those heights, and the tallest triangle.
        self._bands: dict[int, tuple[Any, Any, Any, float]] = {}
        self._centres: Any = None
        self._halves: Any = None

    def read(self, solids: list[Any]) -> None:
        numpy = _numpy()
        self.solids = list(solids)
        self._keys = [_key(s) for s in self.solids]
        old, self._loose, self._bands = self._cache, {}, {}
        self._cache = {k: old[k] for k in self._keys if k in old}
        boxes = [s.shape.BoundBox for s in self.solids]
        low = numpy.array([(b.XMin, b.YMin, b.ZMin) for b in boxes],
                          dtype=float).reshape(-1, 3)
        high = numpy.array([(b.XMax, b.YMax, b.ZMax) for b in boxes],
                           dtype=float).reshape(-1, 3)
        self._centres, self._halves = (low + high) / 2, (high - low) / 2

    def mesh(self, index: int) -> tuple[Any, Any] | None:
        """Solid `index`'s (points, triangles), or None if it has none."""
        key = self._keys[index]
        store: dict[Any, tuple[Any, Any] | None] = (
            self._cache if key is not None else self._loose)
        slot = key if key is not None else index
        if slot not in store:
            try:
                store[slot] = _mesh_of(self.solids[index], _numpy())
            except Exception:  # noqa: BLE001 - no outline or fill for it
                store[slot] = None
        return store[slot]

    def _band(self, index: int, mesh: tuple[Any, Any], n: Any
              ) -> tuple[Any, Any, float]:
        """Solid `index`'s triangles in height order along `n`."""
        numpy = _numpy()
        band = self._bands.get(index)
        if band is None or not numpy.array_equal(band[0], n):
            points, triangles = mesh
            heights = (points @ n)[triangles]
            low = heights.min(axis=1)
            order = numpy.argsort(low, kind="stable")
            reach = float((heights.max(axis=1) - low).max(initial=0.0))
            band = (n.copy(), low[order], triangles[order], reach)
            self._bands[index] = band
        return band[1], band[2], band[3]

    def crossing(self, normal: App.Vector, distance: float,
                 margin: float = 0.0) -> Any:
        """Per solid: whether the plane passes through its box."""
        numpy = _numpy()
        if self._centres is None:
            return numpy.zeros(0, dtype=bool)
        n = numpy.array((normal.x, normal.y, normal.z))
        return abs(self._centres @ n - distance) \
            <= self._halves @ abs(n) + margin

    def outline(self, normal: App.Vector, distance: float
                ) -> list[tuple[float, float, float]]:
        """Where the plane crosses the triangles: segment end pairs."""
        numpy = _numpy()
        n = numpy.array((normal.x, normal.y, normal.z))
        parts = []
        for i in numpy.flatnonzero(self.crossing(normal, distance)):
            mesh = self.mesh(int(i))
            if mesh is None:
                continue
            low, triangles, reach = self._band(int(i), mesh, n)
            first = numpy.searchsorted(low, distance - reach, "left")
            last = numpy.searchsorted(low, distance, "right")
            parts.append(_segments(mesh[0], triangles[first:last], n,
                                   distance))
        if not parts:
            return []
        return list(map(tuple, numpy.concatenate(parts).tolist()))


class Cap:
    """The cut faces of every solid, hatched, under one node."""

    def __init__(self) -> None:
        from pivy import coin
        self.root = coin.SoSeparator()
        self.root.setName("NxtSectionCap")
        unpickable = coin.SoPickStyle()
        unpickable.style = coin.SoPickStyle.UNPICKABLE
        self.root.addChild(unpickable)
        #: The other sections' clips, in world space.
        self.trims = coin.SoGroup()
        self.root.addChild(self.trims)
        self.faces = coin.SoSeparator()
        hints = coin.SoShapeHints()
        # Lit from either side: the cap is seen from both.
        hints.vertexOrdering = coin.SoShapeHints.COUNTERCLOCKWISE
        hints.shapeType = coin.SoShapeHints.UNKNOWN_SHAPE_TYPE
        self.faces.addChild(hints)
        nearest = coin.SoComplexity()
        nearest.textureQuality = 0.01     # crisp hatch lines
        self.faces.addChild(nearest)
        offset = coin.SoPolygonOffset()
        offset.factor = CAP_FACTOR
        offset.units = CAP_UNITS
        self.faces.addChild(offset)
        self.pieces_node = coin.SoGroup()
        self.faces.addChild(self.pieces_node)
        self.root.addChild(self.faces)
        self.lines = coin.SoSeparator()
        light = coin.SoLightModel()
        light.model = coin.SoLightModel.BASE_COLOR
        self.lines.addChild(light)
        colour = coin.SoBaseColor()
        colour.rgb = OUTLINE_COLOUR
        self.lines.addChild(colour)
        style = coin.SoDrawStyle()
        style.lineWidth = OUTLINE_WIDTH
        self.lines.addChild(style)
        self.line_points = coin.SoCoordinate3()
        self.lines.addChild(self.line_points)
        self.line_set = coin.SoLineSet()
        self.lines.addChild(self.line_set)
        self.pieces: list[CapPiece] = []
        #: Solid names selected, and the one preselected.
        self.selected: set[str] = set()
        self.preselected = ""

    def trim_by(self, clips: list[Any]) -> None:
        self.trims.removeAllChildren()
        for clip in clips:
            self.trims.addChild(clip)

    def moving(self, segments: list[tuple[float, float, float]]) -> None:
        """While the plane moves: the outline only."""
        if self.root.findChild(self.faces) >= 0:
            self.root.removeChild(self.faces)
        if self.root.findChild(self.lines) < 0:
            self.root.addChild(self.lines)
        self.line_points.point.setNum(len(segments))
        if segments:
            self.line_points.point.setValues(0, len(segments), segments)
        self.line_set.numVertices.setValues(
            0, len(segments) // 2, [2] * (len(segments) // 2))
        self.line_set.numVertices.setNum(len(segments) // 2)

    def build(self, solids: list[Any], faces: list[list[Any]],
              image_of: Any, look_for: Any, tile: float, u: App.Vector,
              v: App.Vector, normal: App.Vector,
              trims_of: Any = None, meshes: list[Any] | None = None
              ) -> None:
        """One textured mesh per solid's cut faces, in the outline's place.

        `trims_of(solid)`: the other sections' clips that cut that solid,
        and so its cap; a solid another section leaves whole keeps all.
        """
        self.pieces_node.removeAllChildren()
        self.pieces = []
        for k, (solid, cut) in enumerate(zip(solids, faces)):
            if not cut:
                continue
            try:
                piece = _piece(solid, cut, image_of(solid), look_for(solid),
                               normal, meshes[k] if meshes else None)
                for clip in (trims_of(solid) if trims_of else ()):
                    piece.node.insertChild(clip, 0)
            except Exception as exc:  # noqa: BLE001 - that cap is left out
                log.error("section: could not cap %s: %s"
                          % (solid.name, exc))
                continue
            self.pieces.append(piece)
            self.pieces_node.addChild(piece.node)
        self.map(tile, u, v)
        self.paint()
        if self.root.findChild(self.lines) >= 0:
            self.root.removeChild(self.lines)
        if self.root.findChild(self.faces) < 0:
            self.root.addChild(self.faces)

    def map(self, tile: float, u: App.Vector, v: App.Vector) -> None:
        """Lay the hatch tile on the plane at this size."""
        axes = _numpy().array(((u.x, v.x), (u.y, v.y), (u.z, v.z))) / tile
        for piece in self.pieces:
            uv = (piece.points @ axes).tolist()
            piece.coords.point.setValues(0, len(uv), uv)

    def paint(self) -> None:
        """Each cap in its solid's colour, or highlighted with it."""
        chosen, hovered = selection_colours()
        for piece in self.pieces:
            colour = (hovered if piece.name == self.preselected
                      else chosen if piece.name in self.selected
                      else piece.diffuse)
            piece.material.diffuseColor = colour


def cap_mesh(cut: list[Any]) -> Any:
    """The cut faces' (points, triangles)."""
    import Part
    compound = Part.makeCompound(cut)
    size = max(compound.BoundBox.DiagonalLength, 1e-6)
    return compound.tessellate(size * CAP_TOLERANCE)


def _piece(solid: Any, cut: list[Any], image: bytes, look: Look,
           normal: App.Vector, mesh: Any = None) -> CapPiece:
    from pivy import coin
    points, triangles = mesh if mesh is not None else cap_mesh(cut)
    node = coin.SoSeparator()
    material = coin.SoMaterial()
    material.diffuseColor = look.diffuse
    material.ambientColor = look.ambient
    material.specularColor = look.specular
    material.emissiveColor = look.emissive
    material.shininess = look.shininess
    node.addChild(material)
    texture = coin.SoTexture2()
    texture.image.setValue(coin.SbVec2s(TILE, TILE), 4, image)
    texture.model = coin.SoTexture2.MODULATE
    texture.wrapS = coin.SoTexture2.REPEAT
    texture.wrapT = coin.SoTexture2.REPEAT
    node.addChild(texture)
    coords = coin.SoTextureCoordinate2()
    node.addChild(coords)
    face_normal = coin.SoNormal()
    face_normal.vector = (normal.x, normal.y, normal.z)
    node.addChild(face_normal)
    binding = coin.SoNormalBinding()
    binding.value = coin.SoNormalBinding.OVERALL
    node.addChild(binding)
    numpy = _numpy()
    corners = numpy.array([(p.x, p.y, p.z) for p in points], dtype=float)
    vertices = coin.SoCoordinate3()
    vertices.point.setValues(0, len(corners), corners.tolist())
    node.addChild(vertices)
    mesh = coin.SoIndexedFaceSet()
    index = face_index(facing_winding(corners, triangles, normal))
    mesh.coordIndex.setValues(0, len(index), index)
    mesh.textureCoordIndex.setValues(0, len(index), index)
    node.addChild(mesh)
    return CapPiece(solid.name, node, material, coords, look.diffuse,
                    corners)


def facing_winding(points: Any, triangles: Any, normal: App.Vector) -> Any:
    """Triangles wound counter-clockwise about `normal`.

    With two-sided lighting GL picks the lit side by winding, not by the
    normal given; the kernel's winding follows each face's orientation.
    """
    numpy = _numpy()
    rows = numpy.asarray(triangles, dtype=int).reshape(-1, 3).copy()
    if not len(rows):
        return rows
    a, b, c = (points[rows[:, k]] for k in range(3))
    n = numpy.array((normal.x, normal.y, normal.z))
    backwards = numpy.cross(b - a, c - a) @ n < 0
    rows[backwards] = rows[backwards][:, ::-1]
    return rows


def face_index(triangles: Any) -> list[int]:
    """Coin's face index: each triangle's corners, then -1."""
    numpy = _numpy()
    rows = numpy.asarray(triangles, dtype=int).reshape(-1, 3)
    ends = numpy.full((len(rows), 1), -1, dtype=int)
    return numpy.hstack((rows, ends)).ravel().tolist()


class Highlight:
    """Follows FreeCAD's selection, so the caps light up with their part."""

    def __init__(self, cap: Cap, names: Any, owner: Any) -> None:
        self._cap = cap
        #: The solids' names, to match against what is selected.
        self._names = names
        #: The solid a face of the exact cut belongs to, or "": the cut
        #: lies over the cap, so a click on the cap picks it.
        self._owner = owner

    def _which(self, obj: str, sub: str) -> str:
        owned = self._owner(obj, sub)
        if owned:
            return str(owned)
        names = self._names()
        for name in [obj] + (sub or "").split("."):
            if name in names:
                return name
        return ""

    def setPreselection(self, _doc: str, obj: str, sub: str) -> None:  # noqa: N802
        self._cap.preselected = self._which(obj, sub)
        self._cap.paint()

    def removePreselection(self, _doc: str, _obj: str, _sub: str) -> None:  # noqa: N802
        self._cap.preselected = ""
        self._cap.paint()

    def addSelection(self, _doc: str, obj: str, sub: str,  # noqa: N802
                     _pnt: Any = None) -> None:
        name = self._which(obj, sub)
        if name:
            self._cap.selected.add(name)
            self._cap.paint()

    def removeSelection(self, _doc: str, obj: str, sub: str) -> None:  # noqa: N802
        self.sync()

    def clearSelection(self, _doc: str) -> None:  # noqa: N802
        self._cap.selected.clear()
        self._cap.paint()

    def sync(self) -> None:
        """Read the whole selection again."""
        import FreeCADGui as Gui
        chosen: set[str] = set()
        for entry in Gui.Selection.getSelectionEx("", 0):
            for sub in list(entry.SubElementNames) or [""]:
                name = self._which(entry.ObjectName, sub)
                if name:
                    chosen.add(name)
        self._cap.selected = chosen
        self._cap.paint()
