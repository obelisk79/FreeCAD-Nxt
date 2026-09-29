"""Tree colours read from a stylesheet, FreeCAD tokens resolved.

Run with: python3 tests/test_qss_colours.py
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import test_inspector  # noqa: E402,F401  (installs the FreeCAD stub)

from freecad.nxt.tree import qss_colours as q  # noqa: E402

TOKENS = {"TreeBg": "#f0f0f0", "Ink": "@Ink2", "Ink2": "#202020",
          "Packed": 0x336699FF, "Loop": "@Loop", "Mixed": "lighten(@A, 5)"}


def names(pair):
    return tuple(c.name() if c is not None else None for c in pair)


class Tests(unittest.TestCase):
    def read(self, qss):
        return names(q.tree_colours(qss, TOKENS.get))

    def test_explicit(self):
        self.assertEqual(self.read(
            "QTreeView { background-color: #fafafa; color: black; }"),
            ("#fafafa", "#000000"))

    def test_tokens_and_chains(self):
        self.assertEqual(self.read(
            "QTreeView{background-color:@TreeBg;color:@Ink}"),
            ("#f0f0f0", "#202020"))

    def test_packed_parameter(self):
        self.assertEqual(self.read("QTreeView{background-color:@Packed}"),
                         ("#336699", None))

    def test_most_specific_wins_per_property(self):
        qss = ("QAbstractItemView{background-color:#111111;color:#eeeeee}"
               "Gui--TreeWidget{background-color:@TreeBg}")
        self.assertEqual(self.read(qss), ("#f0f0f0", "#eeeeee"))

    def test_later_rule_overrides(self):
        qss = ("QTreeView{background-color:#111111}/* c */"
               "QTreeView, QListView {background-color: rgb(1, 2, 3);}")
        self.assertEqual(self.read(qss), ("#010203", None))

    def test_pseudo_states_ignored(self):
        self.assertEqual(self.read(
            "QTreeView::item:selected{background-color:#ff0000}"),
            (None, None))

    def test_unreadable_is_none(self):
        for value in ("@Loop", "@Missing", "@Mixed",
                      "qlineargradient(x1:0, y1:0, stop:0 red)"):
            self.assertEqual(self.read(
                "QTreeView{background-color:%s}" % value), (None, None),
                value)

    def test_see_through_is_none(self):
        for value in ("transparent", "rgba(0, 0, 0, 0)", "#80ffffff",
                      "rgba(240, 240, 240, 0.5)"):
            self.assertEqual(self.read(
                "QTreeView{background-color:%s}" % value), (None, None),
                value)
        self.assertEqual(self.read(
            "QTreeView{background-color:rgba(1, 2, 3, 255)}"),
            ("#010203", None))

    def test_transparent_tree_takes_what_it_sits_in(self):
        qss = ("QAbstractScrollArea{background-color:transparent}"
               "QTreeView{selection-background-color:#60c7f9}"
               "QWidget{background-color:#f0f0f0;color:#000000}")
        self.assertEqual(self.read(qss), ("#f0f0f0", "#000000"))

    def test_background_shorthand(self):
        self.assertEqual(self.read("QTreeView{background:@TreeBg}"),
                         ("#f0f0f0", None))


if __name__ == "__main__":
    unittest.main()
