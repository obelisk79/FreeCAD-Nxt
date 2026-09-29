# Temporary: what the stylesheet says a tree looks like. Delete after.
import re

import FreeCAD as App
from PySide6 import QtWidgets

from freecad.nxt.tree import qss_colours, theme

print("== theme settings ==")
for group in ("MainWindow", "Themes", "General"):
    p = App.ParamGet("User parameter:BaseApp/Preferences/" + group)
    for kind, key, value in p.GetContents() or ():
        if any(w in key.lower() for w in ("style", "theme", "pack", "qss")):
            print(" ", group, kind, key, "=", value)

qss = QtWidgets.QApplication.instance().styleSheet()
print("\n== applied stylesheet ==")
print("  length", len(qss), "| @tokens in it:", len(re.findall(r"@\w", qss)))
for sel in qss_colours.SELECTORS:
    d = qss_colours.rules_for(qss, sel)
    print(" ", sel, {k: v for k, v in d.items()
                     if "background" in k or k == "color"})
print("\n== every rule whose selector mentions a tree ==")
body = re.sub(r"/\*.*?\*/", "", qss, flags=re.S)
for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", body):
    sel = " ".join(m.group(1).split())
    if "tree" in sel.lower():
        print(" ", sel[:100], "=>", " ".join(m.group(2).split())[:140])
b, t = theme._stylesheet_colours()
print("\nresolved:", b and b.name(), t and t.name())
print("\n== what a tree sits in ==")
for sel in ("QDockWidget", "QMainWindow", "QWidget"):
    d = qss_colours.rules_for(qss, sel)
    print(" ", sel, {k: v for k, v in d.items()
                     if "background" in k or k == "color"})
