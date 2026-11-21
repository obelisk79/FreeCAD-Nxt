"""Ambient occlusion: its settings, what navigation does, the page.

Run with: python3 tests/test_ambient_occlusion.py   (needs PySide6)

Logic with stubs: the Coin node tree and the GL callbacks need a running
FreeCAD and are not exercised here.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import types  # noqa: E402

import fakes  # noqa: E402
from PySide6 import QtWidgets  # noqa: E402

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
STORE: dict[str, Any] = {}
App, Gui = fakes.install(ParamGet=fakes.params(STORE))

from freecad.nxt.core import pyopengl, settings  # noqa: E402
from freecad.nxt.tools import ambient_occlusion as ao  # noqa: E402
from freecad.nxt.tools import (  # noqa: E402
    ao_lines,
    ao_pipeline,
    ao_temporal,
)
from freecad.nxt.ui import prefs  # noqa: E402


class NavigationTests(unittest.TestCase):

    def test_still_camera_shows_the_chosen_level(self) -> None:
        for mode in ao.NAVIGATION:
            self.assertEqual(ao.display(mode, False), (True, 0))

    def test_moving_camera(self) -> None:
        self.assertEqual(ao.display(ao.KEEP, True), (True, 0))
        self.assertEqual(ao.display(ao.REDUCE, True), (True, 1))
        self.assertEqual(ao.display(ao.PAUSE, True), (False, 0))

    def test_every_mode_is_offered(self) -> None:
        self.assertEqual(prefs.CHOICES["AOWhileNavigating"], ao.NAVIGATION)
        self.assertIn(settings.DEFAULTS["AOWhileNavigating"], ao.NAVIGATION)


class LookTests(unittest.TestCase):

    def setUp(self) -> None:
        STORE.clear()
        self.saved = ao_temporal.available
        ao_temporal.available = lambda: True  # type: ignore[assignment]

    def tearDown(self) -> None:
        ao_temporal.available = self.saved  # type: ignore[assignment]

    def test_defaults(self) -> None:
        look = ao.look(settings.get, 2.0)
        self.assertEqual(look, ao_pipeline.Look("medium", 0.8, 2.0, True))
        self.assertFalse(settings.DEFAULTS["AmbientOcclusion"])

    def test_unknown_quality_falls_back(self) -> None:
        STORE["AOQuality"] = "ultra"
        self.assertEqual(ao.look(settings.get, 1.0).quality, "medium")

    def test_every_quality_has_passes(self) -> None:
        for quality in (*ao.QUALITIES, ao_pipeline.INTERACTIVE):
            self.assertIn(quality, ao_pipeline.QUALITY)
        self.assertEqual(prefs.CHOICES["AOQuality"], ao.QUALITIES)

    def test_temporal_budget_is_lighter_for_every_level(self) -> None:
        for level, (dirs, steps, *scales) in ao_pipeline.QUALITY.items():
            t_dirs, t_steps, *t_scales = ao_pipeline.TEMPORAL_QUALITY[level]
            self.assertLess(t_dirs * t_steps, dirs * steps, level)
            self.assertEqual(t_scales, scales, level)

    def test_temporal_failure_falls_back(self) -> None:
        ao_temporal.available = self.saved  # type: ignore[assignment]
        self.addCleanup(setattr, ao_temporal, "failed", False)
        ao_temporal.failed = True
        self.assertFalse(ao.look(settings.get, 1.0).temporal)

    def test_temporal_needs_pyopengl(self) -> None:
        ao_temporal.available = lambda: False  # type: ignore[assignment]
        self.assertFalse(ao.look(settings.get, 1.0).temporal)

    def test_a_new_look_is_a_new_signature(self) -> None:
        a = ao.look(settings.get, 1.0)
        STORE["AOIntensity"] = 2.0
        b = ao.look(settings.get, 1.0)
        self.assertNotEqual(ao_pipeline.signature(10, 10, 1, 2, 3, a),
                            ao_pipeline.signature(10, 10, 1, 2, 3, b))


class SizeTests(unittest.TestCase):

    def test_auto_radius(self) -> None:
        self.assertEqual(ao.diagonal(None), 0.0)
        self.assertEqual(ao.auto_radius(ao.diagonal((0,) * 6), 6.0), 0.0)
        cube = ao.diagonal((0, 0, 0, 100, 100, 100))    # 173.2 mm
        # 6 % and 12 % of it, to two digits
        self.assertEqual(ao.auto_radius(cube, 6.0), 10.0)
        self.assertEqual(ao.auto_radius(cube, 12.0), 21.0)

    def test_spread_counts_only_with_an_automatic_radius(self) -> None:
        page = prefs.NxtVisualizationPage()
        STORE.update(AmbientOcclusion=True, AORadius=0.0)
        page.loadSettings()
        self.assertTrue(page._spread.isEnabled())
        page._radius.setValue(5.0)
        self.assertFalse(page._spread.isEnabled())

    def test_texture_size(self) -> None:
        self.assertEqual(ao_pipeline.texture_size(1000, 500, 0.5),
                         (500, 250))
        self.assertEqual(ao_pipeline.texture_size(2, 2, 0.5),
                         (ao_pipeline.MIN_TEXTURE, ao_pipeline.MIN_TEXTURE))
        width, _ = ao_pipeline.texture_size(20000, 100, 1.0)
        self.assertEqual(width, ao_pipeline.MAX_TEXTURE)


class PreferencesTests(unittest.TestCase):

    def setUp(self) -> None:
        STORE.clear()
        self.applied: list[set[str]] = []
        self.saved = prefs.apply
        prefs.apply = self.applied.append  # type: ignore[assignment]

    def tearDown(self) -> None:
        prefs.apply = self.saved  # type: ignore[assignment]

    def test_quick_switch(self) -> None:
        self.assertIn("AmbientOcclusion", prefs.QUICK)
        quick = prefs.Preferences()
        quick.set("AmbientOcclusion", True)
        self.assertTrue(STORE["AmbientOcclusion"])
        self.assertEqual(self.applied, [{"AmbientOcclusion"}])

    def test_page_round_trip(self) -> None:
        STORE.update(AOQuality="high", AOIntensity=1.5, AORadius=4.0,
                     AOSpread=12.0,
                     AOWhileNavigating="reduce", AOResumeDelay=500,
                     AOTemporal=False)
        page = prefs.NxtVisualizationPage()
        page.loadSettings()
        STORE.clear()
        page.saveSettings()
        self.assertEqual(STORE["AOQuality"], "high")
        self.assertEqual(STORE["AOWhileNavigating"], "reduce")
        self.assertAlmostEqual(STORE["AOIntensity"], 1.5)
        self.assertAlmostEqual(STORE["AORadius"], 4.0)
        self.assertAlmostEqual(STORE["AOSpread"], 12.0)
        self.assertEqual(STORE["AOResumeDelay"], 500)
        self.assertFalse(STORE["AOTemporal"])
        self.assertEqual(self.applied[-1], set(prefs.OCCLUSION))

    def test_page_reset(self) -> None:
        STORE.update(AmbientOcclusion=False, AOQuality="low")
        page = prefs.NxtVisualizationPage()
        page.loadSettings()
        page._reset()
        page.saveSettings()
        for key in prefs.OCCLUSION:
            self.assertEqual(STORE[key], settings.DEFAULTS[key], key)

    def test_switched_off_greys_the_fields(self) -> None:
        STORE["AmbientOcclusion"] = False
        page = prefs.NxtVisualizationPage()
        page.loadSettings()
        self.assertFalse(page._intensity.isEnabled())

    def test_page_says_what_is_missing(self) -> None:
        page = prefs.NxtVisualizationPage()
        missing = pyopengl.missing() is not None
        self.assertEqual(page._needs.isVisibleTo(page.form), missing)
        self.assertEqual(page._temporal.isEnabled(), not missing)


class Node:
    """A Coin node whose group must not be touched once freed."""

    def __init__(self, freed: bool = False) -> None:
        self.freed = freed
        self.refs = 0
        self.children: list[Node] = []

    def ref(self) -> None:
        self.refs += 1

    def unref(self) -> None:
        self.refs -= 1

    def addChild(self, child: Node) -> None:  # noqa: N802 - Coin's API
        self._alive()
        self.children.append(child)

    def findChild(self, child: Node) -> int:  # noqa: N802 - Coin's API
        self._alive()
        return self.children.index(child) if child in self.children else -1

    def removeChild(self, index: int) -> None:  # noqa: N802 - Coin's API
        self._alive()
        del self.children[index]

    def insertChild(self, child: Node,  # noqa: N802 - Coin's API
                    index: int) -> None:
        self._alive()
        self.children.insert(index, child)

    def _alive(self) -> None:
        if self.freed:
            raise AssertionError("touched a freed scene graph")


class Frame:
    """ao_pipeline.FramePass, without Coin."""

    def __init__(self) -> None:
        self.node = Node()
        self.prepass: Node | None = None

    def show(self, prepass: Node | None) -> None:
        self.prepass = prepass


class Sensor:
    def __init__(self, *_args: Any) -> None:
        self.attached = True

    def detach(self) -> None:
        self.attached = False


class ClosedViewTests(unittest.TestCase):
    """Closing a document freed its view's scene graph under the effect."""

    def setUp(self) -> None:
        coin = types.SimpleNamespace(SoNodeSensor=Sensor)
        self.saved = sys.modules.get("pivy")
        sys.modules["pivy"] = types.SimpleNamespace(  # type: ignore
            coin=coin)
        self.effect = ao.AmbientOcclusion()
        self.state = ao.ViewState(object(), self.effect)
        self.state.show = lambda: None  # type: ignore[method-assign]
        self.root, self.parent = Node(), Node()
        self.prepass = Node()
        self.frame = mock.patch.object(ao_pipeline, "FramePass", Frame)
        self.frame.start()
        self.state.place(ao_pipeline.Effect(self.prepass, self.root),
                         self.parent)

    def tearDown(self) -> None:
        self.frame.stop()
        if self.saved is not None:
            sys.modules["pivy"] = self.saved
        else:
            sys.modules.pop("pivy", None)

    def test_prepass_comes_first_composite_last(self) -> None:
        self.parent.children[1:1] = [Node()]   # the selection root
        self.assertIs(self.parent.children[0], self.state.frame.node)
        self.assertIs(self.parent.children[-1], self.root)
        self.assertIs(self.state.frame.prepass, self.prepass)

    def test_live_view_gets_its_group_back(self) -> None:
        self.state.release(view_alive=True)
        self.assertEqual(self.parent.children, [])
        self.assertEqual(self.root.refs, 0)
        self.assertIsNone(self.state.frame.prepass)

    def test_closed_view_is_not_touched(self) -> None:
        self.parent.freed = True
        self.effect.views[1] = self.state
        ao._views = lambda: []  # type: ignore[assignment]
        self.effect.sync()
        self.assertEqual(self.effect.views, {})
        self.assertEqual(self.root.refs, 0)
        self.assertFalse(self.state.sensor.attached)


class CullingTests(unittest.TestCase):

    def test_pass_separators_never_cull(self) -> None:
        class Separator:
            OFF = "off"

            def __init__(self) -> None:
                self.renderCulling = "auto"

        coin = types.SimpleNamespace(SoSeparator=Separator)
        with mock.patch.dict(sys.modules, {
                "pivy": types.SimpleNamespace(coin=coin)}):
            separator = ao_pipeline.Builder().separator()
        self.assertEqual(separator.renderCulling, Separator.OFF)

    def test_pass_quads_reach_around_any_view(self) -> None:
        points: list[Any] = []

        class Field:
            def setValues(self, _start: int, _count: int,  # noqa: N802
                          values: list[Any]) -> None:
                points.extend(values)

            def setValue(self, _value: Any) -> None:  # noqa: N802
                pass

        class Node:
            def __init__(self) -> None:
                self.point = self.numVertices = Field()

            def addChild(self, _child: Any) -> None:  # noqa: N802
                pass

        coin = types.SimpleNamespace(SoCoordinate3=Node, SoFaceSet=Node,
                                     SoGroup=Node)
        with mock.patch.dict(sys.modules, {
                "pivy": types.SimpleNamespace(coin=coin)}):
            ao_pipeline.Builder().quad()
        reach = ao_pipeline.QUAD_REACH
        for axis in range(3):
            self.assertEqual({p[axis] for p in points}, {-reach, reach})


class ShaderTests(unittest.TestCase):

    def test_occlusion_shader_is_filled_in(self) -> None:
        shader = ao_pipeline.GTAO_FRAGMENT % {
            "dirs": 2, "steps": 3, "max_radius": "0.2", "power": "1.5",
            "edge_on": "%r, %r" % ao_pipeline.EDGE_ON_FADE}
        self.assertIn("smoothstep(0.05, 0.25, dot(n, V))", shader)
        self.assertNotIn("%(", shader)


class PyOpenGLTests(unittest.TestCase):

    def test_error_checking_is_off_before_gl_loads(self) -> None:
        fake = types.ModuleType("OpenGL")
        fake.ERROR_CHECKING = True  # type: ignore[attr-defined]
        fake.ERROR_LOGGING = True  # type: ignore[attr-defined]
        with mock.patch.dict(sys.modules, {"OpenGL": fake}):
            pyopengl._configure()
        self.assertFalse(fake.ERROR_CHECKING)  # type: ignore[attr-defined]
        self.assertFalse(fake.ERROR_LOGGING)  # type: ignore[attr-defined]


class LineTests(unittest.TestCase):

    def test_widths_follow_freecad(self) -> None:
        STORE.update(DefaultShapeLineWidth=4, DefaultShapePointSize=6)
        try:
            line, point = ao_lines.widths()
        finally:
            STORE.clear()
        self.assertEqual((line, point),
                         (4.0 + ao_lines.MARGIN_PX,
                          6.0 + ao_lines.MARGIN_PX))


if __name__ == "__main__":
    unittest.main()
