"""Find which step of building the context menu takes FreeCAD down.

A crash in FreeCAD's C++ leaves no Python traceback, so this writes each
step to a log file - flushed to disk before the step runs - and the last
line in the file is the step that crashed:

    from freecad.nxt.menus import diagnose; diagnose.run()

The log is `nxt-diagnose.log` in the addon's folder.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

LOG = Path(__file__).resolve().parents[3] / "nxt-diagnose.log"


def run() -> None:
    """Build the selection's menu step by step, logging before each."""
    with LOG.open("w", encoding="utf-8") as log:

        def step(text: str) -> None:
            log.write(text + "\n")
            log.flush()
            os.fsync(log.fileno())

        from ..tree import panel
        from . import facts, loaded, runner
        from .definitions import resolve

        step("selection")
        doc = App.ActiveDocument
        objects = Gui.Selection.getSelection(doc.Name)
        step("  %s" % [o.Name for o in objects])
        bridge = panel.bridge()
        nodes = bridge._snapshot.nodes if bridge is not None else {}

        for obj in objects:
            step("type chain of %s (%s)" % (obj.Name, obj.TypeId))
            from FreeCAD import Base
            kind = Base.TypeId.fromName(obj.TypeId)
            for _ in range(40):
                step("  getParent of %s" % kind.Name)
                kind = kind.getParent()
                step("  isBad")
                if kind.isBad():
                    break
            step("facts.of %s" % obj.Name)
            _facts_steps(obj, step)
            facts.of(obj, nodes.get(obj.Name), nodes)

        step("resolve")
        selection = [facts.of(o, nodes.get(o.Name), nodes) for o in objects]
        menu = resolve(loaded(), selection)
        for name in menu.commands():
            if ":" in name:
                continue
            step("command %s: get" % name)
            command = runner._command(name)
            if command is None:
                step("  not registered")
                continue
            step("  getInfo")
            command.getInfo()
            step("  getAction")
            built = bool(command.getAction())
            step("  isActive" if built else "  no action yet; not asked")
            runner.is_active(command)
        step("done")
    App.Console.PrintMessage("Nxt: menu built without a crash; see %s\n"
                             % LOG)


def _facts_steps(obj: Any, step: Any) -> None:
    for label, test in (
            ("ExpressionEngine", lambda: obj.ExpressionEngine),
            ("getPropertyStatus Placement",
             lambda: obj.getPropertyStatus("Placement")),
            ("Suppressed", lambda: hasattr(obj, "Suppressed")),
            ("Shape", lambda: hasattr(obj, "Shape")),
            ("ViewObject.Visibility", lambda: obj.ViewObject.Visibility),
            ("getInEdit", lambda: Gui.getDocument(obj.Document.Name)
             .getInEdit()),
            ("hasExtension", lambda: obj.hasExtension(
                "Part::AttachExtension")),
            ("getParentGeoFeatureGroup",
             lambda: obj.getParentGeoFeatureGroup()),
            ("Proxy", lambda: getattr(obj, "Proxy", None))):
        step("  %s" % label)
        try:
            test()
        except Exception as exc:
            step("    raised %s" % exc)
