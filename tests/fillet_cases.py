"""Nxt fillet test cases: builds a document of bodies and checks them.

Run with FreeCAD's command line:
    freecadcmd tests/fillet_cases.py                  # build, check, save
    freecadcmd tests/fillet_cases.py --pass record    # and record volumes
    freecadcmd tests/fillet_cases.py --pass timing    # and time each step
    freecadcmd tests/chamfer_cases.py                 # the same, chamfered

Each body is a base solid with Nxt fillets (or chamfers) on it, built
the way the feature is used. The check recomputes every feature and
wants one valid solid, no skipped edges unless the case expects them,
and the volume recorded for it last time. The document is saved to
tests/models/fillet_cases.FCStd for looking at in FreeCAD.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import FreeCAD as App  # noqa: E402
import Part  # noqa: E402

import freecad  # noqa: E402

freecad.__path__.append(str(ROOT / "freecad"))  # type: ignore[attr-defined]

from freecad.nxt.tools import blend_fillet as bf  # noqa: E402

V = App.Vector
#: Chamfers instead of rounds, for parity: the same cases, sizes as
#: chamfer distances (chamfer_cases.py sets this).
FLAT = "chamfer" in sys.argv
KIND = "chamfer" if FLAT else "fillet"
MODEL = ROOT / "tests" / "models" / ("%s_cases.FCStd" % KIND)
RECORD = ROOT / "tests" / "models" / ("%s_cases.json" % KIND)
#: Volumes may drift this much, relative, from the recorded ones.
DRIFT = 1e-4


def edge_at(shape, point, kind=None):
    """The name of the edge of `shape` passing nearest to `point`."""
    vertex = Part.Vertex(point)
    best = min((i for i, e in enumerate(shape.Edges)
                if kind is None or isinstance(e.Curve, kind)),
               key=lambda i: shape.Edges[i].distToShape(vertex)[0])
    return "Edge%d" % (best + 1)


def face_at(shape, point):
    vertex = Part.Vertex(point)
    best = min(range(len(shape.Faces)),
               key=lambda i: shape.Faces[i].distToShape(vertex)[0])
    return "Face%d" % (best + 1)


class Case:
    """One body: its solid, then rounds added one after another."""

    def __init__(self, doc, name, solid, note):
        self.name = name
        self.note = note
        self.body = doc.addObject("PartDesign::Body", name)
        base = doc.addObject("Part::Feature", name + "_solid")
        base.Shape = solid
        self.body.BaseFeature = base
        doc.recompute()
        self.tip = self.body.Group[0] if self.body.Group else None
        self.features = []
        self.expect_problems = False

    def add(self, picks, size, flat=FLAT, faces=(), tangent=True,
            corners=None):
        """Round the edges nearest `picks` (and of faces at `faces`)."""
        shape = self.tip.Shape
        names = [edge_at(shape, p) for p in picks]
        # Kept as faces, as picked: the feature finds their edges.
        names += [face_at(shape, point) for point in faces]
        obj = bf.new_fillet(self.tip, names, size, flat)
        obj.TangentEdges = tangent
        obj.Refine = True
        if corners is not None and hasattr(obj, "Corners"):
            obj.Corners = corners
        self.tip.Document.recompute()
        self.features.append(obj)
        self.tip = obj
        return obj


def kidney(r1, r2, gap, height, bulge):
    """Two circles joined by arcs of radius `bulge` bowing outward."""
    def centre(sign):
        a, b = bulge - r1, bulge - r2
        x = (a * a - b * b + gap * gap) / (2 * gap)
        return V(x, sign * math.sqrt(a * a - x * x), 0)

    sides = []
    for sign in (1, -1):
        c = centre(sign)
        p = (V() - c).normalize() * r1
        q = V(gap, 0, 0) + (V(gap, 0, 0) - c).normalize() * r2
        sides.append((p, c + ((p + q) * 0.5 - c).normalize() * bulge, q))
    (p1, m1, q1), (p2, m2, q2) = sides
    wire = Part.Wire(Part.__sortEdges__([
        Part.Arc(p1, m1, q1).toShape(), Part.Arc(p2, m2, q2).toShape(),
        Part.Arc(p1, V(-r1, 0, 0), p2).toShape(),
        Part.Arc(q1, V(gap + r2, 0, 0), q2).toShape()]))
    return Part.Face(wire).extrude(V(0, 0, height)), m2


def slot_off_tangent(length=30.0, width=10.0, height=6.0, off=0.02):
    """A slot whose right end bulges `off` past round.

    Its arc meets the straight sides a fraction of a degree off tangent,
    as a sketch's unconstrained arc does.
    """
    half = width / 2
    wire = Part.Wire([
        Part.LineSegment(V(0, 0, 0), V(length, 0, 0)).toShape(),
        Part.Arc(V(length, 0, 0), V(length + half + off, half, 0),
                 V(length, width, 0)).toShape(),
        Part.LineSegment(V(length, width, 0), V(0, width, 0)).toShape(),
        Part.Arc(V(0, width, 0), V(-half, half, 0), V(0, 0, 0)).toShape()])
    return Part.Face(wire).extrude(V(0, 0, height))


def frustum(bottom=17.5, top=8.121785, height=35.0):
    """A square pyramid cut flat: the pyramid.FCStd of a report."""
    def corners(half, z):
        return [V(-half, -half, z), V(half, -half, z), V(half, half, z),
                V(-half, half, z)]

    low, high = corners(bottom, 0), corners(top, height)
    loops = [low[::-1], high] + [
        [low[i], low[(i + 1) % 4], high[(i + 1) % 4], high[i]]
        for i in range(4)]
    faces = [Part.Face(Part.makePolygon(loop + loop[:1])) for loop in loops]
    solid = Part.Solid(Part.Shell(faces))
    return solid if solid.Volume > 0 else solid.reversed()


def plate(length, width, height, at=V()):
    return Part.makeBox(length, width, height, at)


def lever(r1, r2, gap, height):
    """Two circles joined by their outer tangents, extruded."""
    a = math.asin((r2 - r1) / gap)

    def tangent(sign):
        n = V(-math.sin(a), sign * math.cos(a), 0)
        return n * r1, V(gap, 0, 0) + n * r2

    p1, q1 = tangent(1)
    p2, q2 = tangent(-1)
    wire = Part.Wire(Part.__sortEdges__([
        Part.LineSegment(p1, q1).toShape(),
        Part.LineSegment(p2, q2).toShape(),
        Part.Arc(p1, V(-r1, 0, 0), p2).toShape(),
        Part.Arc(q1, V(gap + r2, 0, 0), q2).toShape()]))
    return Part.Face(wire).extrude(V(0, 0, height))


def frame(windows=4):
    """A cone frustum between two flanges, cut into slanted bars.

    Like the stand in the bad-fillets file: the bars' outer faces are
    the cone, their sides flat, and they end on both flanges.
    """
    low = Part.makeCylinder(30, 10)
    high = Part.makeCylinder(22, 10, V(0, 0, 45))
    cone = Part.makeCone(29.88, 20.42, 35, V(0, 0, 10))
    hollow = Part.makeCone(24.88, 15.42, 35, V(0, 0, 10))
    shell = cone.cut(hollow)
    for k in range(windows):
        window = Part.makeBox(40, 16, 35, V(0, -8, 10))
        window.rotate(V(), V(0, 0, 1), 360.0 * k / windows + 45)
        shell = shell.cut(window)
    return low.fuse([high, shell]).removeSplitter()


def build(doc):
    cases = []

    def case(name, solid, note):
        App.Console.PrintLog("building %s\n" % name)
        if "verbose" in sys.argv:
            print("building", name, flush=True)
        c = Case(doc, name, solid, note)
        cases.append(c)
        return c

    c = case("Box_edge", plate(40, 30, 20),
             "One outer edge, r 3.")
    c.add([V(20, 0, 20)], 3.0)

    c = case("Box_corner", plate(40, 30, 20),
             "Three edges meeting at a corner, equal r 4: sphere corner.")
    c.add([V(40, 15, 20), V(20, 30, 20), V(40, 30, 10)], 4.0)

    # A tapered pyramid's top corner: rounded at once, or one edge at a
    # time in any order, the corner is the same sphere (as in Onshape).
    # Picked towards the top edges' far ends: an 8 mm chamfer of the
    # slanted edge first takes their middles.
    top = (V(8.12178, -6, 35), V(-6, 8.12178, 35))
    slant = V(12.81, 12.81, 17.5)
    c = case("Pyramid_corner", frustum(),
             "Three edges at a tapered pyramid's corner, r 8, at once.")
    c.add([top[0], top[1], slant], 8.0)
    # Tangent edges taken along: the second pick runs on round the first
    # round to the third edge, so two picks finish the corner.
    for name, order in (("a", (slant, top[0])),
                        ("b", (top[0], top[1])),
                        ("c", (top[0], slant))):
        c = case("Pyramid_order_" + name, frustum(),
                 "The same corner, one edge at a time: the same result.")
        if FLAT:
            # Chamfers take no tangent edges along: the third is picked.
            order += tuple(p for p in (slant,) + top if p not in order)
        for pick in order:
            c.add([pick], 8.0)
    c = case("Pyramid_order_d", frustum(),
             "The same corner one edge at a time, no tangent edges taken "
             "along: still the same result.")
    for pick in (top[1], top[0], slant):
        c.add([pick], 8.0, tangent=False)

    if FLAT:
        c = case("Box_corner_point", plate(40, 30, 20),
                 "Three chamfered edges at a corner, run to a point.")
        c.add([V(40, 15, 20), V(20, 30, 20), V(40, 30, 10)], 4.0,
              corners="Point")

        inner = plate(60, 40, 20).cut(plate(30, 20, 12, V(15, 10, 8)))
        c = case("Pocket_corner", inner,
                 "Three chamfered edges at a pocket's inner corner: a "
                 "triangle fills it.")
        c.add([V(30, 30, 8), V(45, 20, 8), V(45, 30, 14)], 2.0)

    c = case("Box_all", plate(40, 30, 20),
             "All twelve edges, r 3: eight sphere corners.")
    c.add([], 3.0, faces=[V(20, 15, 20), V(20, 15, 0)], tangent=False)
    c.features[-1].UseAllEdges = True
    doc.recompute()

    c = case("Box_chamfer", plate(40, 30, 20),
             "Chamfer on the top face's edges, 2 mm.")
    c.add([], 2.0, flat=True, faces=[V(20, 15, 20)])

    pocket = plate(60, 40, 20).cut(plate(30, 20, 12, V(15, 10, 8)))
    c = case("Pocket", pocket,
             "Pocket: hollow edges round its floor r 3, then its rim r 2.")
    c.add([V(30, 10, 8), V(30, 30, 8), V(15, 20, 8), V(45, 20, 8)], 3.0)
    c.add([V(30, 10, 20), V(30, 30, 20), V(15, 20, 20), V(45, 20, 20)],
          2.0)

    boss = plate(80, 60, 10).fuse(Part.makeCylinder(15, 15, V(40, 30, 10)))
    c = case("Boss", boss.removeSplitter(),
             "Boss on a plate: hollow round at its foot r 3, then its top "
             "r 2.")
    c.add([V(40, 45, 10)], 3.0)
    c.add([V(40, 45, 25)], 2.0)

    tangent_boss = plate(100, 48.2, 10, V(-50, -24.1, 0)).fuse(
        Part.makeCylinder(24.1, 10, V(23, 0, 10))).removeSplitter()
    c = case("Tangent_boss", tangent_boss,
             "Boss tangent to the plate's side: the whole top face, r 1 "
             "(two swept corridor blends).")
    c.add([], 1.0, faces=[V(-30, 0, 10)])

    c = case("Tangent_order_a", tangent_boss,
             "Same boss: top edge first, then the boss's foot, r 3.")
    c.add([V(-20, -24.1, 10)], 3.0)
    c.add([V(-1.1, 0, 10)], 3.0)

    c = case("Tangent_order_b", tangent_boss,
             "Same boss: the boss's foot first, then the top edge, r 3. "
             "The other order: features apply in turn, so it differs.")
    c.add([V(-1.1, 0, 10)], 3.0)
    c.add([V(-20, -24.1, 10)], 3.0)

    lev = lever(10, 20, 70, 10).fuse(
        Part.makeCylinder(20, 20, V(70, 0, 0))).removeSplitter()
    c = case("Lever_pocket", lev,
             "Plate tangent to a boss: hollow round at the boss's foot and "
             "the plate's top edge meet in a pocket, r 3.")
    c.add([V(55, 0, 10)], 3.0)
    c.add([V(30, -15.5, 10)], 3.0)

    c = case("Lever_top_first", lev,
             "The same plate and boss: its top edge first, then the hollow "
             "round at the boss's foot runs out on it, r 3.")
    c.add([V(30, -15.5, 10)], 3.0)
    c.add([V(55, 0, 10)], 3.0)

    bowed, side = kidney(8, 16, 70, 6, 150)
    bowed = bowed.fuse(Part.makeCylinder(16, 16, V(70, 0, 0))).removeSplitter()
    c = case("Kidney_pocket", bowed,
             "A plate with bowed sides tangent to a boss: hollow round at "
             "the boss's foot r 2, then the plate's top edge r 2.4.")
    c.add([V(54, 0, 6)], 2.0)
    c.add([V(side.x, side.y, 6)], 2.4)

    lev2 = lever(10, 16, 60, 8).fuse(Part.makeCylinder(10, 20, V(0, 0, 0)))
    lev2 = lev2.fuse(Part.makeCylinder(16, 16, V(60, 0, 0))).removeSplitter()
    c = case("Lever_flush", lev2,
             "Plate side flush with the bosses: its top edge only, r 1 "
             "(no tangent run-on into the bosses).")
    c.add([V(30, 13, 8)], 1.0)

    cone = Part.makeCone(30, 18, 30).fuse(plate(80, 80, 6, V(-40, -40, -6)))
    c = case("Cone_foot", cone.removeSplitter(),
             "Cone on a plate: hollow round at its foot r 4, then its top "
             "rim r 2.")
    c.add([V(0, 30, 0)], 4.0)
    c.add([V(0, 18, 30)], 2.0)

    k = 10 - 10 / math.sqrt(2)
    rounded = Part.Face(Part.Wire(Part.__sortEdges__([
        Part.LineSegment(V(10, 0, 0), V(50, 0, 0)).toShape(),
        Part.Arc(V(50, 0, 0), V(60 - k, k, 0), V(60, 10, 0)).toShape(),
        Part.LineSegment(V(60, 10, 0), V(60, 30, 0)).toShape(),
        Part.Arc(V(60, 30, 0), V(60 - k, 40 - k, 0), V(50, 40, 0)).toShape(),
        Part.LineSegment(V(50, 40, 0), V(10, 40, 0)).toShape(),
        Part.Arc(V(10, 40, 0), V(k, 40 - k, 0), V(0, 30, 0)).toShape(),
        Part.LineSegment(V(0, 30, 0), V(0, 10, 0)).toShape(),
        Part.Arc(V(0, 10, 0), V(k, k, 0), V(10, 0, 0)).toShape(),
    ]))).extrude(V(0, 0, 15))
    c = case("Tangent_chain", rounded,
             "Rounded rectangle: pick one top edge, r 2; the tangent "
             "chain takes the whole rim.")
    c.add([V(30, 0, 15)], 2.0)

    c = case("Stacked", plate(50, 40, 20),
             "Round on a round: r 6 edge, then r 1.5 on the edges where "
             "it meets the end faces.")
    c.add([V(25, 0, 20)], 6.0)
    c.add([V(0, 3, 17), V(50, 3, 17)], 1.5)

    stand = frame()
    bar_bottom = V(24.17, -12.85, 10)   # a bar's side at the low flange
    bar_top = V(16.96, -5.65, 45)       # the same side at the high flange
    bar_corner = V(22.47, -11.17, 27.5)  # the bar's outer corner
    c = case("Stand_ends", stand,
             "Slanted bar into both flanges: hollow rounds r 5 at its foot "
             "and head, trimmed flush with the cone (bad-fillets Cuerpo).")
    c.add([bar_bottom], 5.0)
    c.add([bar_top], 5.0)
    c.add([bar_corner], 1.0)

    c = case("Stand_order_a", stand,
             "Bar's outer corner r 1 first, then its foot r 5. The r 5 "
             "round cannot go round the r 1 round's foot (nor can other "
             "CAD systems'): it skips that piece and says why.")
    c.add([bar_corner], 1.0)
    c.add([bar_bottom], 5.0)
    if not FLAT:
        c.expect_problems = True

    c = case("Stand_order_b", stand,
             "Bar's foot r 5 first, then its outer corner r 1: the "
             "other order, so its own result.")
    c.add([bar_bottom], 5.0)
    c.add([bar_corner], 1.0)

    valve = App.openDocument(str(ROOT / "tests" / "models"
                                 / "faucet_valve.FCStd"))
    slider = valve.getObject("Pocket001").Shape.copy()
    App.closeDocument(valve.Name)
    c = case("Faucet_valve", slider,
             "A user's part, a little invalid as it comes: the curved "
             "foot edge and the rounds running on from it, 1.")
    c.add([V(0, 10.65, -5)], 1.0)

    c = case("Faucet_corner", slider,
             "The same part's inner corner, 3.94: wide enough to pass the "
             "rounded rim beside it, where it ends flat, as the face the "
             "round blends into.")
    c.add([V(-8.4845, 6.4371, -2.5)], 3.94)

    c = case("Near_tangent", slot_off_tangent(),
             "A slot's top face, r 1: one end's arc a quarter degree off "
             "tangent to the sides, rounded all round without a sliver.")
    c.add([], 1.0, faces=[V(15, 5, 6)])

    c = case("Kinked_slot", slot_off_tangent(off=0.4),
             "The same slot, its arc meeting the sides some 4 degrees off "
             "tangent: the rounds mitred there go in together, leaving "
             "no sliver where their cuts meet.")
    c.add([], 1.0, faces=[V(15, 5, 6)])

    c = case("Run_off", plate(30, 20, 6),
             "Radius larger than the side face: the round runs off it "
             "into the bottom face.")
    c.add([V(15, 0, 6)], 9.0)
    return cases


def check(cases, record):
    old = json.loads(RECORD.read_text()) if RECORD.exists() else {}
    new = {}
    failed = 0
    for c in cases:
        for obj in c.features:
            obj.touch()
        c.body.Document.recompute()
        for step, obj in enumerate(c.features, 1):
            shape = obj.Shape
            # By case and step, not label: labels shift as cases are added.
            key = "%s/%d" % (c.name, step)
            problems = getattr(obj.Proxy, "problems", [])
            ok = (shape.isValid() and len(shape.Solids) == 1
                  and (c.expect_problems or not problems))
            if obj.Refine and len(
                    bf._cones_joined(shape).Faces) < len(shape.Faces):
                ok = False
                problems = problems + ["cone face left split"]
            if obj.Refine and bf._edges_joined(shape) is not shape:
                ok = False
                problems = problems + ["edge left split"]
            try:
                shape.check(True)
            except Exception as exc:  # noqa: BLE001 - reported below
                ok = False
                problems = problems + ["BOP check: %s" % " ".join(
                    str(exc).split())[:120]]
            volume = shape.Volume
            new[key] = round(volume, 4)
            if key in old and abs(volume - old[key]) > DRIFT * old[key]:
                ok = False
                problems = problems + ["volume %.4f, was %.4f"
                                       % (volume, old[key])]
            failed += not ok
            print("%-4s %-34s valid=%s solids=%d faces=%d vol=%.4f %s" % (
                "ok" if ok else "FAIL", "%s/%s" % (c.name, obj.Label),
                shape.isValid(),
                len(shape.Solids), len(shape.Faces), volume,
                problems or ""))
    if record:
        RECORD.write_text(json.dumps(new, indent=1, sort_keys=True))
        print("recorded", RECORD)
    return failed


def main():
    App.ParamGet(bf.TIMING[0]).SetBool(bf.TIMING[1], "timing" in sys.argv)
    doc = App.newDocument("%s_cases" % KIND)
    cases = build(doc)
    for c in cases:
        c.body.Label2 = c.note
    failed = check(cases, "record" in sys.argv)
    settings = App.ParamGet("User parameter:BaseApp/Preferences/Document")
    settings.SetBool("CreateBackupFiles", False)
    doc.saveAs(str(MODEL))
    print("saved", MODEL)
    verdict = "PASSED" if not failed else "FAILED"
    print("%s CASES %s (%d failed)" % (KIND.upper(), verdict, failed))


main()
