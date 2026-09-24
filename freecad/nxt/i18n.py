"""Translation helpers, per FreeCAD's convention for addons.

`translate` looks a string up at runtime; `QT_TRANSLATE_NOOP` only marks a
string for extraction by lupdate, for text that is translated later - a
table of phrases, say, translated when it is shown. Console output is
developer-facing and is not translated. QML text uses `qsTr`.

Outside FreeCAD (the tests) there is nothing to translate against, and the
text is returned as written.
"""

from __future__ import annotations

import FreeCAD as App

#: The context Nxt's own strings are filed under (commands use their name).
CONTEXT = "Nxt"


def translate(context: str, text: str) -> str:
    """FreeCAD's `App.Qt.translate`, with the same (context, text) order.

    Call sites pass the context as a literal, `translate("Nxt", "...")`, so
    lupdate can file the string, exactly as FreeCAD's own modules do.
    """
    qt = getattr(App, "Qt", None)
    if qt is None or not hasattr(qt, "translate"):
        return text
    return str(qt.translate(context, text))


def QT_TRANSLATE_NOOP(context: str, text: str) -> str:  # noqa: N802
    """Mark `text` for extraction without translating it here."""
    return text
