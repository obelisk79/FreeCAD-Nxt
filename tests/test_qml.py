"""Load the panel's QML offscreen against stub context objects.

Catches what qmllint cannot: binding loops, missing model roles, and errors
raised while a delegate is actually being created. The stubs are generated
from the real modules' own declarations, so the harness cannot drift into
testing an interface the panel does not have.

    python3 tests/test_qml.py

Needs PySide6, which the interpreter running FreeCAD has and a bare system
python may not. If `import PySide6` fails here, run it with FreeCAD's own
interpreter instead of installing a second Qt.

PySide6 builds a QObject subclass's metaobject when the class is created, so
every Property and Slot has to be in the class namespace *before* type() runs
- setattr afterwards produces an object QML cannot see at all, which is how
the first version of this harness managed to hand QML a null `theme`.
"""

from __future__ import annotations

import ast
import os
import re
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("LC_ALL", "C.UTF-8")

from PySide6 import QtCore, QtGui, QtQml, QtQuick  # noqa: E402,F401
from PySide6.QtTest import QTest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "freecad" / "nxt" / "tree"
QML = ROOT / "freecad" / "nxt" / "resources" / "qml"

problems = []
BAD = ("binding loop", "is not defined", "cannot read property",
       "unable to assign", "typeerror", "referenceerror", "cannot assign",
       "is not a function", "required property",
       "no signal of the target matches")


def _handler(mode, context, message):
    text = message if isinstance(message, str) else str(message)
    print(text)
    lowered = text.lower()
    if any(token in lowered for token in BAD):
        problems.append(text)


QtCore.qInstallMessageHandler(_handler)


# --- theme stub, generated from theme.py's own property list -------------- #

def theme_properties():
    tree = ast.parse((SRC / "theme.py").read_text())
    out = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for dec in node.decorator_list:
            if (isinstance(dec, ast.Call)
                    and getattr(dec.func, "attr", "") == "Property"):
                out[node.name] = (ast.unparse(dec.args[0]) if dec.args
                                  else "str")
    return out


# The int metrics theme.py caches. Kept in step with its ratios by hand;
# a value missing here falls back to 20, which would silently change what
# the geometry assertions below mean.
SIZES = {"rowHeight": 20, "rowPad": 6, "indent": 12, "tipGutter": 14,
         "iconSize": 14, "markSize": 12, "markSizeSmall": 10,
         "fontRow": 10, "fontSmall": 9, "fontAside": 8,
         "chipHeight": 14, "fieldHeight": 17,
         # A generous cap, so the offscreen screen (800 px) leaves the
         # header full width and the name-truncation check below still
         # means what it did; the cap itself is checked against these.
         "headerMaxPercent": 60, "headerMinWidth": 220}


def make_theme(overlay=False):
    missing = [n for n, k in theme_properties().items()
               if k == "int" and n not in SIZES]
    assert not missing, (
        "theme gained int metrics the stub does not size: %s" % missing)
    ns = {"changed": QtCore.Signal(), "_overlay": overlay}
    for name, kind in theme_properties().items():
        if name == "overlay":
            ns[name] = QtCore.Property(bool, lambda self: self._overlay,
                                       notify=ns["changed"])
            continue
        if kind == "QtGui.QColor":
            value, qtype = QtGui.QColor("#7a7a7a"), QtGui.QColor
        elif kind == "bool":
            value, qtype = False, bool
        elif kind == "float":
            value, qtype = 1.0, float
        elif kind == "int":
            value, qtype = SIZES.get(name, 20), int
        else:
            value, qtype = "", str
        ns[name] = QtCore.Property(qtype, (lambda v: lambda self: v)(value),
                                   notify=ns["changed"])
    return type("Theme", (QtCore.QObject,), ns)


# --- model stub, with the real role names --------------------------------- #

def role_names():
    src = (SRC / "models.py").read_text()
    body = src[src.index("_ROLE_NAMES = {"):]
    return re.findall(r':\s*"([A-Za-z]+)"', body[:body.index("\n    }")])


NAMES = role_names()
ROLE0 = int(QtCore.Qt.ItemDataRole.UserRole) + 1

# One of each shape the delegate has to survive: a container, a profile with
# a finding and an open detail strip, a live feature, a rolled-back profile,
# and a failed feature blaming its sketch.
ROWS = [
    dict(name="Body", label="Body", depth=0, hasChildren=True, expanded=True,
         isContainer=True, isActive=True),
    dict(name="Sketch", label="Sketch", depth=1, isProfile=True, severity=1,
         dof=14, constrained=0, detailOpen=True, bodyName="Body", timeline=0,
         isLifted=True,
         notes=["redundant constraints (32)"],
         consumers=[{"name": "Pad", "label": "Pad", "props": ["Profile"]},
                    {"name": "Pocket", "label": "Pkt", "props": ["Profile"]}]),
    dict(name="Pad", label="Pad", depth=1, isFeature=True, bodyName="Body",
         timeline=1,
         refs=[{"name": "Sketch", "label": "Sketch", "severity": 1,
                "sub": "", "iconUrl": ""}]),
    dict(name="Sketch001", label="Sketch001", depth=1, isProfile=True,
         isLifted=True, afterTip=True, bodyName="Body", constrained=1,
         dof=0, timeline=2),
    dict(name="Pocket", label="Pocket", depth=1, isFeature=True,
         afterTip=True, bodyName="Body", inError=True, timeline=3,
         refs=[{"name": "Sketch001", "label": "Sketch001", "severity": 2,
                "sub": "", "iconUrl": ""},
               {"name": "Pad", "label": "Pad", "severity": 0,
                "sub": "Face3", "iconUrl": ""},
               {"name": "Datum", "label": "XY_Plane", "severity": 0,
                "sub": "", "iconUrl": ""},
               {"name": "Sketch", "label": "Sketch", "severity": 1,
                "sub": "", "iconUrl": ""}]),
    dict(name="Tool", label="Tool", depth=1, isLifted=True, bodyName="Body",
         timeline=4, detailOpen=True,
         consumers=[{"name": "Pocket", "label": "Pocket",
                     "props": ["Base"]}]),
    # The shape that opened an empty strip: an ordinary feature, not
    # lifted, nothing wrong with it, one reference - and something built
    # on top of it. Its only reason for a detail strip is the "used by"
    # list, which is exactly the section that used to be withheld from it.
    dict(name="Pocket002", label="Pocket002", depth=1, isFeature=True,
         bodyName="Body", timeline=5, detailOpen=True,
         refs=[{"name": "Sketch002", "label": "Sketch002", "severity": 0,
                "sub": "", "iconUrl": ""}],
         consumers=[{"name": "Fillet", "label": "Fillet",
                     "props": ["Base"]}],
         # One of each kind of key value, as properties.describe gives it.
         keyProps=[
             {"name": "Length", "kind": "quantity", "text": "10 mm",
              "checked": False, "options": [], "expression": "",
              "readOnly": False},
             {"name": "Offset", "kind": "quantity", "text": "4 mm",
              "checked": False, "options": [],
              "expression": "Sketch.Width * 2", "readOnly": False},
             {"name": "Type", "kind": "enum", "text": "Dimension",
              "checked": False, "readOnly": False, "expression": "",
              "options": ["Dimension", "ThroughAll", "UpToFace",
                          "UpToFirstFaceFromSketchPlane"]},
             {"name": "Reversed", "kind": "bool", "text": "",
              "checked": True, "options": [], "expression": "",
              "readOnly": False}],
         propertyCount=31),
    # A flagged reference whose name is too long to show: 29 characters,
    # so the chip has to fall back to its icon rather than elide.
    dict(name="Fillet", label="Fillet", depth=1, isFeature=True,
         bodyName="Body", timeline=6,
         refs=[{"name": "Long", "severity": 2,
                "label": "Mounting_Bracket_Profile_Rev2",
                "sub": "", "iconUrl": ""}]),
]

DEFAULTS = dict(name="", label="", depth=0, hasChildren=False, expanded=False,
                objectVisible=True, selected=False, iconUrl="", refs=[],
                isContainer=False, inError=False, touched=False,
                highlighted=False, isFeature=False, afterTip=False,
                isProfile=False, severity=0, notes=[], dof=-1, constrained=-1,
                detailOpen=False, timeline=0, bodyName="", consumers=[],
                isLifted=False, isActive=False, keyProps=[],
                propertyCount=0, branches=[], activeFrom=-1)
# refs entries must carry every key the delegate reads; a missing one shows
# up as undefined rather than as an error, so it is worth being strict.
REF_KEYS = {"name", "label", "severity", "sub", "iconUrl"}
for _row in ROWS:
    for _ref in _row.get("refs", ()):
        assert set(_ref) == REF_KEYS, "ref keys drifted: %s" % sorted(_ref)


class Rows(QtCore.QAbstractListModel):
    def rowCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(ROWS)

    def roleNames(self):
        return {ROLE0 + i: QtCore.QByteArray(n.encode())
                for i, n in enumerate(NAMES)}

    def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        offset = role - ROLE0
        if not (0 <= offset < len(NAMES)):
            return None
        row = dict(DEFAULTS)
        row.update(ROWS[index.row()])
        return row.get(NAMES[offset])


# --- bridge stub, generated from bridge.py's slot list -------------------- #

def bridge_slots():
    tree = ast.parse((SRC / "bridge.py").read_text())
    out = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for dec in node.decorator_list:
            if (isinstance(dec, ast.Call)
                    and getattr(dec.func, "attr", "") == "Slot"):
                types = []
                for arg in dec.args:
                    text = ast.unparse(arg).strip("'\"")
                    types.append({"str": str, "int": int, "bool": bool,
                                  "float": float}.get(text, "QVariant"))
                out[node.name] = types
    return out


ROWS_MODEL = Rows()
BARS = [{"body": "Body", "label": "Body", "pos": 2, "minPos": 2, "maxPos": 4,
         "depth": 1, "step": 1, "steps": 2}]


def make_bridge():
    ns = {
        "changed": QtCore.Signal(),
        "revealTreeRow": QtCore.Signal(int),
        "rowHeld": QtCore.Signal(int),
        "rowReleased": QtCore.Signal(),
        "detailAutoShow": QtCore.Property(bool, lambda self: True,
                                          constant=True),
        "pinnedDetails": QtCore.Property(list, lambda self: ["Sketch"],
                                         constant=True),
        "propertyInspectorRequested": QtCore.Signal(int),
        "contextMenuRequested": QtCore.Signal(float, float),
        "renameRowRequested": QtCore.Signal(int),
        "flashRows": QtCore.Signal(list),
        "treeModel": QtCore.Property(QtCore.QObject,
                                     lambda self: ROWS_MODEL, constant=True),
        "hasDocument": QtCore.Property(bool, lambda self: True),
        "documentLabel": QtCore.Property(
            str, lambda self: "PartDesignExample"),
        "profileCount": QtCore.Property(int, lambda self: 2),
        "problemCount": QtCore.Property(int, lambda self: 1),
        "searchResults": QtCore.Property(list, lambda self: []),
        "tipBars": QtCore.Property(list, lambda self: BARS),
        # One row marked as the origin of a 3D pick, so its binding runs.
        "pickOrigins": QtCore.Property(list, lambda self: ["Pad"],
                                       constant=True),
        # Arrows from the Pad, so the overlay paints every kind.
        "linkArrows": QtCore.Property("QVariantMap", lambda self: {
            "source": 2, "links": [
                {"row": 1, "dir": "in", "kind": "geometry", "count": 1},
                {"row": 3, "dir": "out", "kind": "attachment", "count": 2},
                {"row": 40, "dir": "out", "kind": "link", "count": 1}]},
            constant=True),
    }
    for name, types in bridge_slots().items():
        if name in ns:
            continue
        ns[name] = QtCore.Slot(*types)(
            (lambda n: lambda self, *a: None)(name))
    return type("Bridge", (QtCore.QObject,), ns)


class Host(QtCore.QObject):
    viewOverlayChanged = QtCore.Signal()

    @QtCore.Property(bool, notify=viewOverlayChanged)
    def viewOverlay(self):  # noqa: N802
        return False

    @QtCore.Slot()
    def repaintBehind(self):
        pass

    @QtCore.Slot(result=QtCore.QPointF)
    def menuAnchorOffset(self):
        return QtCore.QPointF(0, 0)


def visual_tree(item, depth=0):
    """Every item in the *visual* tree below `item`.

    findChildren() is not enough: a delegate's QObject parent is the
    delegate model, not the view, so the rows a ListView creates are
    invisible to it. childItems() is the tree that actually got built.
    """
    out = []
    if depth > 24:
        return out
    try:
        kids = item.childItems()
    except AttributeError:
        return out
    for kid in kids:
        out.append(kid)
        out.extend(visual_tree(kid, depth + 1))
    return out


def find(item, cls_name):
    for child in visual_tree(item):
        if child.metaObject().className().startswith(cls_name):
            return child
    return None


app = QtGui.QGuiApplication(sys.argv)
KEEP = []      # nothing is torn down: dropping a context property while the
# object tree still reads it re-evaluates every binding
# against null, which is noise, not a finding.


class Isolation(QtCore.QObject):
    """Stands in for isolate.Isolation.

    On, so the row dimming's bindings run.
    """

    changed = QtCore.Signal()

    @QtCore.Property(bool, notify=changed)
    def isActive(self):  # noqa: N802
        return True

    @QtCore.Property(str, notify=changed)
    def notice(self):
        return "Isolated: Pad"

    @QtCore.Property("QVariantMap", notify=changed)
    def keptNames(self):  # noqa: N802
        return {"Body": True, "Pad": True}

    @QtCore.Slot(result=bool)
    def leave(self):
        return True


def run(overlay):
    # A QQuickView, not a bare QQmlComponent: items outside a window are
    # never polished, so a ListView in one realises no delegates at all and
    # the harness would pass by doing nothing.
    view = QtQuick.QQuickView()
    theme, bridge, host = make_theme(overlay)(), make_bridge()(), Host()
    view.engine().addImportPath(str(QML))
    ctx = view.rootContext()
    ctx.setContextProperty("theme", theme)
    ctx.setContextProperty("nxt", bridge)
    ctx.setContextProperty("host", host)
    isolation = Isolation()
    ctx.setContextProperty("isolation", isolation)
    view.isolation = isolation      # kept alive as long as the view
    view.setResizeMode(QtQuick.QQuickView.ResizeMode.SizeRootObjectToView)
    view.resize(320, 480)
    view.setSource(QtCore.QUrl.fromLocalFile(str(QML / "NxtTree.qml")))

    if view.status() == QtQuick.QQuickView.Status.Error:
        for err in view.errors():
            print("VIEW ERROR:", err.toString())
            problems.append(err.toString())
        return

    view.show()
    KEEP.extend([view, theme, bridge, host])
    # Real time has to pass, not just event turns: the bar animates into
    # position, and a Behavior that never advances leaves it at wherever it
    # started - which looks exactly like a positioning bug.
    deadline = time.monotonic() + 1.5
    while time.monotonic() < deadline:
        app.processEvents(QtCore.QEventLoop.ProcessEventsFlag.AllEvents, 10)
        time.sleep(0.005)

    def settle(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents(
                QtCore.QEventLoop.ProcessEventsFlag.AllEvents, 10)
            time.sleep(0.005)

    root = view.rootObject()

    # Nxt's overlay asks the panel, per press, whether it draws anything
    # there (view_overlay.py). The header is the panel's; far below the
    # last row is the model's.
    def wants(x, y):
        return QtCore.QMetaObject.invokeMethod(
            root, "wantsPoint", QtCore.Qt.ConnectionType.DirectConnection,
            QtCore.Q_RETURN_ARG("QVariant"),
            QtCore.Q_ARG("QVariant", float(x)),
            QtCore.Q_ARG("QVariant", float(y)))
    # And a container's expand arrow, which sits outside its pill.
    arrows = [c for c in visual_tree(root)
              if c.metaObject().className().startswith("Disclosure")
              and c.property("shown")]
    if arrows:
        spot = arrows[0].mapToItem(root, QtCore.QPointF(
            arrows[0].width() / 2, arrows[0].height() / 2))
        if wants(spot.x(), spot.y()) is not True:
            problems.append("overlay=%s: the expand arrow passes clicks "
                            "through" % overlay)
    else:
        problems.append("overlay=%s: no expand arrow found" % overlay)
    if wants(10, 10) is not True or wants(300, 470) is not False:
        problems.append("overlay=%s: wantsPoint header %r, empty %r"
                        % (overlay, wants(10, 10), wants(300, 470)))

    # More than one ListView in the tree: the search results are a list too,
    # and an empty one sorts first in findChildren. Take the populated one.
    lists = [c for c in visual_tree(root)
             if c.metaObject().className().startswith("QQuickListView")]
    counts = [(c.property("count") or 0, c.property("contentHeight") or 0.0)
              for c in lists]
    count, content = max(counts) if counts else (-1, 0.0)
    listview = None
    for c in lists:
        if (c.property("count") or 0) == count:
            listview = c
            break
    print("  overlay=%-5s listviews=%s counts=%s -> rows=%s contentHeight=%s"
          % (overlay, len(lists), [c for c, _h in counts], count, content))

    # The bar has to land on the boundary below its row even though a row
    # above it is taller than the others. This is the whole risk of letting
    # the detail strip change a delegate's height, so it is checked rather
    # than eyeballed.
    # The header is capped at a share of the screen, never below a floor.
    header = [c for c in visual_tree(root)
              if c.objectName() == "header"]
    if header:
        screen_w = app.primaryScreen().size().width()
        want = min(root.property("width"),
                   max(SIZES["headerMinWidth"],
                       screen_w * SIZES["headerMaxPercent"] / 100))
        got = header[0].property("width")
        print("     header: width %.1f  expected %.1f  (screen %d)"
              % (got, want, screen_w))
        if abs(got - want) > 0.5:
            problems.append("overlay=%s: header width %.1f, expected %.1f"
                            % (overlay, got, want))
        # A panel wider than the cap: the header stops at the cap.
        view.resize(700, 480)
        settle(0.1)
        capped = header[0].property("width")
        strips = [c.property("width") for c in visual_tree(root)
                  if c.objectName() == "detail" and c.property("visible")]
        view.resize(320, 480)
        settle(0.1)
        cap = max(SIZES["headerMinWidth"],
                  screen_w * SIZES["headerMaxPercent"] / 100)
        print("     header in a 700 px panel: %.1f (cap %.1f)"
              % (capped, cap))
        if abs(capped - min(700, cap)) > 0.5:
            problems.append("overlay=%s: header not capped (%.1f)"
                            % (overlay, capped))
        print("     open detail strips in a 700 px panel: %s" % strips)
        if not strips or any(abs(w - min(700, cap)) > 0.5 for w in strips):
            problems.append("overlay=%s: detail strip not capped like the "
                            "header (%s)" % (overlay, strips))
    else:
        problems.append("header not found")

    # The document name should not be truncated while the search field
    # beside it still has room to give.
    labels = [c for c in visual_tree(root)
              if c.metaObject().className().startswith("QQuickText") and
              c.property("text") == "PartDesignExample"]
    if labels:
        w = labels[0].property("width")
        iw = labels[0].property("implicitWidth")
        print("     doc label: width %.0f of implicit %.0f" % (w, iw))
        if w < iw - 0.5:
            problems.append("overlay=%s: document name truncated at %.0f "
                            "when it wants %.0f" % (overlay, w, iw))
    else:
        problems.append("overlay=%s: no document label found" % overlay)

    # The key values in an open strip: a plain value and an expression
    # shown in their fields, and the link to the inspector with its count.
    texts = {c.property("text") for c in visual_tree(root)
             if c.metaObject().className().startswith(("QQuickText",
                                                       "QQuickTextInput"))}
    for want in ("10 mm", "= Sketch.Width * 2", "Dimension  ▾", "on",
                 "All properties · 31…"):
        if want not in texts:
            problems.append("overlay=%s: key value %r not shown"
                            % (overlay, want))

    # A rebuild must not recreate the key value fields: that is what threw
    # away the focus of a field being typed in. Re-announce the row with a
    # fresh list of the same length and check the field is the same object.
    def fields():
        return [c for c in visual_tree(root)
                if c.metaObject().className().startswith("KeyValue")]
    # Python wrappers are not stable, so the survivor is recognised by a
    # name given to it before the refresh.
    before = fields()
    for field in before:
        field.setObjectName("survivor")
    row = next(i for i, r in enumerate(ROWS) if r.get("keyProps"))
    ROWS[row]["keyProps"] = [dict(e) for e in ROWS[row]["keyProps"]]
    index = ROWS_MODEL.index(row)
    ROWS_MODEL.dataChanged.emit(index, index)
    settle(0.1)
    kept = sum(1 for f in fields() if f.objectName() == "survivor")
    if not before or kept != len(before):
        problems.append("overlay=%s: a data refresh recreated key value "
                        "fields (%d of %d kept)"
                        % (overlay, kept, len(before)))

    # The choice opens a drop-down above the whole panel, and a press
    # outside it closes it.
    chips = [c for c in visual_tree(root)
             if c.metaObject().className().startswith("Chip")
             and c.property("text") == "Dimension  ▾"]
    if chips:
        centre = chips[0].mapToScene(QtCore.QPointF(
            chips[0].property("width") / 2, chips[0].property("height") / 2))
        QTest.mouseClick(view, QtCore.Qt.MouseButton.LeftButton,
                         QtCore.Qt.KeyboardModifier.NoModifier,
                         centre.toPoint())
        settle(0.1)
        lists = [c for c in view.contentItem().childItems()
                 if c.metaObject().className().startswith("ChoiceList")]
        shown = len(lists) == 1 and lists[0].property("visible")
        print("     choice drop-down: %s" % ("open" if shown else "missing"))
        # Wide enough for its longest option, not stuck at the chip's.
        if shown:
            box = [c for c in lists[0].childItems()
                   if c.metaObject().className().startswith("QQuickRect")]
            box = box[0]
            need = lists[0].property("widest")
            print("     drop-down width %.0f for longest option %.0f"
                  % (box.property("width"), need))
            if need <= 0 or box.property("width") < need + 20:
                problems.append("overlay=%s: drop-down narrower than its "
                                "options" % overlay)
        if not shown:
            problems.append("overlay=%s: the choice did not open a "
                            "drop-down" % overlay)
        QTest.mouseClick(view, QtCore.Qt.MouseButton.LeftButton,
                         QtCore.Qt.KeyboardModifier.NoModifier,
                         QtCore.QPoint(5, 470))
        settle(0.1)
        if any(c.metaObject().className().startswith("ChoiceList")
               for c in view.contentItem().childItems()):
            problems.append("overlay=%s: a press outside did not close the "
                            "drop-down" % overlay)
    else:
        problems.append("overlay=%s: no choice chip" % overlay)

    # Entering a quantity's field selects its number and not its unit, so
    # typing replaces the value; an expression is selected whole.
    inputs = {c.property("text"): c for c in visual_tree(root)
              if c.metaObject().className() == "QQuickTextInput"}
    for text, want in (("10 mm", "10"),
                       ("= Sketch.Width * 2", "= Sketch.Width * 2")):
        field = inputs.get(text)
        if field is None:
            problems.append("overlay=%s: no field showing %r"
                            % (overlay, text))
            continue
        spot = field.mapToScene(QtCore.QPointF(
            field.property("width") - 2, field.property("height") / 2))
        QTest.mouseClick(view, QtCore.Qt.MouseButton.LeftButton,
                         QtCore.Qt.KeyboardModifier.NoModifier,
                         spot.toPoint())
        settle(0.1)
        got = field.property("selectedText")
        print("     click into %r selects %r" % (text, got))
        if got != want:
            problems.append("overlay=%s: clicking into %r selected %r, "
                            "not %r" % (overlay, text, got, want))
    QTest.keyClick(view, QtCore.Qt.Key.Key_Escape)
    settle(0.1)

    # Live mode switches and bare `changed` re-notifications. Every theme
    # property shares one notify signal, so a flip re-evaluates the label
    # and the tail in the same pass - which is where a loop that a fresh
    # load never exercises shows up.
    loops_before = sum(1 for p in problems if "binding loop" in p.lower())
    for _flip in range(2):
        theme._overlay = not theme._overlay
        theme.changed.emit()
        settle(0.2)
    theme.changed.emit()
    settle(0.2)
    loops = sum(1 for p in problems
                if "binding loop" in p.lower()) - loops_before
    print("     live mode flips: %d binding-loop reports" % loops)

    # The rename gesture: a single click on the name of an already
    # selected row. Its delay must come out as a real number - reading it
    # from the platform means an undefined would land as NaN and the timer
    # would never fire, which is indistinguishable from "not implemented".
    a_row = find(root, "TreeRow")
    if a_row is None:
        problems.append("overlay=%s: no TreeRow to test" % overlay)
    else:
        ctx = QtQml.qmlContext(a_row)

        def ask(expression):
            expr = QtQml.QQmlExpression(ctx, a_row, expression)
            value = expr.evaluate()
            if expr.hasError():
                problems.append("%s: %s" % (expression,
                                            expr.error().toString()))
            return value[0] if isinstance(value, tuple) else value

        # A component's ids are not properties of the object, so the
        # expression cannot name them - the label and the timer are found
        # from outside instead, which is a fair test anyway.
        timers = [c for c in a_row.findChildren(QtCore.QObject)
                  if c.metaObject().className().startswith("QQmlTimer")]
        delay = timers[0].property("interval") if timers else None
        labels = [c for c in visual_tree(a_row)
                  if c.metaObject().className().startswith("QQuickText") and
                  c.property("text") == a_row.property("label")]
        if labels:
            label = labels[0]
            mid = label.property("x") + min(label.property("width"),
                                            label.property("contentWidth")) / 2
            on_glyph = ask("overGlyphs(%f, height / 2)" % mid)
        else:
            on_glyph = None
            problems.append("overlay=%s: no label found on the row" % overlay)
        off_glyph = ask("overGlyphs(width - 2, height / 2)")
        print("     rename: delay %s ms  on-name %s  past-name %s"
              % (delay, on_glyph, off_glyph))
        if not isinstance(delay, (int, float)) or delay <= 0 or delay != delay:
            problems.append(
                "overlay=%s: rename delay is %r" % (overlay, delay))
        if on_glyph is not True or off_glyph is not False:
            problems.append(
                "overlay=%s: the name hit-test is wrong (on %r, past %r)"
                % (overlay, on_glyph, off_glyph))

    # The active container has to be visible without relying on colour, so
    # the row draws a rule as well as tinting. Checked by presence: the
    # active row must have a visible child the others do not.
    def marks_on(row_item):
        # By objectName, not by shape: a row already draws several narrow
        # rules - the rollback spine, the ancestor guides - and guessing
        # between them tests the heuristic rather than the mark.
        return sum(1 for c in visual_tree(row_item)
                   if c.objectName() == "activeMark" and c.property("visible"))

    active_marks, other_marks = None, []
    for c in visual_tree(root):
        if not c.metaObject().className().startswith("TreeRow"):
            continue
        if c.property("isActive"):
            active_marks = marks_on(c)
        else:
            other_marks.append((c.property("name"), marks_on(c)))
    inactive_max = max((n for _r, n in other_marks), default=0)
    print("     active mark: active row %s  busiest inactive row %s"
          % (active_marks, inactive_max))
    if active_marks is None:
        problems.append("overlay=%s: no active row in the fixture" % overlay)
    elif active_marks <= inactive_max:
        problems.append(
            "overlay=%s: the active row shows %s active marks and an "
            "inactive one shows %s - it is not distinguishing them"
            % (overlay, active_marks, inactive_max))

    # A gutter mark must never open an empty box. Every row that offers
    # one has to have something in it, and the row that broke this had a
    # consumer and nothing else.
    for c in visual_tree(root):
        if not c.metaObject().className().startswith("TreeRow"):
            continue
        if not c.property("detailOpen") or not c.property("hasDetail"):
            continue
        strips = [d for d in visual_tree(c)
                  if d.metaObject().className().startswith("DetailStrip")]
        filled = 0
        for strip in strips:
            for child in visual_tree(strip):
                if child.property("visible") and child.property("height") > 0:
                    filled += 1
        print("     detail on %-10s visible items %d"
              % (c.property("name"), filled))
        if filled == 0:
            problems.append(
                "overlay=%s: %s offers a detail strip and opens an empty one"
                % (overlay, c.property("name")))

    # The whole point of the adaptive cluster: four references must not
    # cost four names' worth of row. Chips inside an open detail strip are
    # excluded - only the ones on the row line count.
    def chips_on(row_item):
        out = []
        for c in visual_tree(row_item):
            if not c.metaObject().className().startswith("Chip"):
                continue
            here = c.mapToItem(row_item, 0, 0)
            if here.y() < 20 and c.property("visible"):
                out.append(c)
        return out

    widths = {}
    for c in visual_tree(root):
        if not c.metaObject().className().startswith("TreeRow"):
            continue
        name = c.property("name")
        chips = chips_on(c)
        if chips:
            widths[name] = (len(chips),
                            round(sum(ch.property("width") for ch in chips)))
    print("     chips on the row: %s" % widths)
    # A clean reference is no longer chipped at all.
    if "Pocket002" in widths:
        problems.append(
            "overlay=%s: Pocket002's reference is clean and still chipped"
            % overlay)
    # A flagged one too long to name falls back to its icon, which is
    # square - so its width should be about its height, not its text.
    long_chip = widths.get("Fillet")
    if not long_chip or long_chip[0] != 1:
        problems.append("overlay=%s: the long flagged reference lost its chip"
                        % overlay)
    elif long_chip[1] > 24:
        problems.append(
            "overlay=%s: a 29-character name drew a %dpx chip instead of "
            "falling back to its icon" % (overlay, long_chip[1]))

    one = widths.get("Pad")
    many = widths.get("Pocket")
    # Pocket reads four things, two of them flagged. Only the flagged ones
    # are chipped, and because there is more than one they go compact.
    flagged = sum(1 for r in next(r for r in ROWS if r["name"] == "Pocket")
                  ["refs"] if r["severity"] > 0)
    if one and many:
        if many[0] != flagged:
            problems.append(
                "overlay=%s: %d flagged references of four drew %d chips"
                % (overlay, flagged, many[0]))
        elif many[1] > one[1] * 1.6:
            problems.append(
                "overlay=%s: %d compact chips take %dpx against %dpx for "
                "one named chip - the cluster is not paying for itself"
                % (overlay, many[0], many[1], one[1]))
    else:
        problems.append("overlay=%s: could not measure the chip cluster"
                        % overlay)

    bar = find(root, "TimelineBar")
    if bar is None:
        problems.append("overlay=%s: no TimelineBar was created" % overlay)
    else:
        rows_above = []
        target = None
        for c in visual_tree(root):
            if c.metaObject().className().startswith("TreeRow"):
                rows_above.append((c.property("y"), c.property("height"),
                                   c.property("name"),
                                   c.property("pillRight")))
        rows_above.sort()
        listw = listview.property("width") if listview else 0
        # bar pos is 2, so the boundary is the bottom of the third row
        if len(rows_above) >= 3:
            target = rows_above[2][0] + rows_above[2][1]
        got = bar.property("y") + bar.property("height") / 2 - 3
        print("     rows: %s" % [(r[2], round(r[0]), round(r[1]))
                                 for r in rows_above])
        print("     bar boundary: got %.1f  expected %.1f (bottom of %s)"
              % (got, target if target is not None else -1,
                 rows_above[2][2] if len(rows_above) >= 3 else "?"))
        if target is None or abs(got - target) > 1.0:
            problems.append(
                "overlay=%s: bar sits at %.1f, not on the boundary at %.1f"
                % (overlay, got, target if target is not None else -1))
        # Evaluated in the bar's own QML context rather than through
        # invokeMethod: a delegate's metaobject is the wrapper the view
        # made, and reaching a QML-declared function through it is a
        # detail of how the delegate was created rather than of the bar.
        expr = QtQml.QQmlExpression(QtQml.qmlContext(bar), bar, "slotAt(13)")
        result = expr.evaluate()
        if expr.hasError():
            problems.append("slotAt: " + expr.error().toString())
        slot = result[0] if isinstance(result, tuple) else result
        print("     slotAt(top of list) -> %s (clamped to minPos 2)" % slot)
        if slot != 2:
            problems.append("overlay=%s: slotAt above the first feature "
                            "returned %s, expected the clamp to 2"
                            % (overlay, slot))

        # In overlay mode the bar must stop just past whichever neighbour
        # reaches furthest right, not run the width of the list.
        if overlay:
            edges = [r[3] for r in rows_above[2:4] if len(r) > 3 and
                     r[3] is not None]
            want = max(edges) + 12 - bar.property("x") if edges else None
            got_w = bar.property("width")
            print("     bar width: got %.1f  expected %.1f  (list is %.0f)"
                  % (got_w, want if want else -1, listw))
            if want is None or abs(got_w - want) > 1.0:
                problems.append("bar width %.1f, expected %.1f" %
                                (got_w, want if want else -1))
            if got_w >= listw - 10:
                problems.append("bar still spans the list in overlay mode")

        # A held bar follows the pointer continuously. Quantising the
        # drawing as well as the slot is what made it step a row at a time
        # under a smoothly moving hand, so the test is that a fractional
        # position survives.
        rest = bar.property("y")
        bar.setProperty("dragY", rest + 7.5)
        bar.setProperty("dragging", True)
        settle(0.15)
        held = bar.property("y")
        bar.setProperty("dragY", rest + 8.25)
        settle(0.15)
        moved = bar.property("y")
        bar.setProperty("dragging", False)
        settle(0.4)
        back = bar.property("y")
        print("     drag: rest %.2f  held %.2f  moved %.2f  back %.2f"
              % (rest, held, moved, back))
        if (abs(held - (rest + 7.5)) > 0.01
                or abs(moved - (rest + 8.25)) > 0.01):
            problems.append("overlay=%s: a held bar does not follow its "
                            "drag position continuously (%.2f, %.2f)"
                            % (overlay, held, moved))
        if abs(back - rest) > 0.5:
            problems.append("overlay=%s: released bar settled at %.2f, "
                            "not back on the boundary at %.2f"
                            % (overlay, back, rest))

        # Scrolling moves the bar in lockstep with the rows. An animation
        # on `y` made it trail the list and rubber-band into place.
        listview.setProperty("contentY", 12)
        app.processEvents()
        scrolled = bar.property("y")
        listview.setProperty("contentY", 0)
        settle(0.2)
        print("     scroll: rest %.2f  scrolled 12 -> %.2f" % (back, scrolled))
        if abs(scrolled - (back - 12)) > 0.01:
            problems.append("overlay=%s: the bar lags a scroll (%.2f, want "
                            "%.2f)" % (overlay, scrolled, back - 12))

        # The drag gap: opening a space under a row has to make that row
        # taller and move the bar into the middle of the space.
        before_h = listview.property("contentHeight")
        listview.setProperty("dropGap", 3)
        settle(0.4)
        after_h = listview.property("contentHeight")
        listview.setProperty("dropGap", -1)
        settle(0.4)
        back_h = listview.property("contentHeight")
        print("     gap: contentHeight %.0f -> %.0f -> %.0f"
              % (before_h, after_h, back_h))
        if after_h <= before_h:
            problems.append("overlay=%s: opening a gap did not grow the list"
                            % overlay)
        if abs(back_h - before_h) > 0.5:
            problems.append("overlay=%s: the gap did not close again (%.1f)"
                            % (overlay, back_h))

    plain = 20 * len(ROWS)
    if content <= plain:
        problems.append(
            "overlay=%s: the open detail strip added no height "
            "(contentHeight %s, %s rows at 20px = %s)"
            % (overlay, content, len(ROWS), plain))
    if count != len(ROWS):
        problems.append("overlay=%s: %s of %s delegates realised"
                        % (overlay, count, len(ROWS)))


print("loading:")
run(False)
run(True)

print()
print("roles:", len(NAMES), " rows:", len(ROWS))
print("PROBLEMS:", len(problems))
for text in problems:
    print("  *", text)
print("HARNESS", "FAILED" if problems else "PASSED")
os._exit(1 if problems else 0)
