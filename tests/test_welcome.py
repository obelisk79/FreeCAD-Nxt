"""The first-run welcome: when it shows, and which addons it offers.

Run with: python3 tests/test_welcome.py   (needs PySide6)
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import fakes  # noqa: E402

App, Gui = fakes.install()

from freecad.nxt.app import welcome  # noqa: E402


class Group:
    """A parameter group holding `contents`, as GetContents lists them."""

    def __init__(self, contents: list[tuple[str, str, Any]]) -> None:
        self.contents = contents

    def GetContents(self) -> list[tuple[str, str, Any]]:  # noqa: N802
        return self.contents


class FirstRunTests(unittest.TestCase):

    def tearDown(self) -> None:
        App.ParamGet = fakes.params()

    def test_an_empty_settings_group_is_a_first_run(self) -> None:
        App.ParamGet = lambda _group: Group([])
        self.assertTrue(welcome.first_run())

    def test_an_update_keeps_the_settings_and_is_not(self) -> None:
        App.ParamGet = lambda _group: Group([("Boolean", "Visible", True)])
        self.assertFalse(welcome.first_run())

    def test_unreadable_settings_are_not_a_first_run(self) -> None:
        def broken(_group: str) -> Any:
            raise RuntimeError("no parameters")
        App.ParamGet = broken
        self.assertFalse(welcome.first_run())


class InstalledTests(unittest.TestCase):

    def setUp(self) -> None:
        self.home = tempfile.TemporaryDirectory()
        self.mod = Path(self.home.name) / "Mod"
        self.mod.mkdir()
        App.getUserAppDataDir = lambda: self.home.name + os.sep

    def tearDown(self) -> None:
        self.home.cleanup()

    def test_found_by_folder_name_whatever_its_case(self) -> None:
        (self.mod / "opentheme").mkdir()
        self.assertTrue(welcome.installed("OpenTheme"))
        self.assertFalse(welcome.installed("Telemetry"))

    def test_found_by_package_name_in_another_folder(self) -> None:
        folder = self.mod / "FreeCAD-Telemetry"
        folder.mkdir()
        (folder / "package.xml").write_text(
            "<package><name> Telemetry </name></package>", encoding="utf-8")
        self.assertTrue(welcome.installed("Telemetry"))

    def test_only_missing_addons_are_offered(self) -> None:
        (self.mod / "OpenTheme").mkdir()
        offered = [a["name"] for a in welcome.Welcome().addons]
        self.assertEqual(offered, ["Telemetry"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
