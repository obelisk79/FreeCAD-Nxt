"""A link field led by its type (Pad's Up to face) keeps the type's choice.

Run with: python3 tests/test_link_lead_qml.py
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import fakes  # noqa: E402
from PySide6 import QtCore, QtGui, QtQuick  # noqa: E402

fakes.install()

from freecad.nxt.ui.theme import Theme  # noqa: E402

QML = ROOT / "freecad" / "nxt" / "resources" / "qml"
TYPES = ["Length", "UpToFace", "UpToShape"]
LABELS = ["Dimension", "Up to face", "Up to shape"]
HOST = """
import QtQuick
import Nxt.Controls
Item {
    width: 300; height: 60
    property var spec: ({ kind: "link", chips: [] })
    ValueEditor {
        width: parent.width
        spec: parent.spec
        labelled: false
        editsLinks: true
    }
}
"""


def lead_box(spec: dict[str, Any], name: str = "linkLead") -> Any:
    view = QtQuick.QQuickView()
    view.engine().addImportPath(str(QML))
    view.rootContext().setContextProperty("theme", THEME)
    host = ROOT / "tests" / "_lead_host.qml"
    host.write_text(HOST, encoding="utf-8")
    view.setSource(QtCore.QUrl.fromLocalFile(str(host)))
    host.unlink()
    VIEWS.append(view)
    root = view.rootObject()
    root.setProperty("spec", spec)
    APP.processEvents()
    return root.findChild(QtCore.QObject, name)


APP = QtGui.QGuiApplication.instance() or QtGui.QGuiApplication(sys.argv)
THEME = Theme()
VIEWS: list[Any] = []


class LinkLeadTests(unittest.TestCase):
    def spec(self, lead: bool) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": "link", "name": "UpToFace",
                               "chips": []}
        if lead:
            out["lead"] = {"kind": "enum", "name": "Type",
                           "text": "UpToFace", "options": TYPES,
                           "optionLabels": LABELS}
        return out

    def test_the_type_stays_beside_the_link(self) -> None:
        box = lead_box(self.spec(lead=True))
        self.assertTrue(box.property("visible"))
        self.assertEqual(box.property("text"), "Up to face")

    def test_no_lead_no_box(self) -> None:
        box = lead_box(self.spec(lead=False))
        self.assertFalse(box.property("visible"))


class InviteTests(unittest.TestCase):
    def invite(self, **spec: Any) -> Any:
        return lead_box({"kind": "link", "name": "UpToFace", "chips": [],
                         **spec}, "invite")

    def test_an_empty_link_says_what_to_pick(self) -> None:
        invite = self.invite(pickHint="Select a face")
        self.assertTrue(invite.property("visible"))

    def test_no_invitation_once_linked_or_while_picking(self) -> None:
        chip = [{"key": "0", "label": "Pad.Face6", "sub": "Face6"}]
        self.assertFalse(self.invite(pickHint="Select a face", chips=chip)
                         .property("visible"))
        self.assertFalse(self.invite(pickHint="Select a face", readOnly=True)
                         .property("visible"))

    def test_without_a_prompt_the_plus_stays(self) -> None:
        self.assertFalse(self.invite().property("visible"))


if __name__ == "__main__":
    unittest.main()
