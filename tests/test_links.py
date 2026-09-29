"""Dependency arrows: which rows the selection links to, and how.

Run with: python3 tests/test_links.py
"""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from freecad.nxt.tree import links  # noqa: E402


def node(parent: str | None = None, refs: Any = (),
         consumers: Any = ()) -> Any:
    return types.SimpleNamespace(parent=parent, refs=list(refs),
                                 consumers=list(consumers))


class Snapshot:
    def __init__(self, nodes: dict[str, Any]) -> None:
        self.nodes = nodes

    def is_ancestor(self, name: str, candidate: str) -> bool:
        cursor = self.nodes[name].parent if name in self.nodes else None
        while cursor:
            if cursor == candidate:
                return True
            cursor = self.nodes[cursor].parent
        return False


def ref(name: str) -> tuple[str, str, str, str]:
    return (name, name, "", "")


class KindTests(unittest.TestCase):
    def test_kinds(self) -> None:
        self.assertEqual(links.kind_of(["AttachmentSupport"]), "attachment")
        self.assertEqual(links.kind_of(["ExpressionEngine"]), "expression")
        self.assertEqual(links.kind_of(["LinkedObject"]), "link")
        self.assertEqual(links.kind_of(["Profile"]), "geometry")
        self.assertEqual(links.kind_of([]), "geometry")


class ArrowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.nodes = {
            "Body": node(),
            "Sketch": node("Body", consumers=[("Pad", "Pad", ["Profile"])]),
            "Pad": node("Body", refs=[ref("Sketch")],
                        consumers=[("Hole", "Hole", ["BaseFeature"]),
                                   ("S2", "S2", ["AttachmentSupport"])]),
            "Hole": node("Body", refs=[ref("Pad")]),
            "S2": node("Folder", refs=[ref("Pad")]),
            "Folder": node("Body"),
        }
        self.rows = {"Body": 0, "Sketch": 1, "Pad": 2, "Hole": 3,
                     "Folder": 4, "S2": 5}

    def run_for(self, name: str) -> dict[str, Any]:
        return links.arrows(Snapshot(self.nodes), name,
                            lambda n: self.rows.get(n, -1))

    def test_in_and_out(self) -> None:
        out = self.run_for("Pad")
        self.assertEqual(out["source"], 2)
        got = {(e["row"], e["dir"], e["kind"]) for e in out["links"]}
        self.assertEqual(got, {(1, "in", "geometry"), (3, "out", "geometry"),
                               (5, "out", "attachment")})
        self.assertEqual(out["links"][0]["row"] in (1, 3), True)

    def test_collapsed_goes_to_ancestor(self) -> None:
        del self.rows["S2"]
        out = self.run_for("Pad")
        rows = {(e["row"], e["kind"]) for e in out["links"]}
        self.assertIn((4, "attachment"), rows)

    def test_merged_count(self) -> None:
        self.nodes["Pad"].consumers.append(("S3", "S3", ["Support"]))
        self.nodes["S3"] = node("Folder", refs=[ref("Pad")])
        del self.rows["S2"]
        out = self.run_for("Pad")
        badge = [e for e in out["links"] if e["row"] == 4]
        self.assertEqual(badge[0]["count"], 2)
        self.assertEqual(sorted(badge[0]["names"]), ["S2", "S3"])

    def test_nested_operands_skipped(self) -> None:
        self.nodes["Sketch"].parent = "Pad"
        out = self.run_for("Pad")
        self.assertNotIn(1, [e["row"] for e in out["links"]])
        out = self.run_for("Sketch")
        self.assertEqual(out["links"], [])

    def test_unknown(self) -> None:
        self.assertEqual(self.run_for("Nope"), {"source": -1, "links": []})


if __name__ == "__main__":
    unittest.main()
