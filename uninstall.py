"""Run by FreeCAD's Addon Manager when Nxt is uninstalled, if allowed.

Puts back the drag-handle preferences Nxt changed on its first run
(freecad/nxt/tree/gizmos.py). Without it, Nxt does the same at the quit
after the uninstall.
"""

try:
    from freecad.nxt.tree import gizmos
    gizmos.restore_freecads()
except Exception as exc:
    import FreeCAD
    FreeCAD.Console.PrintError(
        "Nxt: could not restore the drag settings: %s\n" % exc)
