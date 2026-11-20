"""Relationship hints: when a kind of link counts as learned.

Run with: python3 tests/test_hints.py
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

import fakes  # noqa: E402

App, Gui = fakes.install()

from freecad.nxt.tree import hints  # noqa: E402


class HintTests(unittest.TestCase):

    def setUp(self) -> None:
        App.ParamGet = fakes.params()
        hints.reset()
        self.addCleanup(setattr, hints, "_SESSION", hints._SESSION)

    def sessions(self, count: int, sightings: int, kinds: set[str]) -> None:
        for session in range(count):
            hints._SESSION = "session %d" % session
            for _ in range(sightings):
                hints.seen(kinds)

    def test_many_sightings_in_one_session_are_not_enough(self) -> None:
        self.sessions(1, hints.SIGHTINGS * 3, {"geometry"})
        self.assertEqual(hints.learned(), [])

    def test_enough_sightings_over_enough_sessions_are(self) -> None:
        per = -(-hints.SIGHTINGS // hints.SESSIONS)
        self.sessions(hints.SESSIONS, per, {"geometry"})
        self.assertEqual(hints.learned(), ["geometry"])

    def test_each_kind_is_learned_on_its_own(self) -> None:
        self.sessions(hints.SESSIONS, hints.SIGHTINGS, {"geometry"})
        self.sessions(hints.SESSIONS, 1, {"link"})
        self.assertEqual(hints.learned(), ["geometry"])

    def test_seen_says_when_a_kind_is_newly_learned(self) -> None:
        self.sessions(hints.SESSIONS - 1, hints.SIGHTINGS, {"link"})
        hints._SESSION = "last"
        self.assertTrue(hints.seen({"link"}))
        self.assertFalse(hints.seen({"link"}))

    def test_reset_shows_them_again(self) -> None:
        self.sessions(hints.SESSIONS, hints.SIGHTINGS, {"expression"})
        hints.reset()
        self.assertEqual(hints.learned(), [])

    def test_a_damaged_setting_counts_as_nothing_learned(self) -> None:
        from freecad.nxt.core import settings
        settings.put(hints.SETTING, "{not json")
        self.assertEqual(hints.learned(), [])
        hints.seen({"geometry"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
