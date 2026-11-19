"""The 3D view's own depth buffer as the AO depth (setting: AODepthReuse).

Without it, the effect draws the whole model a second time only to learn
each pixel's depth: on a heavy model, most of its cost. The view has
drawn that depth already, so a callback at the start of the composite
(the end-of-frame annotation phase, after the scene) blits the depth
attachment being drawn, multisampled or not, into a depth texture of the
same format, and converts it to what the AO shaders read: r = eye depth,
gba = eye normal rebuilt from the neighbours (zero on the background).

Unlike the separate pass, everything in the depth buffer counts: edges,
drawn just in front of their faces, and transparent objects that write
depth. A GL failure sets `failed`; the effect is then rebuilt with the
separate depth pass.
"""

from __future__ import annotations

import contextlib
from typing import Any

from ..core import pyopengl

failed = False
UNIFORMS = ("dt_src", "dt_srcSize", "dt_proj")
#: Depth formats by bit count, when the buffer has no stencil.
DEPTH_FORMATS = {16: "GL_DEPTH_COMPONENT16", 24: "GL_DEPTH_COMPONENT24",
                 32: "GL_DEPTH_COMPONENT32"}

VERTEX = """#version 120
varying vec2 dt_uv;
void main() {
    dt_uv = gl_Vertex.xy * 0.5 + 0.5;
    gl_Position = vec4(gl_Vertex.xy, 0.0, 1.0);
}
"""

FRAGMENT = """#version 120
uniform sampler2D dt_src;    // the copied depth buffer, window depth
uniform vec2 dt_srcSize;
uniform mat4 dt_proj;
varying vec2 dt_uv;

bool hit(vec2 uv) { return texture2D(dt_src, uv).r < 1.0; }

float eyeDepth(vec2 uv) {
    float z = texture2D(dt_src, uv).r * 2.0 - 1.0;
    return -(dt_proj[3][2] - z * dt_proj[3][3])
           / (z * dt_proj[2][3] - dt_proj[2][2]);
}

vec3 eyePos(vec2 uv, float d) {
    float ze = -d;
    float wc = dt_proj[2][3] * ze + dt_proj[3][3];
    vec2 ndc = uv * 2.0 - 1.0;
    return vec3(
        (ndc.x * wc - dt_proj[2][0] * ze - dt_proj[3][0]) / dt_proj[0][0],
        (ndc.y * wc - dt_proj[2][1] * ze - dt_proj[3][1]) / dt_proj[1][1],
        ze);
}

void main() {
    vec2 texel = 1.0 / dt_srcSize;
    vec2 uv = (floor(dt_uv * dt_srcSize) + 0.5) * texel;
    if (!hit(uv)) { gl_FragColor = vec4(0.0); return; }
    vec3 C = eyePos(uv, eyeDepth(uv));

    // on each axis the side with the smaller depth step: silhouettes
    // must not bend the normal
    vec2 ul = uv - vec2(texel.x, 0.0), ur = uv + vec2(texel.x, 0.0);
    vec2 ud = uv - vec2(0.0, texel.y), uu = uv + vec2(0.0, texel.y);
    vec3 L = eyePos(ul, eyeDepth(ul)), R = eyePos(ur, eyeDepth(ur));
    vec3 D = eyePos(ud, eyeDepth(ud)), U = eyePos(uu, eyeDepth(uu));
    bool right = hit(ur)
                 && (!hit(ul) || abs(R.z - C.z) < abs(C.z - L.z));
    bool up = hit(uu) && (!hit(ud) || abs(U.z - C.z) < abs(C.z - D.z));
    vec3 n = normalize(cross(right ? R - C : C - L, up ? U - C : C - D));
    if (n.z < 0.0) n = -n;
    gl_FragColor = vec4(-C.z, n);
}
"""


def available() -> bool:
    """Whether depth reuse can run here (says why not, once)."""
    reason = ("disabled after a GL error" if failed
              else pyopengl.missing())
    if reason is not None:
        pyopengl.warn_once("ao-depth",
                           "AO depth reuse unavailable (%s)" % reason)
    return reason is None


def _source_format(gl: Any, framebuffer: int) -> int:
    """The internal format of the depth of `framebuffer`.

    A depth blit needs the same format on both sides.
    """
    default = framebuffer == 0
    depth = gl.GL_DEPTH if default else gl.GL_DEPTH_ATTACHMENT
    stencil = gl.GL_STENCIL if default else gl.GL_STENCIL_ATTACHMENT
    gl.glBindFramebuffer(gl.GL_READ_FRAMEBUFFER, framebuffer)

    def attachment(point: int, name: int) -> int:
        return int(gl.glGetFramebufferAttachmentParameteriv(
            gl.GL_READ_FRAMEBUFFER, point, name))

    bits = attachment(depth, gl.GL_FRAMEBUFFER_ATTACHMENT_DEPTH_SIZE)
    kind = attachment(depth, gl.GL_FRAMEBUFFER_ATTACHMENT_COMPONENT_TYPE)
    has_stencil = False
    # some drivers make asking about a missing attachment a GL error
    with contextlib.suppress(Exception):
        has_stencil = attachment(
            stencil, gl.GL_FRAMEBUFFER_ATTACHMENT_STENCIL_SIZE) > 0
    if kind == gl.GL_FLOAT:
        return int(gl.GL_DEPTH32F_STENCIL8 if has_stencil
                   else gl.GL_DEPTH_COMPONENT32F)
    if has_stencil:
        return int(gl.GL_DEPTH24_STENCIL8)
    return int(getattr(gl, DEPTH_FORMATS.get(bits, DEPTH_FORMATS[24])))


class DepthSource:
    """The depth of one view and quality level, copied every frame.

    Lives with its view, across rebuilds of the effect: its GL objects
    belong to the view's context and are reused, not leaked.
    """

    def __init__(self) -> None:
        from pivy import coin
        self.width = 0                # of the converted texture
        self.height = 0
        self.output = 0
        self.output_fbo = 0
        self.output_size = (0, 0)
        self.source = 0
        self.source_fbo = 0
        self.source_key = (0, 0, 0)
        self.program = 0
        self.locations: dict[str, int] = {}
        self.valid = False            # output holds this frame's depth
        self.copy_node = coin.SoCallback()
        self.copy_node.setCallback(self._copy, None)

    def resize(self, width: int, height: int) -> None:
        """Serve a newly built pipeline of `width` x `height`."""
        self.width, self.height = width, height
        self.valid = False

    def bind_node(self, unit: int) -> Any:
        """A node binding the converted depth to texture `unit`."""
        from pivy import coin
        node = coin.SoCallback()
        node.setCallback(self._bind, unit)
        return node

    def _allocate(self, gl: Any) -> None:
        if not self.program:
            self.program = pyopengl.program(gl, VERTEX, FRAGMENT)
            self.locations = {
                name: gl.glGetUniformLocation(self.program, name)
                for name in UNIFORMS}
            self.output = pyopengl.nearest_texture(gl)
            self.output_fbo = int(gl.glGenFramebuffers(1))
            self.source = pyopengl.nearest_texture(gl)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_COMPARE_MODE,
                               gl.GL_NONE)
            self.source_fbo = int(gl.glGenFramebuffers(1))
        gl.glBindTexture(gl.GL_TEXTURE_2D, self.output)
        gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA32F, self.width,
                        self.height, 0, gl.GL_RGBA, gl.GL_FLOAT, None)
        pyopengl.attach(gl, self.output_fbo, self.output)
        self.output_size = (self.width, self.height)

    def _resize_source(self, gl: Any, width: int, height: int,
                       internal: int) -> None:
        # the raw entry point: PyOpenGL's array converter knows no packed
        # depth-stencil type and rejects a null data pointer
        from OpenGL.raw.GL.VERSION.GL_1_0 import glTexImage2D
        packed = {gl.GL_DEPTH24_STENCIL8: gl.GL_UNSIGNED_INT_24_8,
                  gl.GL_DEPTH32F_STENCIL8:
                      gl.GL_FLOAT_32_UNSIGNED_INT_24_8_REV}
        kind = packed.get(internal, gl.GL_FLOAT)
        fmt = (gl.GL_DEPTH_STENCIL if internal in packed
               else gl.GL_DEPTH_COMPONENT)
        point = (gl.GL_DEPTH_STENCIL_ATTACHMENT if internal in packed
                 else gl.GL_DEPTH_ATTACHMENT)
        gl.glBindTexture(gl.GL_TEXTURE_2D, self.source)
        glTexImage2D(gl.GL_TEXTURE_2D, 0, internal, width, height, 0, fmt,
                     kind, None)
        gl.glBindFramebuffer(gl.GL_DRAW_FRAMEBUFFER, self.source_fbo)
        gl.glFramebufferTexture2D(gl.GL_DRAW_FRAMEBUFFER, point,
                                  gl.GL_TEXTURE_2D, self.source, 0)
        gl.glDrawBuffer(gl.GL_NONE)
        gl.glReadBuffer(gl.GL_NONE)
        if (gl.glCheckFramebufferStatus(gl.GL_DRAW_FRAMEBUFFER)
                != gl.GL_FRAMEBUFFER_COMPLETE):
            raise RuntimeError("depth copy framebuffer incomplete")
        self.source_key = (width, height, internal)

    def _convert(self, gl: Any, drawn: int, viewport: list[int],
                 projection: Any) -> None:
        x, y, width, height = viewport
        if self.output_size != (self.width, self.height):
            self._allocate(gl)
        internal = _source_format(gl, drawn)
        if self.source_key != (width, height, internal):
            self._resize_source(gl, width, height, internal)
        gl.glBindFramebuffer(gl.GL_READ_FRAMEBUFFER, drawn)
        gl.glBindFramebuffer(gl.GL_DRAW_FRAMEBUFFER, self.source_fbo)
        gl.glDisable(gl.GL_SCISSOR_TEST)
        gl.glBlitFramebuffer(x, y, x + width, y + height, 0, 0, width,
                             height, gl.GL_DEPTH_BUFFER_BIT, gl.GL_NEAREST)
        pyopengl.check(gl, "depth blit")

        gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, self.output_fbo)
        pyopengl.plain_drawing(gl, self.width, self.height)
        gl.glUseProgram(self.program)
        gl.glActiveTexture(gl.GL_TEXTURE0)
        gl.glBindTexture(gl.GL_TEXTURE_2D, self.source)
        gl.glUniform1i(self.locations["dt_src"], 0)
        gl.glUniform2f(self.locations["dt_srcSize"], width, height)
        gl.glUniformMatrix4fv(self.locations["dt_proj"], 1, gl.GL_FALSE,
                              projection)
        pyopengl.draw_quad(gl)
        pyopengl.check(gl, "depth convert")

    def _copy(self, data: Any, action: Any) -> None:
        global failed
        from pivy import coin
        render = coin.SoGLRenderAction.getClassTypeId()
        if failed or not self.width or not action.isOfType(render):
            return
        gl = pyopengl.load()
        pyopengl.clear_errors(gl)
        drawn = int(gl.glGetIntegerv(gl.GL_DRAW_FRAMEBUFFER_BINDING))
        viewport = [int(v) for v in gl.glGetIntegerv(gl.GL_VIEWPORT)]
        _, projection = pyopengl.matrices(gl)
        try:
            with pyopengl.preserved_state(gl):
                self._convert(gl, drawn, viewport, projection)
            self.valid = True
        except Exception as exc:  # noqa: BLE001 - called from Coin's render
            failed = True
            self.valid = False
            pyopengl.warn_once("ao-depth-gl",
                               "AO depth reuse disabled (%s)" % exc)

    def _bind(self, unit: int, action: Any) -> None:
        from pivy import coin
        render = coin.SoGLRenderAction.getClassTypeId()
        if self.valid and action.isOfType(render):
            pyopengl.bind(pyopengl.load(), unit, self.output)
