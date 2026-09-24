"""Nxt model panel: a timeline view of a FreeCAD document.

See DESIGN.md in this directory for the paradigm and its rules.

Layering (each module depends only on the ones above it):

    scene      pure snapshot of the document. No Qt.
    icons      QQuickImageProvider serving ViewObject icons.
    models     the QAbstractListModel of rows over a snapshot.
    bridge     QObject exposing commands to QML; owns the models.
    observers  FreeCAD document/selection observers -> bridge invalidation.
    panel      QDockWidget + QQuickWidget host, engine wiring.
"""

from __future__ import annotations

__all__ = ["scene", "icons", "models", "bridge", "observers", "panel"]
