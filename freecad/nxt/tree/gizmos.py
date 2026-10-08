"""FreeCAD's 3D drag handles ("gizmos"): how dragging them steps.

FreeCAD 26.3's arrows for Pad, Pocket and the like step in fixed
increments. What decides the steps is a handful of FreeCAD preferences
that FreeCAD itself does not put on any page; found with probe.draggers()
and confirmed by trying them:

  Gui/Gizmos/DefaultCoarseDragBehavior   what a plain drag does:
                                         1 fine steps, 0 coarse steps
  Gui/Gizmos/FineSnapModifier            the key that swaps to the other
                                         (a Qt modifier; despite the
                                         name, it toggles either way)
  Gui/Gizmos/EnableCoarseSnap            whether coarse steps exist
  Gui/Gizmos/CoarseLinearSnapMultiplier  coarse step = this x fine step
  Gui/Gizmos/CoarseRotationSnapMultiplier  the same for rotation handles
  History/Dragger/LastTranslationIncrement  the fine step, in mm; kept
                                         with FreeCAD's dialog history,
                                         so another tool may change it

FreeCAD's default is coarse (5 mm) on a plain drag and Shift for fine,
the reverse of most desktop software. Nxt's default is fine on a plain
drag and Ctrl for coarse steps, set once on the first run and the user's
to change from then on. Changes apply to the next drag; nothing needs
reopening.

What those two were before is kept, and put back when Nxt is
uninstalled (uninstall.py, run by the Addon Manager) or, at the quit
after it is disabled or removed, by Nxt itself - unless the user has
changed them since, which makes them the user's.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import FreeCAD as App

from . import settings

GIZMOS = "User parameter:BaseApp/Preferences/Gui/Gizmos"
HISTORY = "User parameter:BaseApp/History/Dragger"
#: "Show interactive draggers while editing features", in GIZMOS.
ENABLED = "EnableGizmos"

#: Qt::KeyboardModifier values, as FineSnapModifier stores them.
SHIFT = 0x02000000
CTRL = 0x04000000
ALT = 0x08000000
KEYS = {"shift": SHIFT, "ctrl": CTRL, "alt": ALT}

#: FreeCAD's value for DefaultCoarseDragBehavior.
FINE_FIRST = 1
COARSE_FIRST = 0

#: What Nxt's defaults set the two preferences they change to.
OURS = {"DefaultCoarseDragBehavior": FINE_FIRST, "FineSnapModifier": CTRL}

#: Files the Addon Manager leaves in an addon's folder: one there means
#: it is disabled at the next start; the other gone, that it is removed.
DISABLED = "ADDON_DISABLED"
MANIFEST = "package.xml"

#: Nxt's defaults: fine on a plain drag, Ctrl for coarse steps.
DEFAULTS: dict[str, Any] = {
    "plain": "fine",
    "key": "ctrl",
    "coarse": True,
    "step": 1.0,
    "linear": 5,
    "rotation": 5,
}


def read() -> dict[str, Any]:
    """The current settings, in Nxt's terms."""
    gizmos = App.ParamGet(GIZMOS)
    history = App.ParamGet(HISTORY)
    modifier = gizmos.GetInt("FineSnapModifier", SHIFT)
    key = next((k for k, v in KEYS.items() if v == modifier), "shift")
    first = gizmos.GetInt("DefaultCoarseDragBehavior", COARSE_FIRST)
    return {
        "plain": "fine" if first == FINE_FIRST else "coarse",
        "key": key,
        "coarse": gizmos.GetBool("EnableCoarseSnap", True),
        "step": history.GetFloat("LastTranslationIncrement", 1.0),
        "linear": gizmos.GetInt("CoarseLinearSnapMultiplier", 5),
        "rotation": gizmos.GetInt("CoarseRotationSnapMultiplier", 5),
    }


def write(values: dict[str, Any]) -> None:
    """Store settings given in Nxt's terms; missing keys are left alone."""
    gizmos = App.ParamGet(GIZMOS)
    if "plain" in values:
        gizmos.SetInt("DefaultCoarseDragBehavior",
                      FINE_FIRST if values["plain"] == "fine"
                      else COARSE_FIRST)
    if "key" in values and values["key"] in KEYS:
        gizmos.SetInt("FineSnapModifier", KEYS[values["key"]])
    if "coarse" in values:
        gizmos.SetBool("EnableCoarseSnap", bool(values["coarse"]))
    if "linear" in values:
        gizmos.SetInt("CoarseLinearSnapMultiplier",
                      max(1, int(values["linear"])))
    if "rotation" in values:
        gizmos.SetInt("CoarseRotationSnapMultiplier",
                      max(1, int(values["rotation"])))
    if "step" in values:
        App.ParamGet(HISTORY).SetFloat(
            "LastTranslationIncrement", max(0.001, float(values["step"])))


@contextlib.contextmanager
def hidden() -> Iterator[None]:
    """Open an edit without its drag handles.

    FreeCAD decides whether a task gets handles when the task is made,
    from FreeCAD's own preference. So the preference is turned off
    for just that moment and put back at once: the edit opened inside
    has none, and a feature created afterwards has them as usual. Left
    alone when the user has them off already.
    """
    group = App.ParamGet(GIZMOS)
    was_on = bool(group.GetBool(ENABLED, True))
    if was_on:
        group.SetBool(ENABLED, False)
    try:
        yield
    finally:
        if was_on:
            group.SetBool(ENABLED, True)


def apply_defaults_once() -> bool:
    """Set Nxt's defaults the first time Nxt runs. True if it did.

    Only the plain-drag behaviour and the key: the step sizes are left as
    FreeCAD has them. Never again after the first run, so a user who
    prefers FreeCAD's way keeps it. What they were is kept, for
    restore_freecads.
    """
    if settings.get("GizmoDefaultsApplied"):
        return False
    try:
        group = App.ParamGet(GIZMOS)
        present = set(group.GetInts())
        settings.put("GizmoOriginals", json.dumps({
            name: group.GetInt(name, 0) if name in present else None
            for name in OURS}))
        for name, value in OURS.items():
            group.SetInt(name, value)
    except Exception:
        App.Console.PrintError("Nxt: could not set the drag defaults\n")
        return False
    settings.put("GizmoDefaultsApplied", True)
    return True


def restore_freecads() -> bool:
    """Put back what Nxt's defaults replaced. True if they had been set.

    Only where Nxt's value is still there: one changed since is the
    user's choice and stays. A preference that was not set before is
    unset again, so FreeCAD's own default applies. Nxt's defaults are
    set afresh if it runs again.
    """
    if not settings.get("GizmoDefaultsApplied"):
        return False
    try:
        originals = json.loads(settings.get("GizmoOriginals") or "{}")
    except ValueError:
        originals = {}
    group = App.ParamGet(GIZMOS)
    present = set(group.GetInts())
    for name, value in OURS.items():
        if name not in present or group.GetInt(name, 0) != value:
            continue
        before = originals.get(name)
        if before is None:
            group.RemInt(name)
        else:
            group.SetInt(name, int(before))
    settings.put("GizmoOriginals", "")
    settings.put("GizmoDefaultsApplied", False)
    return True


def restore_if_leaving(root: Path) -> bool:
    """At quit: restore_freecads if Nxt will not run at the next start.

    `root` is Nxt's folder. Disabling and uninstalling both take effect
    at the next start, when nothing of Nxt runs to put things back.
    """
    if (root / DISABLED).exists() or not (root / MANIFEST).exists():
        return restore_freecads()
    return False
