"""Temporal accumulation of the ambient occlusion (setting: AOTemporal).

A temporal filter reads its own output of the previous frame. Two Coin
scene textures reading each other would make the scene graph a cycle,
which Coin does not support, so an SoCallback does it in raw GL right
after Coin binds the blurred AO (r = visibility, g = eye depth) to unit 0:
each texel is reprojected into the previous frame with the camera
matrices Coin used, blended with the history where the depths agree, and
the result is bound to unit 0 for the composite to read.

After each frame a one-shot sensor bumps the occlusion shader's
`dt_frame`, so the next one searches other slices: while the camera
moves, the history adds them up (the per-frame budget is small, see
ao_pipeline.TEMPORAL_QUALITY); once it stops, only the AO passes
re-render, with new noise, until STILL_FRAMES frames have refined it.
"""

from __future__ import annotations

from typing import Any

from ..core import pyopengl

#: Frames of history while the camera moves: more is smoother but lags.
MOVING_MAX = 4.0
#: Frames of history once the camera stops.
STILL_MAX = 24.0
#: Extra frames rendered, for refinement, after the camera stops.
STILL_FRAMES = 24
#: Depth mismatch, as a fraction of the AO radius, that rejects the
#: history at a pixel. The radius follows the model's size; the depth
#: itself does not (an orthographic camera may sit inside the model).
TOLERANCE_OF_RADIUS = 0.1
#: How close two camera matrices must be to count as "not moving".
MATRIX_RTOL = 1e-6
MATRIX_ATOL = 1e-7
UNIFORMS = ("dt_cur", "dt_hist", "dt_invView", "dt_prevView",
            "dt_prevProj", "dt_proj", "dt_maxCount", "dt_tolerance")

VERTEX = """#version 120
varying vec2 dt_uv;
void main() {
    dt_uv = gl_Vertex.xy * 0.5 + 0.5;
    gl_Position = vec4(gl_Vertex.xy, 0.0, 1.0);
}
"""

FRAGMENT = """#version 120
uniform sampler2D dt_cur;    // r = visibility, g = eye depth, b = model
uniform sampler2D dt_hist;   // r, g as above, b = frames (0: background)
uniform mat4 dt_invView;     // current eye -> world
uniform mat4 dt_prevView;    // world -> previous eye
uniform mat4 dt_prevProj;
uniform mat4 dt_proj;
uniform float dt_maxCount;
uniform float dt_tolerance;  // model units
varying vec2 dt_uv;

void main() {
    vec4 c = texture2D(dt_cur, dt_uv);
    if (c.b < 0.5) { gl_FragColor = vec4(1.0, 0.0, 0.0, 1.0); return; }

    float ze = -c.g;
    float wc = dt_proj[2][3] * ze + dt_proj[3][3];
    vec2 ndc = dt_uv * 2.0 - 1.0;
    vec3 eye = vec3(
        (ndc.x * wc - dt_proj[2][0] * ze - dt_proj[3][0]) / dt_proj[0][0],
        (ndc.y * wc - dt_proj[2][1] * ze - dt_proj[3][1]) / dt_proj[1][1],
        ze);

    vec4 pe = dt_prevView * (dt_invView * vec4(eye, 1.0));
    vec4 pc = dt_prevProj * pe;
    vec2 puv = pc.xy / pc.w * 0.5 + 0.5;

    float count = 1.0;
    float vis = c.r;
    if (all(greaterThan(puv, vec2(0.0))) && all(lessThan(puv, vec2(1.0)))) {
        vec4 h = texture2D(dt_hist, puv);
        if (h.b > 0.5 && abs(h.g + pe.z) < dt_tolerance) {
            count = min(h.b + 1.0, dt_maxCount);
            vis = mix(h.r, c.r, 1.0 / count);
        }
    }
    gl_FragColor = vec4(vis, c.g, count, 1.0);
}
"""


#: Set by a GL failure: the effect is rebuilt without the filter, at the
#: full per-frame budget its few slices a frame relied on.
failed = False


def available() -> bool:
    """Whether the filter can run here (says why not, once)."""
    reason = ("disabled after a GL error" if failed
              else pyopengl.missing())
    if reason is not None:
        pyopengl.warn_once("ao-temporal",
                           "AO temporal accumulation unavailable (%s)"
                           % reason)
    return reason is None


class Accumulator:
    """The temporal filter of one view and quality level.

    Lives with its view, across rebuilds of the effect: its GL objects
    belong to the view's context and are reused, not leaked.
    """

    def __init__(self) -> None:
        from pivy import coin
        self.width = 0
        self.height = 0
        self.frame: Any = None        # the occlusion shader's dt_frame
        self.tolerance = 0.0
        self.disabled = False
        self.textures: list[int] = []
        self.fbo = 0
        self.program = 0
        self.locations: dict[str, int] = {}
        self.index = 0
        self.previous: tuple[Any, Any] | None = None
        self.still = 0
        self.sensor = coin.SoOneShotSensor(self._next_frame, None)
        self.node = coin.SoCallback()
        self.node.setCallback(self._render, None)

    def attach(self, width: int, height: int, frame: Any,
               radius: float) -> Any:
        """Serve a newly built pipeline; the node to place in it."""
        self.tolerance = TOLERANCE_OF_RADIUS * radius
        if (width, height) != (self.width, self.height):
            self.width, self.height = width, height
            self.previous = None
            self.still = 0
        if self.frame is not None:
            self.frame.unref()
        self.frame = frame
        frame.ref()
        return self.node

    def release(self) -> None:
        """Let go of the scene graph; GL objects go with the context."""
        self.sensor.unschedule()
        if self.frame is not None:
            self.frame.unref()
            self.frame = None

    def _next_frame(self, data: Any, sensor: Any) -> None:
        if self.frame is not None:
            self.frame.value = self.frame.value.getValue() + 1.0

    def _allocate(self, gl: Any) -> None:
        if not self.program:
            self.program = pyopengl.program(gl, VERTEX, FRAGMENT)
            self.locations = {
                name: gl.glGetUniformLocation(self.program, name)
                for name in UNIFORMS}
            self.textures = [pyopengl.nearest_texture(gl) for _ in range(2)]
            self.fbo = int(gl.glGenFramebuffers(1))
        gl.glClearColor(0.0, 0.0, 0.0, 0.0)   # an empty history: 0 frames
        for texture in self.textures:
            gl.glBindTexture(gl.GL_TEXTURE_2D, texture)
            gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA16F, self.width,
                            self.height, 0, gl.GL_RGBA, gl.GL_FLOAT, None)
            pyopengl.attach(gl, self.fbo, texture)
            gl.glClear(gl.GL_COLOR_BUFFER_BIT)
        self.allocated = (self.width, self.height)

    def _accumulate(self, gl: Any, current: int, view: Any,
                    projection: Any, moving: bool) -> int:
        """Blend this frame into the history; the texture it went to."""
        import numpy
        if getattr(self, "allocated", None) != (self.width, self.height):
            self._allocate(gl)
        target = self.textures[self.index]
        previous_view, previous_projection = (self.previous
                                              or (view, projection))
        pyopengl.attach(gl, self.fbo, target)
        pyopengl.plain_drawing(gl, self.width, self.height)
        gl.glUseProgram(self.program)
        gl.glActiveTexture(gl.GL_TEXTURE0)
        gl.glBindTexture(gl.GL_TEXTURE_2D, current)
        gl.glActiveTexture(gl.GL_TEXTURE1)
        gl.glBindTexture(gl.GL_TEXTURE_2D, self.textures[1 - self.index])
        at = self.locations
        gl.glUniform1i(at["dt_cur"], 0)
        gl.glUniform1i(at["dt_hist"], 1)
        # GL keeps M column-major, as M.T: inverse(M).T is inverse(M.T)
        gl.glUniformMatrix4fv(at["dt_invView"], 1, gl.GL_FALSE,
                              numpy.linalg.inv(view).astype(numpy.float32))
        gl.glUniformMatrix4fv(at["dt_prevView"], 1, gl.GL_FALSE,
                              previous_view)
        gl.glUniformMatrix4fv(at["dt_prevProj"], 1, gl.GL_FALSE,
                              previous_projection)
        gl.glUniformMatrix4fv(at["dt_proj"], 1, gl.GL_FALSE, projection)
        gl.glUniform1f(at["dt_maxCount"],
                       MOVING_MAX if moving else STILL_MAX)
        gl.glUniform1f(at["dt_tolerance"], self.tolerance)
        pyopengl.draw_quad(gl)
        return target

    def _moved(self, view: Any, projection: Any) -> bool:
        import numpy
        if self.previous is None:
            return True
        return not all(
            numpy.allclose(now, before, rtol=MATRIX_RTOL, atol=MATRIX_ATOL)
            for now, before in zip((view, projection), self.previous))

    def _render(self, data: Any, action: Any) -> None:
        global failed
        from pivy import coin
        render = coin.SoGLRenderAction.getClassTypeId()
        if self.disabled or self.frame is None or not action.isOfType(
                render):
            return
        gl = pyopengl.load()
        pyopengl.clear_errors(gl)
        current = pyopengl.bound(gl, 0)
        if current == 0:
            return
        view, projection = pyopengl.matrices(gl)
        moving = self._moved(view, projection)
        try:
            with pyopengl.preserved_state(gl):
                result = self._accumulate(gl, current, view, projection,
                                          moving)
        except Exception as exc:  # noqa: BLE001 - called from Coin's render
            failed = True
            self.disabled = True
            pyopengl.warn_once("ao-temporal-gl",
                               "AO temporal accumulation disabled (%s)"
                               % exc)
            return
        pyopengl.bind(gl, 0, result)
        self.index = 1 - self.index
        self.previous = (view, projection)
        if moving:
            self.still = 0
            self.sensor.schedule()
        elif self.still < STILL_FRAMES:
            self.still += 1
            self.sensor.schedule()
