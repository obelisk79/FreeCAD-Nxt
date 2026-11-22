"""The Coin node trees of the ambient occlusion: depth to composite.

Four passes, built from stock Coin nodes, after Intel's XeGTAO layout of
ground truth AO (Jimenez et al. 2016):

1. depth: eye depth and facet normal per pixel of the solid model,
   drawn into a float texture; transparent shapes and lines are left
   out;
2. occlusion: horizons searched along a few slices per pixel, the visible
   arc between them integrated exactly;
3. blur: depth-aware 4x4 at AO resolution, averaging away the 4x4
   interleaved noise of the occlusion pass;
4. composite: depth-aware upsample, blended black over the picture,
   after the temporal filter (ao_temporal.py) where it runs; the model's
   lines and points (ao_lines.py), drawn into a mask of their own, are
   left undarkened.

Two trees, so that nothing of the passes leaks into the view's drawing:

- the "prepass" holds the scene textures. A callback at the start of the
  view's frame (FramePass) draws it with a render action of its own, so
  paths queued for later (annotations) replay in that action, and GL
  state is restored after it;
- the composite is an ordinary node right after the view's selection
  root: it binds the textures, already up to date, and blends one quad.
  It runs in the opaque part of the view's frame, so transparent objects,
  FreeCAD's on-top selection, annotations and draggers come after it and
  stay clear of the effect.

Each pass re-renders only when its scene notifies a change, so a still
view costs only the composite. A switch holds a cheap Interactive level
for while the camera moves.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..core import opengl

ROOT_NAME = "NxtAmbientOcclusion"
PREPASS_NAME = ROOT_NAME + "Prepass"
#: On/off, flipped while the camera moves when the AO pauses then.
SWITCH_NAME = ROOT_NAME + "Switch"
#: Child 0 is the chosen quality, child 1 the Interactive level.
LEVEL_NAME = ROOT_NAME + "Level"
INFO_NAME = ROOT_NAME + "Info"

#: Quality -> (slices, steps per side, depth scale, AO scale); each AO
#: pixel reads 2 * slices * steps depths.
QUALITY = {
    "interactive": (2, 3, 0.5, 0.5),
    "low": (2, 4, 1.0, 0.5),
    "medium": (3, 4, 1.0, 1.0),
    "high": (4, 6, 1.0, 1.0),
}
#: The same per frame where temporal accumulation runs: the slices turn
#: each frame and the history adds them up, so one or two slices a frame
#: give the look of four or more once settled.
TEMPORAL_QUALITY = {
    "interactive": (1, 3, 0.5, 0.5),
    "low": (1, 3, 1.0, 0.5),
    "medium": (1, 4, 1.0, 1.0),
    "high": (2, 4, 1.0, 1.0),
}
INTERACTIVE = "interactive"
#: Largest sampling disc, as a fraction of the view: a smaller one
#: shrinks a zoomed-in part's radius to a thin line along its contacts.
MAX_SCREEN_RADIUS = 0.2
#: Visibility ** (intensity * POWER): deepens creases, open faces stay 1.
POWER = 1.5
#: Facing (cosine between the surface normal and the view) below which
#: the effect fades out: seen edge-on, a facet's horizons are unreliable,
#: and the blur cannot average across the silhouette, so the occlusion's
#: noise would show as dots along curved outlines.
EDGE_ON_FADE = (0.05, 0.25)
#: Scene texture sizes are 16 bit.
MAX_TEXTURE = 8192
MIN_TEXTURE = 8
#: How far out the passes' quads reach in every direction, in model
#: units: Coin culls a shape whose bounds miss the view, so the quad's
#: bounds must hold any view (kilometres, in millimetres).
QUAD_REACH = 1e9
#: Half the material's opacity: there only to make Coin enable blending.
BLEND_TRANSPARENCY = 0.5
#: Opacity below which a shape counts as transparent, and stays out of
#: the depth pass: datum and origin planes, transparent objects.
OPAQUE_ALPHA = 0.99
GL_ALL_ATTRIB_BITS = 0x000FFFFF
GL_MODELVIEW = 0x1700
GL_PROJECTION = 0x1701
#: How much nearer than the face under it a picked edge or vertex may be
#: and still count as seen, as a fraction of the radius: an edge lies on
#: its faces, a hidden one far behind the face in front.
MASK_TOLERANCE_OF_RADIUS = 0.05


@dataclass(frozen=True)
class Look:
    """What the effect looks like; a new one means a rebuild."""

    quality: str
    intensity: float
    radius: float
    temporal: bool
    #: FreeCAD's line width and point size, plus a margin, in pixels.
    line_px: float = 2.0
    point_px: float = 2.0


DEPTH_VERTEX = """#version 120
varying vec3 dt_eye;
varying float dt_alpha;
void main() {
    vec4 eye = gl_ModelViewMatrix * gl_Vertex;
    dt_eye = eye.xyz;
    dt_alpha = gl_Color.a;          // Coin's diffuse colour and opacity
    gl_ClipVertex = eye;            // keep FreeCAD"s clipping planes
    gl_Position = ftransform();
}
"""

# The facet normal, not the smooth vertex normal: only it agrees with the
# depth samples, and the mismatch shows as stripes along the facets.
MASK_FRAGMENT = """#version 120
varying vec3 dt_eye;
void main() {
    gl_FragColor = vec4(-dt_eye.z, 0.0, 0.0, 1.0);
}
"""

DEPTH_FRAGMENT = """#version 120
varying vec3 dt_eye;
varying float dt_alpha;
void main() {
    if (dt_alpha < %(opaque)s) discard;
    vec3 n = normalize(cross(dFdx(dt_eye), dFdy(dt_eye)));
    if (n.z < 0.0) n = -n;
    gl_FragColor = vec4(-dt_eye.z, n);  // a zero normal: background
}
"""

# The quad's corners may lie far out (see Builder.quad): only their signs
# place it, over the whole viewport.
QUAD_VERTEX = """#version 120
varying vec2 dt_uv;
void main() {
    vec2 corner = sign(gl_Vertex.xy);
    dt_uv = corner * 0.5 + 0.5;
    gl_Position = vec4(corner, 0.0, 1.0);
}
"""

# Samples snap to texel centres, which moves them off their slice; on a
# sloped face such a point sits above the true horizon and fakes
# occlusion, so each offset is projected back into the slice plane.
GTAO_FRAGMENT = """#version 120
#define DT_DIRS %(dirs)d
#define DT_STEPS %(steps)d
#define DT_PI 3.14159265
#define DT_HALF_PI 1.57079633
#define P00 gl_ProjectionMatrix[0][0]
#define P11 gl_ProjectionMatrix[1][1]
#define P20 gl_ProjectionMatrix[2][0]
#define P21 gl_ProjectionMatrix[2][1]
#define P23 gl_ProjectionMatrix[2][3]
#define P30 gl_ProjectionMatrix[3][0]
#define P31 gl_ProjectionMatrix[3][1]
#define P33 gl_ProjectionMatrix[3][3]
uniform sampler2D dt_depthTex;
uniform vec2 dt_texel;
uniform vec2 dt_size;
uniform float dt_radius;
uniform float dt_intensity;
uniform float dt_frame;
varying vec2 dt_uv;

vec3 eyePos(vec2 uv, float d) {
    float ze = -d;
    float wc = P23 * ze + P33;
    vec2 ndc = uv * 2.0 - 1.0;
    return vec3((ndc.x * wc - P20 * ze - P30) / P00,
                (ndc.y * wc - P21 * ze - P31) / P11, ze);
}

vec2 snap(vec2 uv) { return (floor(uv * dt_size + 0.01) + 0.5) * dt_texel; }

float horizon(vec2 uv, vec2 dir, vec3 C, vec3 V, vec3 axis,
              float invR2, float jitter, float minT) {
    float best = -1.0;
    for (int j = 0; j < DT_STEPS; j++) {
        float t = (float(j) + jitter) / float(DT_STEPS);
        t = minT + (1.0 - minT) * t * t;
        vec2 quv = snap(uv + dir * t);
        vec4 q = texture2D(dt_depthTex, quv);
        vec3 S = eyePos(quv, q.r) - C;
        S -= axis * dot(S, axis);
        float ll = dot(S, S);
        if (dot(q.gba, q.gba) < 0.5 || ll < 1e-12) continue;
        float c = dot(S, V) * inversesqrt(ll);
        float w = clamp(1.0 - ll * invR2, 0.0, 1.0);
        best = max(best, mix(-1.0, c, w));
    }
    return best;
}

void main() {
    vec2 cuv = snap(dt_uv);
    vec4 c = texture2D(dt_depthTex, cuv);
    if (dot(c.gba, c.gba) < 0.5) {
        gl_FragColor = vec4(1.0, 0.0, 0.0, 1.0);
        return;
    }
    vec3 C = eyePos(cuv, c.r);
    vec3 n = c.gba;
    vec3 V = (P33 > 0.5) ? vec3(0.0, 0.0, 1.0) : normalize(-C);
    if (dot(n, V) < 0.0) n = -n;

    float wc = P23 * C.z + P33;
    vec2 ruv = dt_radius * 0.5 * vec2(P00, P11) / max(wc, 1e-6);
    float scale = min(1.0, %(max_radius)s / max(ruv.x, ruv.y));
    ruv *= scale;
    if (max(ruv.x * dt_size.x, ruv.y * dt_size.y) < 1.5) {
        gl_FragColor = vec4(1.0, c.r, 1.0, 1.0);
        return;
    }
    float R = dt_radius * scale;
    float invR2 = 1.0 / (R * R);

    vec2 cell = mod(floor(gl_FragCoord.xy), 4.0);
    float n1 = fract(mod((cell.x * 4.0 + cell.y) * 7.0, 16.0) / 16.0
                     + dt_frame * 0.618034);
    float n2 = fract(mod((cell.y * 4.0 + cell.x) * 5.0 + 3.0, 16.0) / 16.0
                     + dt_frame * 0.381966);
    // the whole step, or the gaps between steps show as bands
    float jitter = n2;

    float vis = 0.0;
    for (int i = 0; i < DT_DIRS; i++) {
        float phi = (float(i) + n1) * DT_PI / float(DT_DIRS);
        vec2 omega = vec2(cos(phi), sin(phi));
        vec3 dir = vec3(omega, 0.0);
        vec3 orthoDir = dir - dot(dir, V) * V;
        vec3 axis = normalize(cross(orthoDir, V));
        vec3 projN = n - axis * dot(n, axis);
        float projLen = length(projN);
        float cosN = clamp(dot(projN, V) / max(projLen, 1e-6), 0.0, 1.0);
        float nAng = sign(dot(orthoDir, projN)) * acos(cosN);

        vec2 stepUV = omega * ruv;
        float minT = clamp(1.0 / length(stepUV * dt_size), 0.0, 0.5);
        float hc0 = horizon(dt_uv, stepUV, C, V, axis, invR2, jitter, minT);
        float hc1 = horizon(dt_uv, -stepUV, C, V, axis, invR2, jitter, minT);
        float h0 = -acos(clamp(hc1, -1.0, 1.0));
        float h1 = acos(clamp(hc0, -1.0, 1.0));
        h0 = nAng + max(h0 - nAng, -DT_HALF_PI);
        h1 = nAng + min(h1 - nAng, DT_HALF_PI);
        float sinN = sin(nAng);
        float arc0 = (cosN + 2.0 * h0 * sinN - cos(2.0 * h0 - nAng)) * 0.25;
        float arc1 = (cosN + 2.0 * h1 * sinN - cos(2.0 * h1 - nAng)) * 0.25;
        vis += projLen * (arc0 + arc1);
    }
    vis = clamp(vis / float(DT_DIRS), 0.0, 1.0);
    vis = mix(1.0, vis, smoothstep(%(edge_on)s, dot(n, V)));
    float visibility = pow(vis, max(dt_intensity, 0.0) * %(power)s);
    gl_FragColor = vec4(visibility, c.r, 1.0, 1.0);
}
"""

BLUR_FRAGMENT = """#version 120
uniform sampler2D dt_aoTex;
uniform vec2 dt_aoTexel;
uniform float dt_radius;
varying vec2 dt_uv;

void main() {
    vec4 c = texture2D(dt_aoTex, dt_uv);
    if (c.b < 0.5) { gl_FragColor = vec4(1.0, 0.0, 0.0, 1.0); return; }
    float inv = 1.0 / dt_radius;
    float sum = 0.0;
    float weight = 0.0;
    for (int x = -2; x < 2; x++) {
        for (int y = -2; y < 2; y++) {
            vec2 uv = clamp(dt_uv + vec2(float(x), float(y)) * dt_aoTexel,
                            0.5 * dt_aoTexel, 1.0 - 0.5 * dt_aoTexel);
            vec4 s = texture2D(dt_aoTex, uv);
            float w = step(0.5, s.b)
                      * max(0.0, 1.0 - abs(s.g - c.g) * inv) + 1e-4;
            sum += w * s.r;
            weight += w;
        }
    }
    gl_FragColor = vec4(sum / weight, c.g, 1.0, 1.0);
}
"""

COMPOSITE_FRAGMENT = """#version 120
uniform sampler2D dt_aoTex;
uniform sampler2D dt_depthTex;
uniform sampler2D dt_maskTex;  // the model's lines: a = 1, r = depth
uniform vec2 dt_aoSize;
uniform vec2 dt_depthSize;
uniform vec2 dt_maskSize;
uniform float dt_radius;
uniform float dt_maskTolerance;
uniform float dt_maskBlend;    // tent spacing, in mask texels
varying vec2 dt_uv;

// 1 where a seen line or point covers the mask texel at `uv`
float line(vec2 uv, float z) {
    vec4 m = texture2D(dt_maskTex, uv);
    return step(0.5, m.a) * step(m.r, z + dt_maskTolerance);
}

void main() {
    vec2 duv = (floor(dt_uv * dt_depthSize) + 0.5) / dt_depthSize;
    vec4 d = texture2D(dt_depthTex, duv);
    if (dot(d.gba, d.gba) < 0.5) discard;
    float z = d.r;
    // a 3x3 tent over the mask (centre 1/4, sides 1/8, corners 1/16):
    // a soft edge in place of a hard, aliased one, which left jaggies
    // and a rim of unshaded face beside antialiased lines
    vec2 muv = (floor(dt_uv * dt_maskSize) + 0.5) / dt_maskSize;
    vec2 mt = 1.0 / dt_maskSize;
    float covered = 0.0;
    for (int x = -1; x <= 1; x++) {
        for (int y = -1; y <= 1; y++) {
            float w = (2.0 - abs(float(x))) * (2.0 - abs(float(y))) / 16.0;
            covered += w * line(muv + vec2(float(x), float(y)) * mt
                                    * dt_maskBlend, z);
        }
    }
    if (covered > 0.99) discard;
    vec2 p = dt_uv * dt_aoSize - 0.5;
    vec2 base = floor(p);
    vec2 f = p - base;
    vec2 half_texel = 0.5 / dt_aoSize;
    float inv = 1.0 / dt_radius;
    float sum = 0.0;
    float weight = 0.0;
    for (int x = 0; x < 2; x++) {
        for (int y = 0; y < 2; y++) {
            vec2 o = vec2(float(x), float(y));
            vec2 uv = clamp((base + o + 0.5) / dt_aoSize,
                            half_texel, 1.0 - half_texel);
            vec4 s = texture2D(dt_aoTex, uv);
            vec2 b = mix(1.0 - f, f, o);
            float depth_w = step(0.5, s.b)
                            * max(0.0, 1.0 - abs(s.g - z) * inv) + 1e-3;
            float w = b.x * b.y * depth_w;
            sum += w * s.r;
            weight += w;
        }
    }
    // dithered by under one 8-bit step: smooth shading without bands
    float dither = fract(52.9829189 * fract(dot(gl_FragCoord.xy,
                                               vec2(0.06711056,
                                                    0.00583715))));
    float darkness = (1.0 - sum / max(weight, 1e-6)) * (1.0 - covered);
    gl_FragColor = vec4(0.0, 0.0, 0.0,
                        clamp(darkness + (dither - 0.5) / 255.0, 0.0, 1.0));
}
"""


def texture_size(width: int, height: int, scale: float) -> tuple[int, int]:
    """A pass's texture size for a view of `width` x `height` pixels."""
    shrink = min(1.0, MAX_TEXTURE / max(width, height, 1)) * scale
    return (max(int(width * shrink), MIN_TEXTURE),
            max(int(height * shrink), MIN_TEXTURE))


def signature(width: int, height: int, camera: int, scene: int,
              mask: int, look: Look) -> str:
    """Everything the node tree depends on: a new one, a rebuild."""
    return "%dx%d|%x|%x|%x|%s" % (width, height, camera, scene, mask,
                                  look)


def current_signature(root: Any) -> str | None:
    """The signature the effect under `root` was built with."""
    info = find(root, INFO_NAME)
    return info.string.getValue().getString() if info is not None else None


def find(group: Any, name: str) -> Any:
    """The direct child of `group` named `name`, or None."""
    for i in range(group.getNumChildren()):
        child = group.getChild(i)
        if child.getName().getString() == name:
            return child
    return None


class Builder:
    """Makes the nodes; pivy is imported only once one is needed."""

    def __init__(self) -> None:
        from pivy import coin
        self.coin = coin

    def program(self, vertex: str, fragment: str,
                parameters: list[Any]) -> Any:
        coin = self.coin
        vs = coin.SoVertexShader()
        vs.sourceType = coin.SoShaderObject.GLSL_PROGRAM
        vs.sourceProgram = vertex
        fs = coin.SoFragmentShader()
        fs.sourceType = coin.SoShaderObject.GLSL_PROGRAM
        fs.sourceProgram = fragment
        for i, parameter in enumerate(parameters):
            fs.parameter.set1Value(i, parameter)
        program = coin.SoShaderProgram()
        program.shaderObject.set1Value(0, vs)
        program.shaderObject.set1Value(1, fs)
        return program

    def scalar(self, name: str, value: float) -> Any:
        parameter = self.coin.SoShaderParameter1f()
        parameter.name = name
        parameter.value = value
        return parameter

    def vec2(self, name: str, x: float, y: float) -> Any:
        parameter = self.coin.SoShaderParameter2f()
        parameter.name = name
        parameter.value = self.coin.SbVec2f(x, y)
        return parameter

    def sampler(self, name: str, unit: int) -> Any:
        parameter = self.coin.SoShaderParameter1i()
        parameter.name = name
        parameter.value = unit
        return parameter

    def quad(self, reach: float = QUAD_REACH) -> Any:
        """The full-screen quad of a pass, `reach` out from the origin.

        Its shader places it; Coin culls it by its bounds, which a quad
        reaching QUAD_REACH out on every axis keeps around any view.
        """
        coin = self.coin
        coords = coin.SoCoordinate3()
        coords.point.setValues(0, 4, [
            (-reach, -reach, -reach), (reach, -reach, -reach),
            (reach, reach, reach), (-reach, reach, reach)])
        face = coin.SoFaceSet()
        face.numVertices.setValue(4)
        return self.group(coin.SoGroup(), coords, face)

    def framed_quad(self) -> Any:
        """The composite's quad, framed by a camera of its own.

        It is drawn in the view's scene, where a far-reaching quad would
        stretch "fit all"; a unit quad under the view's camera was culled
        with the origin out of view. This camera always sees it.
        """
        coin = self.coin
        camera = coin.SoOrthographicCamera()
        camera.viewportMapping = coin.SoCamera.LEAVE_ALONE
        camera.position = (0, 0, 1)
        camera.height = 2.0
        camera.aspectRatio = 1.0
        camera.nearDistance = 0.5
        camera.farDistance = 1.5
        return self.group(coin.SoGroup(), camera, self.quad(reach=1.0))

    def separator(self) -> Any:
        """A separator Coin never culls.

        The passes' full-screen quads are placed by their shaders, but
        Coin culls by their coordinates: a square at the world origin.
        With the origin out of view (a building far from it, zoomed in)
        a culling separator dropped the whole pass: no AO at all.
        """
        separator = self.coin.SoSeparator()
        separator.renderCulling = self.coin.SoSeparator.OFF
        return separator

    @staticmethod
    def group(group: Any, *children: Any) -> Any:
        for child in children:
            group.addChild(child)
        return group

    def depth_test(self, enabled: bool) -> Any:
        """Depth test and write switch.

        A scene texture renders (and clears) its buffers with the depth
        settings in force where it sits: with writing off, its depth
        buffer is never cleared. So the "off" node of a quad always
        follows the texture nodes that quad reads.
        """
        node = self.coin.SoDepthBuffer()
        node.test = enabled
        node.write = enabled
        return node

    def overriding(self, node: Any) -> Any:
        node.setOverride(True)
        return node

    def texture(self, width: int, height: int, kind: Any,
                scene: Any) -> Any:
        coin = self.coin
        texture = coin.SoSceneTexture2()
        texture.size = coin.SbVec2s(width, height)
        texture.type = kind
        texture.backgroundColor = coin.SbVec4f(0, 0, 0, 0)
        texture.transparencyFunction = coin.SoSceneTexture2.NONE
        texture.wrapS = coin.SoSceneTexture2.CLAMP
        texture.wrapT = coin.SoSceneTexture2.CLAMP
        texture.scene = scene
        return texture

    def unit(self, index: int) -> Any:
        unit = self.coin.SoTextureUnit()
        unit.unit = index
        return unit

    def depth_pass(self, size: tuple[int, int], camera: Any,
                   scene: Any) -> Any:
        coin = self.coin
        lines = coin.SoDrawStyle()      # edges stay out of the occlusion
        lines.linePattern = 0
        for name in ("style", "pointSize", "lineWidth"):
            lines.getField(name).setIgnored(True)
        # drawn in place, never queued for later, and with their opacity
        # for the shader to leave them out
        blend = coin.SoTransparencyType()
        blend.value = coin.SoTransparencyType.BLEND
        # off then on: SoAnnotation turns depth testing off behind Coin's
        # back, and only a change of value makes Coin turn it on again
        depth_scene = self.group(
            self.separator(), self.depth_test(False),
            self.depth_test(True), self.overriding(blend), camera,
            self.overriding(lines),
            self.program(DEPTH_VERTEX, DEPTH_FRAGMENT
                         % {"opaque": repr(OPAQUE_ALPHA)}, []), scene)
        return self.texture(*size, coin.SoSceneTexture2.RGBA32F,
                            depth_scene)

    def mask_state(self, look: Look) -> list[Any]:
        """The draw style and shader the model's lines are masked with."""
        coin = self.coin
        widths = coin.SoDrawStyle()
        widths.lineWidth = look.line_px
        widths.pointSize = look.point_px
        widths.linePattern = 0xFFFF
        widths.style.setIgnored(True)
        flat = coin.SoLightModel()
        flat.model = coin.SoLightModel.BASE_COLOR
        return [self.overriding(widths), flat,
                self.program(DEPTH_VERTEX, MASK_FRAGMENT, [])]

    def mask_pass(self, size: tuple[int, int], lines: Any, camera: Any,
                  scene: Any) -> Any:
        """The model's lines and points, as eye depths, at full size.

        `lines` is the node that draws them (ao_lines.LineMask). It
        draws them from a root of its own, so a change of the camera or
        the model would not reach this texture, which would keep the
        lines where they were: white ghosts of edges while orbiting. So
        both are traversed here too, the model drawn invisible, only to
        pass their changes on. (A switch showing no child would not do:
        Coin's SoSwitch drops notifications from children it hides.)
        """
        coin = self.coin
        invisible = coin.SoDrawStyle()
        invisible.style = coin.SoDrawStyle.INVISIBLE
        for name in ("pointSize", "lineWidth", "linePattern"):
            invisible.getField(name).setIgnored(True)
        watch = self.group(self.separator(), camera,
                           self.overriding(invisible), scene)
        mask_scene = self.group(
            self.separator(), watch,
            self.depth_test(False), self.depth_test(True), lines)
        return self.texture(*size, self.coin.SoSceneTexture2.RGBA32F,
                            mask_scene)

    def composite_body(self) -> Any:
        coin = self.coin
        pick = coin.SoPickStyle()
        pick.style = coin.SoPickStyle.UNPICKABLE
        light_model = coin.SoLightModel()
        light_model.model = coin.SoLightModel.BASE_COLOR
        style = coin.SoDrawStyle()
        style.style = coin.SoDrawStyle.FILLED
        blend = coin.SoTransparencyType()
        blend.value = coin.SoTransparencyType.BLEND
        material = coin.SoMaterial()
        material.diffuseColor = (0, 0, 0)
        material.transparency = BLEND_TRANSPARENCY
        body = coin.SoSkipBoundingGroup() if hasattr(
            coin, "SoSkipBoundingGroup") else coin.SoGroup()
        return self.group(body, pick, light_model, style, blend, material)


@dataclass(frozen=True)
class Effect:
    """The two node trees of the effect: see the module's docstring."""

    #: Drawn by FramePass at the start of the view's frame.
    prepass: Any
    #: Placed right after the view's selection root.
    composite: Any


def _pipeline(make: Builder, width: int, height: int, camera: Any,
              scene: Any, mask_key: tuple[Any, ...], look: Look,
              level: str, resources: Any) -> tuple[Any, Any]:
    """The passes of one quality level: (prepass, composite)."""
    # Full floats throughout: (visibility, eye depth) in half floats kept
    # depth to about three digits, and the depth-aware blur, upsample and
    # history then weighed neighbours unevenly: grainy shading, worse on
    # some GPUs than others.
    float_rgba = make.coin.SoSceneTexture2.RGBA32F
    budget = TEMPORAL_QUALITY if look.temporal else QUALITY
    dirs, steps, depth_scale, ao_scale = budget[level]
    depth_size = texture_size(width, height, depth_scale)
    ao_size = texture_size(width, height, ao_scale)
    dw, dh = depth_size
    aw, ah = ao_size

    depth_tex = make.depth_pass(depth_size, camera, scene)

    frame = make.scalar("dt_frame", 0.0)
    occlusion = GTAO_FRAGMENT % {"dirs": dirs, "steps": steps,
                                 "max_radius": repr(MAX_SCREEN_RADIUS),
                                 "power": repr(POWER),
                                 "edge_on": "%r, %r" % EDGE_ON_FADE}
    ao_scene = make.group(
        make.separator(), camera, make.unit(0), depth_tex,
        make.depth_test(False),
        make.program(QUAD_VERTEX, occlusion,
                     [make.sampler("dt_depthTex", 0),
                      make.vec2("dt_texel", 1.0 / dw, 1.0 / dh),
                      make.vec2("dt_size", dw, dh),
                      make.scalar("dt_radius", look.radius),
                      make.scalar("dt_intensity", look.intensity),
                      frame]),
        make.quad())
    ao_tex = make.texture(aw, ah, float_rgba, ao_scene)

    blur_scene = make.group(
        make.separator(), make.unit(0), ao_tex, make.depth_test(False),
        make.program(QUAD_VERTEX, BLUR_FRAGMENT,
                     [make.sampler("dt_aoTex", 0),
                      make.vec2("dt_aoTexel", 1.0 / aw, 1.0 / ah),
                      make.scalar("dt_radius", look.radius)]),
        make.quad())
    blur_tex = make.texture(aw, ah, float_rgba, blur_scene)

    mask_size = texture_size(width, height, 1.0)
    blend = make.scalar("dt_maskBlend", resources.edge_blend)
    resources.blends.append(blend)
    lines = resources.lines.follow(
        mask_key, mask_size,
        lambda: [camera, *make.mask_state(look), scene])
    mask_tex = make.mask_pass(mask_size, lines, camera, scene)

    # each texture renders here if its scene changed; the composite then
    # finds them up to date and only binds them
    prepass = make.group(make.separator(), depth_tex, ao_tex, blur_tex,
                         mask_tex)

    body = make.composite_body()
    make.group(body, make.unit(2), mask_tex, make.unit(1), depth_tex,
               make.unit(0), blur_tex)
    accumulator = resources.accumulator(level) if look.temporal else None
    if accumulator is not None:
        body.addChild(accumulator.attach(aw, ah, frame, look.radius))
    composite = make.group(
        body, make.depth_test(False),
        make.program(QUAD_VERTEX, COMPOSITE_FRAGMENT,
                     [make.sampler("dt_aoTex", 0),
                      make.sampler("dt_depthTex", 1),
                      make.sampler("dt_maskTex", 2),
                      make.vec2("dt_aoSize", aw, ah),
                      make.vec2("dt_depthSize", dw, dh),
                      make.vec2("dt_maskSize", *mask_size),
                      make.scalar("dt_radius", look.radius),
                      make.scalar("dt_maskTolerance",
                                  MASK_TOLERANCE_OF_RADIUS * look.radius),
                      blend]),
        make.framed_quad())
    return prepass, composite


def _levels(make: Builder, root: Any, signed: str) -> Any:
    """Give `root` the info, on/off switch and level switch; the latter."""
    coin = make.coin
    info = coin.SoInfo()
    info.setName(INFO_NAME)
    info.string = signed
    switch = coin.SoSwitch()
    switch.setName(SWITCH_NAME)
    switch.whichChild = coin.SO_SWITCH_ALL
    levels = coin.SoSwitch()
    levels.setName(LEVEL_NAME)
    levels.whichChild = 0
    make.group(root, info, make.group(switch, levels))
    return levels


def build(width: int, height: int, camera: Any, scene: Any,
          mask_key: tuple[Any, ...], look: Look, resources: Any,
          signed: str) -> Effect:
    """The effect's two node trees.

    `mask_key` changes when the model's lines must be searched again;
    `resources` lends each level its GL helpers (ViewResources).
    """
    make = Builder()
    coin = make.coin
    resources.blends.clear()
    # Inside an annotation, the passes render while Coin replays delayed
    # paths: an annotation in the model then draws in place, into the
    # texture, instead of queueing a path for after the prepass.
    prepass = coin.SoAnnotation()
    prepass.setName(PREPASS_NAME)
    composite = make.separator()
    composite.setName(ROOT_NAME)
    for root in (prepass, composite):
        root.renderCulling = coin.SoSeparator.OFF
        root.pickCulling = coin.SoSeparator.OFF
    early = _levels(make, prepass, signed)
    late = _levels(make, composite, signed)
    chosen = _pipeline(make, width, height, camera, scene, mask_key, look,
                       look.quality, resources)
    reduced = chosen if look.quality == INTERACTIVE else _pipeline(
        make, width, height, camera, scene, mask_key, look, INTERACTIVE,
        resources)
    for passes in (chosen, reduced):
        early.addChild(passes[0])
        late.addChild(passes[1])
    return Effect(prepass, composite)


class FramePass:
    """The node that draws a view's prepass at the start of its frame.

    It sits first in the view's scene graph and draws the prepass with
    a render action of its own, sharing the view's GL cache context, so
    the textures' GL objects are the ones the composite binds later in
    the frame. GL attributes and matrices are restored after it.
    """

    def __init__(self) -> None:
        from pivy import coin
        self.prepass: Any = None
        self.action: Any = None
        self.node = coin.SoCallback()
        self.node.setCallback(self._render, None)

    def show(self, prepass: Any) -> None:
        """Draw `prepass` from the next frame on; None draws nothing."""
        if self.prepass is not None:
            self.prepass.unref()
        self.prepass = prepass
        if prepass is not None:
            prepass.ref()

    def _render(self, data: Any, action: Any) -> None:
        from pivy import coin
        render = coin.SoGLRenderAction.getClassTypeId()
        if self.prepass is None or not action.isOfType(render):
            return
        # pivy hands callbacks the base SoAction wrapper
        action = coin.cast(action, "SoGLRenderAction")
        region = action.getViewportRegion()
        if self.action is None:
            self.action = coin.SoGLRenderAction(region)
        else:
            self.action.setViewportRegion(region)
        self.action.setCacheContext(action.getCacheContext())
        gl = opengl.library()
        gl.glPushAttrib(GL_ALL_ATTRIB_BITS)
        for mode in (GL_PROJECTION, GL_MODELVIEW):
            gl.glMatrixMode(mode)
            gl.glPushMatrix()
        try:
            self.action.apply(self.prepass)
        finally:
            for mode in (GL_PROJECTION, GL_MODELVIEW):
                gl.glMatrixMode(mode)
                gl.glPopMatrix()
            gl.glPopAttrib()
