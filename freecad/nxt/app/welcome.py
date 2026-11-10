"""The welcome dialog on Nxt's first run: what Nxt adds, and addons to add.

First run means Nxt's settings group is empty as FreeCAD starts. That is
only so before Nxt has ever run: an update keeps the group, and removing
Nxt deletes it (so a reinstall is welcomed again).

Recommended addons that are missing can be installed from the dialog,
through the Addon Manager's own installer.
"""

from __future__ import annotations

import contextlib
import re
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from .. import resources
from ..core import settings
from ..core.qt import QtCore, QtWidgets
from .i18n import QT_TRANSLATE_NOOP, translate

#: Wait after startup, so the window and the panel are up first.
DELAY_MS = 1500

#: Install states, as QML shows them.
MISSING, INSTALLING, INSTALLED, FAILED = ("missing", "installing",
                                          "installed", "failed")


@dataclass(frozen=True)
class Recommended:
    """An addon the welcome offers: its catalog entry and why to have it."""

    name: str
    blurb: str
    url: str
    zip_url: str


#: From FreeCAD's addon index (github.com/FreeCAD/Addons, Data/Index.json).
RECOMMENDED = (
    Recommended(
        "OpenTheme",
        QT_TRANSLATE_NOOP("Nxt", "Accessible light and dark themes."),
        "https://github.com/obelisk79/OpenTheme",
        "https://github.com/obelisk79/OpenTheme/archive/refs/heads/"
        "main.zip"),
    Recommended(
        "Telemetry",
        QT_TRANSLATE_NOOP("Nxt", "Shares non-identifying usage data."),
        "https://github.com/FreeCAD/FreeCAD-Telemetry",
        "https://github.com/FreeCAD/FreeCAD-Telemetry/archive/refs/heads/"
        "main.zip"),
)
BRANCH = "main"

_PACKAGE_NAME = re.compile(r"<name>\s*([^<]+?)\s*</name>")


def first_run() -> bool:
    """Whether Nxt has never run here: its settings group is empty.

    Ask before anything at startup writes a setting.
    """
    try:
        return not App.ParamGet(settings.GROUP).GetContents()
    except Exception:  # noqa: BLE001 - unreadable: don't welcome
        return False


def _mod_dirs() -> list[Path]:
    dirs = [Path(App.getUserAppDataDir()) / "Mod"]
    with contextlib.suppress(Exception):  # no Addon Manager: the default
        import addonmanager_freecad_interface as fci
        dirs.append(Path(fci.DataPaths().mod_dir))
    return [d for d in dict.fromkeys(dirs) if d.is_dir()]


def _package_name(folder: Path) -> str:
    with contextlib.suppress(OSError):
        text = (folder / "package.xml").read_text(
            encoding="utf-8", errors="replace")
        found = _PACKAGE_NAME.search(text)
        if found:
            return found.group(1)
    return ""


def installed(name: str) -> bool:
    """Whether an addon of this name is in a Mod folder."""
    wanted = name.lower()
    for mod in _mod_dirs():
        for folder in mod.iterdir():
            if folder.is_dir() and wanted in (
                    folder.name.lower(), _package_name(folder).lower()):
                return True
    return False


class _Job(QtCore.QObject):
    """One addon's installation, reporting back on the main thread.

    The installer's signals come from its own thread; connected to this
    object's slots they are queued to the thread this object lives in.
    """

    def __init__(self, name: str, welcome: Welcome) -> None:
        super().__init__(welcome)
        self.name = name
        self.welcome = welcome
        self.thread: Any = None
        self.installer: Any = None

    @QtCore.Slot(object)
    def succeeded(self, _addon: Any) -> None:
        self.welcome._set(self.name, INSTALLED)

    @QtCore.Slot(object, str)
    def failed(self, _addon: Any, why: str) -> None:
        self.welcome._failed(self.name, why)


class Welcome(QtCore.QObject):
    """What the welcome QML reads and asks for."""

    changed = QtCore.Signal()
    close_requested = QtCore.Signal()

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._offers = [r for r in RECOMMENDED if not installed(r.name)]
        self._states = {r.name: MISSING for r in self._offers}
        self._errors: dict[str, str] = {}
        self._jobs: dict[str, _Job] = {}

    @QtCore.Property(str, constant=True)
    def logo(self) -> str:
        return QtCore.QUrl.fromLocalFile(str(resources.LOGO)).toString()

    @QtCore.Property("QVariantList",  # type: ignore[arg-type]
                     notify=changed)
    def addons(self) -> list[dict[str, str]]:
        return [{"name": r.name, "blurb": translate("Nxt", r.blurb),
                 "state": self._states[r.name],
                 "error": self._errors.get(r.name, "")}
                for r in self._offers]

    @QtCore.Property(bool, notify=changed)
    def restartNeeded(self) -> bool:  # noqa: N802 - QML API
        return INSTALLED in self._states.values()

    @QtCore.Slot(str)
    def install(self, name: str) -> None:
        offer = next((r for r in self._offers if r.name == name), None)
        if offer is None or self._states[name] in (INSTALLING, INSTALLED):
            return
        self._set(name, INSTALLING)
        try:
            self._start(offer)
        except Exception as exc:  # noqa: BLE001 - shown on the dialog
            App.Console.PrintLog(traceback.format_exc())
            self._failed(name, str(exc))

    def _start(self, offer: Recommended) -> None:
        import NetworkManager
        from Addon import Addon
        from addonmanager_installer import AddonInstaller

        # Downloads go through the Addon Manager's network manager, made
        # here on the main thread, as its own command does.
        NetworkManager.InitializeNetworkManager()
        addon = Addon(offer.name, offer.url, Addon.Status.NOT_INSTALLED,
                      BRANCH)
        addon.zip_url = offer.zip_url
        job = _Job(offer.name, self)
        job.thread = QtCore.QThread(self)
        job.installer = AddonInstaller(addon)
        job.installer.moveToThread(job.thread)
        job.installer.success.connect(job.succeeded)
        job.installer.failure.connect(job.failed)
        job.installer.finished.connect(job.thread.quit)
        job.thread.started.connect(job.installer.run)
        self._jobs[offer.name] = job
        job.thread.start()

    def _set(self, name: str, state: str) -> None:
        self._states[name] = state
        self.changed.emit()

    def _failed(self, name: str, why: str) -> None:
        App.Console.PrintWarning("Nxt: %s was not installed: %s\n"
                                 % (name, why))
        self._errors[name] = why
        self._set(name, FAILED)

    @QtCore.Slot()
    def restart(self) -> None:
        """Restart FreeCAD, so the new addons load."""
        with contextlib.suppress(Exception):  # no Addon Manager: no restart
            import addonmanager_utilities as utils
            self.close_requested.emit()
            utils.restart_freecad()

    @QtCore.Slot()
    def close(self) -> None:
        self.close_requested.emit()


#: The open dialog, kept so Qt does not lose it.
_dialog: QtWidgets.QDialog | None = None


def show() -> None:
    """Open the welcome dialog over the main window."""
    global _dialog
    try:
        from ..ui import quick_host
        from . import services
        main = Gui.getMainWindow()
        dialog = QtWidgets.QDialog(main)
        dialog.setWindowTitle(translate("Nxt", "Welcome to Nxt"))
        dialog.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        # Owned by the window, not the dialog: an installation started
        # here carries on if the dialog is closed.
        welcome = Welcome(main)
        view = quick_host.make_view(
            dialog, "Welcome.qml",
            {"welcome": welcome, "theme": services.theme()})
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(view)
        root = view.rootObject()
        if root is not None:
            dialog.resize(int(root.implicitWidth()),
                          int(root.implicitHeight()))
        welcome.close_requested.connect(dialog.accept)
        dialog.finished.connect(_closed)
        _dialog = dialog
        dialog.show()
    except Exception:  # noqa: BLE001 - a welcome is never worth an error
        App.Console.PrintError("Nxt: could not show the welcome\n")
        App.Console.PrintLog(traceback.format_exc())


def _closed(_result: int) -> None:
    global _dialog
    _dialog = None


def schedule() -> None:
    """Show the welcome once startup has settled, on a first run."""
    if first_run():
        QtCore.QTimer.singleShot(DELAY_MS, show)
