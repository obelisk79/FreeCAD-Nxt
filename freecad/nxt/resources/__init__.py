"""The addon's assets - icons and QML - located through importlib.resources.

Resolved from the package rather than from `__file__`, so they are found
wherever and however the addon is installed. FreeCAD's icon path and QML's
import path both want real directories, which an installed addon always
has; `as_file` would only matter for a zipped install.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

_ROOT = files(__name__)

#: Command and addon icons, registered with FreeCAD's icon path.
ICONS = Path(str(_ROOT / "icons"))
#: The project's logo. A copy named preferences-freecad-nxt.svg is what
#: FreeCAD's Preferences dialog finds for the FreeCAD-Nxt group.
LOGO = ICONS / "FreeCAD-Nxt.svg"

#: QML: the panel's and inspector's root files, and the `Nxt` module.
QML = Path(str(_ROOT / "qml"))

#: Context menu definitions; `default.toml` is Nxt's own.
MENUS = Path(str(_ROOT / "menus"))

#: Compiled translations, Nxt_<locale>.qm, for FreeCAD's language path.
TRANSLATIONS = Path(str(_ROOT / "translations"))


def qml(name: str) -> Path:
    """A root QML file, such as 'NxtTree.qml'."""
    return QML / name
