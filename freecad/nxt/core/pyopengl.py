"""Raw OpenGL through PyOpenGL, for callbacks drawing inside Coin's frame.

PyOpenGL is optional (package.xml): the features using it ask
`missing()` first and fall back without it. OpenGL 1.1 needs no
PyOpenGL; see opengl.py.

Coin keeps its own idea of the GL state, so a callback that draws must
leave the state as it found it: `preserved_state` restores what
`glPushAttrib` does not cover (framebuffers, program, active texture unit).
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import Any

import FreeCAD as App

#: A full-screen quad in clip space.
QUAD = ((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0))
#: Errors other code left behind are cleared, or our checks would trip.
STALE_ERRORS = 16
REQUIRED = ("OpenGL.GL", "numpy")

_reported: set[str] = set()


def _configure() -> None:
    """Turn off PyOpenGL's checks, before its GL module is first loaded.

    By default PyOpenGL calls glGetError after every GL call: a driver
    round trip that can stall the GPU, on every call of every frame.
    `check` tests for errors where it matters. Loaded first by other
    code, PyOpenGL keeps that code's choice.
    """
    import OpenGL
    OpenGL.ERROR_CHECKING = False
    OpenGL.ERROR_LOGGING = False


def load() -> Any:
    """PyOpenGL's GL module; ImportError where it is missing."""
    _configure()
    from OpenGL import GL
    return GL


def missing() -> str | None:
    """Why raw GL cannot run here, or None if it can."""
    with contextlib.suppress(ImportError):
        _configure()
    for package in REQUIRED:
        try:
            __import__(package)
        except ImportError as exc:
            return "%s: %s" % (package, exc)
    return None


def warn_once(key: str, message: str) -> None:
    """One line in the Report view per key and session."""
    if key not in _reported:
        _reported.add(key)
        App.Console.PrintWarning("Nxt: %s\n" % message)


def clear_errors(gl: Any) -> None:
    for _ in range(STALE_ERRORS):
        if gl.glGetError() == gl.GL_NO_ERROR:
            return


def check(gl: Any, step: str) -> None:
    """RuntimeError if the GL calls of `step` left an error."""
    error = gl.glGetError()
    if error != gl.GL_NO_ERROR:
        raise RuntimeError("%s failed, GL error 0x%x" % (step, error))


def program(gl: Any, vertex: str, fragment: str) -> int:
    """A linked GLSL program; RuntimeError with the log if it fails."""
    def shader(kind: int, source: str) -> int:
        handle = gl.glCreateShader(kind)
        gl.glShaderSource(handle, source)
        gl.glCompileShader(handle)
        if not gl.glGetShaderiv(handle, gl.GL_COMPILE_STATUS):
            raise RuntimeError(gl.glGetShaderInfoLog(handle))
        return int(handle)

    handle = gl.glCreateProgram()
    gl.glAttachShader(handle, shader(gl.GL_VERTEX_SHADER, vertex))
    gl.glAttachShader(handle, shader(gl.GL_FRAGMENT_SHADER, fragment))
    gl.glLinkProgram(handle)
    if not gl.glGetProgramiv(handle, gl.GL_LINK_STATUS):
        raise RuntimeError(gl.glGetProgramInfoLog(handle))
    return int(handle)


def nearest_texture(gl: Any) -> int:
    """A new clamped texture with nearest filtering, left bound."""
    texture = int(gl.glGenTextures(1))
    gl.glBindTexture(gl.GL_TEXTURE_2D, texture)
    for name, value in ((gl.GL_TEXTURE_MIN_FILTER, gl.GL_NEAREST),
                        (gl.GL_TEXTURE_MAG_FILTER, gl.GL_NEAREST),
                        (gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE),
                        (gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)):
        gl.glTexParameteri(gl.GL_TEXTURE_2D, name, value)
    return texture


def color_target(gl: Any, texture: int) -> int:
    """A framebuffer drawing into `texture`; RuntimeError if unusable."""
    framebuffer = int(gl.glGenFramebuffers(1))
    attach(gl, framebuffer, texture)
    return framebuffer


def attach(gl: Any, framebuffer: int, texture: int) -> None:
    """Make `texture` the colour target of `framebuffer`, left bound."""
    gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, framebuffer)
    gl.glFramebufferTexture2D(gl.GL_FRAMEBUFFER, gl.GL_COLOR_ATTACHMENT0,
                              gl.GL_TEXTURE_2D, texture, 0)
    if (gl.glCheckFramebufferStatus(gl.GL_FRAMEBUFFER)
            != gl.GL_FRAMEBUFFER_COMPLETE):
        raise RuntimeError("framebuffer incomplete")


def draw_quad(gl: Any) -> None:
    """The full-screen quad, with the current program."""
    gl.glBegin(gl.GL_QUADS)
    for x, y in QUAD:
        gl.glVertex2f(x, y)
    gl.glEnd()


def plain_drawing(gl: Any, width: int, height: int) -> None:
    """Viewport and state for a full-screen pass of `width` x `height`."""
    gl.glViewport(0, 0, width, height)
    for capability in (gl.GL_DEPTH_TEST, gl.GL_BLEND, gl.GL_CULL_FACE,
                       gl.GL_SCISSOR_TEST, gl.GL_STENCIL_TEST):
        gl.glDisable(capability)
    gl.glDepthMask(gl.GL_FALSE)
    gl.glColorMask(True, True, True, True)


def bound(gl: Any, unit: int) -> int:
    """The texture bound on `unit`, leaving the active unit as it was."""
    active = int(gl.glGetIntegerv(gl.GL_ACTIVE_TEXTURE))
    gl.glActiveTexture(gl.GL_TEXTURE0 + unit)
    texture = int(gl.glGetIntegerv(gl.GL_TEXTURE_BINDING_2D))
    gl.glActiveTexture(active)
    return texture


def bind(gl: Any, unit: int, texture: int) -> None:
    """Bind `texture` on `unit`, leaving the active unit as it was."""
    active = int(gl.glGetIntegerv(gl.GL_ACTIVE_TEXTURE))
    gl.glActiveTexture(gl.GL_TEXTURE0 + unit)
    gl.glBindTexture(gl.GL_TEXTURE_2D, texture)
    gl.glActiveTexture(active)


@contextlib.contextmanager
def preserved_state(gl: Any) -> Iterator[None]:
    """Everything drawn inside is undone from Coin's point of view."""
    draw = int(gl.glGetIntegerv(gl.GL_DRAW_FRAMEBUFFER_BINDING))
    read = int(gl.glGetIntegerv(gl.GL_READ_FRAMEBUFFER_BINDING))
    current = int(gl.glGetIntegerv(gl.GL_CURRENT_PROGRAM))
    active = int(gl.glGetIntegerv(gl.GL_ACTIVE_TEXTURE))
    gl.glPushAttrib(gl.GL_ALL_ATTRIB_BITS)
    try:
        yield
    finally:
        gl.glBindFramebuffer(gl.GL_DRAW_FRAMEBUFFER, draw)
        gl.glBindFramebuffer(gl.GL_READ_FRAMEBUFFER, read)
        gl.glUseProgram(current)
        gl.glPopAttrib()
        gl.glActiveTexture(active)


def matrices(gl: Any) -> tuple[Any, Any]:
    """Modelview and projection as GL holds them (column-major)."""
    import numpy
    view = numpy.array(gl.glGetFloatv(gl.GL_MODELVIEW_MATRIX),
                       dtype=numpy.float32).reshape(4, 4)
    projection = numpy.array(gl.glGetFloatv(gl.GL_PROJECTION_MATRIX),
                             dtype=numpy.float32).reshape(4, 4)
    return view, projection
