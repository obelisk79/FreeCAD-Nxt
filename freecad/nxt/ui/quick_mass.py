"""Quick Mass: the selection's mass in a chosen material.

Shown at the bottom centre of the active 3D view while the tree's quick
setting is on. The material and unit system are remembered.
"""

from __future__ import annotations

import contextlib
import math
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from ..app.i18n import translate
from ..core import settings
from ..core.qt import QtCore
from ..core.view3d import active_viewport
from . import quick_host
from .view_notice import TopNotice

#: Gap between the bottom of the 3D view and the bar.
BOTTOM_MARGIN = 12
#: Unit schemas offered first, by FreeCAD's name for them.
FIRST_SCHEMAS = ("Internal", "ImperialDecimal")
#: Significant digits shown.
DIGITS = 4
BODY = "PartDesign::Body"
#: kg/m³ in a kg/mm³, FreeCAD's internal density unit.
PER_CUBIC_METRE = 1e9
#: The material setting's value while a custom density is used.
CUSTOM = "Custom"
#: Densities at least this large are shown as whole numbers.
WHOLE_FROM = 1000.0


def materials() -> list[tuple[str, float]]:
    """(name, density in kg/mm³) of each material with a density."""
    import Materials
    found: dict[str, float] = {}
    for material in Materials.MaterialManager().Materials.values():
        try:
            if not material.hasPhysicalProperty("Density"):
                continue
            density = App.Units.Quantity(
                material.PhysicalProperties["Density"]).Value
        except Exception:  # nosec B112  # an unreadable card
            continue
        if density > 0:
            found.setdefault(material.Name, density)
    return sorted(found.items(), key=lambda item: item[0].lower())


def density_text(kg_per_m3: float) -> str:
    """A density as the material list shows it: "7850 kg/m³"."""
    number = ("%.0f" % kg_per_m3 if kg_per_m3 >= WHOLE_FROM
              else "%.*g" % (DIGITS, kg_per_m3))
    return "%s kg/m³" % number


def parse_density(text: str) -> float | None:
    """kg/m³ from what was typed: a number, or a density with its unit."""
    text = text.strip().replace(",", ".")
    try:
        value = float(text)
    except ValueError:
        try:
            value = float(App.Units.Quantity(text).getValueAs("kg/m^3"))
        except Exception:
            return None
    return value if value > 0 and math.isfinite(value) else None


def schemas() -> list[tuple[str, str]]:
    """(name, label) of each unit system, the usual ones first."""
    names = list(App.Units.listSchemas())
    ordered = [n for n in FIRST_SCHEMAS if n in names]
    ordered += [n for n in names if n not in ordered]
    return [(n, str(App.Units.listSchemas(names.index(n))))
            for n in ordered]


def _owner(obj: Any) -> Any:
    """The body for a feature inside one, else the object itself."""
    try:
        group = obj.getParentGeoFeatureGroup()
    except Exception:  # noqa: BLE001 - not a document object
        return obj
    if group is not None and group.isDerivedFrom(BODY):
        return group
    return obj


def selected_volume() -> tuple[float, int]:
    """Total volume in mm³ of the selection's solids, and their count."""
    owners: dict[tuple[str, str], Any] = {}
    for obj in Gui.Selection.getSelection():
        owner = _owner(obj)
        owners[(owner.Document.Name, owner.Name)] = owner
    volume, count = 0.0, 0
    for owner in owners.values():
        shape = getattr(owner, "Shape", None)
        if shape is None or shape.isNull():
            continue
        for solid in shape.Solids:
            volume += abs(solid.Volume)
            count += 1
    return volume, count


def shown(mass_kg: float, schema: int) -> str:
    """The mass in the schema's unit, to DIGITS significant digits."""
    _text, factor, unit = App.Units.schemaTranslate(
        App.Units.Quantity("%r kg" % mass_kg), schema)
    value = mass_kg / factor if factor else mass_kg
    places = 0
    if value:
        places = max(0, DIGITS - 1 - int(math.floor(math.log10(abs(value)))))
    return "%.*f %s" % (min(places, 8), value, unit)


class QuickMass(QtCore.QObject):
    """What the QML bar shows and sets."""

    changed = QtCore.Signal()

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._materials: list[tuple[str, float]] | None = None
        self._schemas = schemas()
        self._mass = ""
        #: The QQuickWidget showing the bar, once there is one.
        self.view: Any = None

    def _all_materials(self) -> list[tuple[str, float]]:
        if self._materials is None:
            try:
                self._materials = materials()
            except Exception as exc:  # noqa: BLE001 - no Materials module
                App.Console.PrintLog("Nxt quick mass: %s\n" % exc)
                self._materials = []
        return self._materials

    def _names(self) -> list[str]:
        """The materials, then the custom density, last."""
        return [name for name, _density in self._all_materials()] + [
            translate("QuickMass", "Custom")]

    def _material(self) -> int:
        names = [name for name, _density in self._all_materials()]
        wanted = settings.get("QuickMassMaterial")
        if wanted == CUSTOM or not names:
            return len(names)
        return names.index(wanted) if wanted in names else 0

    def _custom(self) -> float:
        return float(settings.get("QuickMassDensity"))

    def _density(self) -> float:
        """The chosen density, kg/mm³."""
        found = self._all_materials()
        index = self._material()
        if index < len(found):
            return found[index][1]
        return self._custom() / PER_CUBIC_METRE

    def _unit(self) -> int:
        names = [name for name, _label in self._schemas]
        wanted = settings.get("QuickMassUnits")
        return names.index(wanted) if wanted in names else 0

    @QtCore.Property(list, notify=changed)
    def materials(self) -> list[str]:
        return self._names()

    @QtCore.Property(list, notify=changed)
    def densities(self) -> list[str]:
        return [density_text(d * PER_CUBIC_METRE)
                for _name, d in self._all_materials()] + [
            density_text(self._custom())]

    @QtCore.Property(int, notify=changed)
    def material(self) -> int:
        return self._material()

    @QtCore.Property(bool, notify=changed)
    def custom(self) -> bool:
        return self._material() == len(self._all_materials())

    @QtCore.Property(str, notify=changed)
    def customDensity(self) -> str:  # noqa: N802 - QML API
        return "%g" % self._custom()

    @QtCore.Property(list, notify=changed)
    def units(self) -> list[str]:
        return [label for _name, label in self._schemas]

    @QtCore.Property(int, notify=changed)
    def unit(self) -> int:
        return self._unit()

    @QtCore.Property(str, notify=changed)
    def mass(self) -> str:
        return self._mass

    @QtCore.Slot(result=QtCore.QPointF)
    def anchorOffset(self) -> QtCore.QPointF:  # noqa: N802 - QML API
        """The bar's offset in FreeCAD's window, under Wayland only."""
        return quick_host.window_offset(self.view)

    @QtCore.Slot(int)
    def pickMaterial(self, index: int) -> None:  # noqa: N802 - QML API
        names = [name for name, _density in self._all_materials()]
        if 0 <= index < len(names):
            settings.put("QuickMassMaterial", names[index])
        elif index == len(names):
            settings.put("QuickMassMaterial", CUSTOM)
        self.refresh()

    @QtCore.Slot(str, result=bool)
    def setCustomDensity(self, text: str) -> bool:  # noqa: N802 - QML API
        """Keep a density of one's own; False if it is no density.

        Only the value: the field finishes editing as it loses focus,
        which picking another material makes it do.
        """
        value = parse_density(text)
        if value is not None:
            settings.put("QuickMassDensity", value)
        self.refresh()
        return value is not None

    @QtCore.Slot(int)
    def pickUnit(self, index: int) -> None:  # noqa: N802 - QML API
        if 0 <= index < len(self._schemas):
            settings.put("QuickMassUnits", self._schemas[index][0])
            self.refresh()

    def refresh(self) -> None:
        self._mass = self._measured()
        self.changed.emit()

    def _measured(self) -> str:
        try:
            volume, count = selected_volume()
        except Exception as exc:  # noqa: BLE001 - a broken shape
            App.Console.PrintLog("Nxt quick mass: %s\n" % exc)
            count = 0
        if not count:
            return translate("QuickMass", "Select a solid or body")
        density = self._density()
        name = self._schemas[self._unit()][0]
        schema = list(App.Units.listSchemas()).index(name)
        return shown(volume * density, schema)


class MassBar(TopNotice):
    """Keeps the bar at the bottom centre of the active 3D view."""

    SOURCE = "QuickMass.qml"

    def __init__(self, theme: Any,
                 parent: QtCore.QObject | None = None) -> None:
        super().__init__(theme, parent)
        self._mass = QuickMass(self)
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._update)
        self._watching = False

    def install(self) -> None:
        super().install()
        self.sync()

    def remove(self) -> None:
        self._watch(False)
        self._timer.stop()
        super().remove()

    def sync(self) -> None:
        """Show or hide the bar to match the setting."""
        on = bool(settings.get("QuickMass"))
        self._watch(on)
        self._sync()
        if on:
            self._mass.refresh()

    def _watch(self, on: bool) -> None:
        if on == self._watching:
            return
        selection = Gui.Selection.addObserver if on \
            else Gui.Selection.removeObserver
        documents = App.addDocumentObserver if on \
            else App.removeDocumentObserver
        for add in (selection, documents):
            with contextlib.suppress(Exception):  # already (un)registered
                add(self)
        self._watching = on

    def _context(self) -> dict[str, Any]:
        return {"quickMass": self._mass}

    def _wanted_host(self) -> Any:
        if not settings.get("QuickMass"):
            return None
        return active_viewport()

    def _y(self, height: int) -> int:
        if self._host is None:
            return 0
        return max(0, self._host.height() - height - BOTTOM_MARGIN)

    def _ensure(self, host: Any) -> Any:
        widget = super()._ensure(host)
        self._mass.view = widget
        return widget

    def _view_changed(self, *_args: Any) -> None:
        super()._view_changed()
        self._timer.start()

    def _update(self) -> None:
        if self._widget is not None:
            self._mass.refresh()

    # -- selection and document observer -- #

    def addSelection(self, *_args: Any) -> None:  # noqa: N802
        self._timer.start()

    def removeSelection(self, *_args: Any) -> None:  # noqa: N802
        self._timer.start()

    def setSelection(self, *_args: Any) -> None:  # noqa: N802
        self._timer.start()

    def clearSelection(self, *_args: Any) -> None:  # noqa: N802
        self._timer.start()

    def slotRecomputedDocument(self, *_args: Any) -> None:  # noqa: N802
        self._timer.start()
