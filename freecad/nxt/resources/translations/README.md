# Translations

Nxt's user-facing text is marked for translation: `translate("Nxt", ...)`
and `QT_TRANSLATE_NOOP("Nxt", ...)` from `freecad/nxt/i18n.py` in Python,
the same (context, text) form FreeCAD's own modules use, with the context
written as a literal so lupdate can file it (commands use their own name),
and `qsTr()` in QML (context: the QML file's name). Console output is
developer-facing and is not translated.

To update the source file after changing text, from the repository root:

```bash
pyside6-lupdate $(find freecad/nxt -name '*.py' -o -name '*.qml') \
    -ts freecad/nxt/resources/translations/Nxt.ts
```

Translators work on copies named `Nxt_<locale>.ts` (for example
`Nxt_de.ts`); compile each with `pyside6-lrelease` to `Nxt_<locale>.qm`
beside it. `init_gui.py` adds this folder to FreeCAD's language path, so
the compiled files are picked up in the user's language at startup.
