import QtQuick
import QtQuick.Controls.Basic

// Help writing an expression in any value field: give it the field's
// TextInput and the object the field belongs to, and once the text starts
// with "=" it shows, under the field, what fits at the cursor and what the
// expression gives now.
//
//   Up, Down      move through the suggestions
//   Tab           put the highlighted one in
//   Return        put it in, once Up or Down has picked one; otherwise
//                 Return is the field's own (apply the expression)
//   Escape        hide the list; a second Escape is the field's
//   a click       puts that one in
//
// The field calls handleKey() from its own Keys.onPressed, first; a key it
// returns true for is taken. It never takes the keyboard from the field:
// the list is a window of its own, made as a tooltip is (a Qt::ToolTip
// window), which never takes focus - a popup window grabs the keyboard,
// and the field being typed in lost it the moment the list appeared.
//
// It needs `expressions` (freecad/nxt/expressions.py) on the QML context.
// Without it, or without an owner, it does nothing at all.
Item {
    id: assist

    //: The TextInput being typed in.
    property Item input: null
    //: The object the field edits a property of: "Document#Name" or "Name".
    property string owner: ""

    readonly property bool available:
        typeof expressions !== "undefined" && assist.owner.length > 0
    readonly property bool typing: available && input !== null
                                   && input.activeFocus
                                   && input.text.trim().charAt(0) === "="
    property var suggestions: []
    property int current: 0
    //: Up or Down has picked a suggestion, so Return means "this one".
    property bool picked: false
    //: Escape hid the list; it stays hidden until the text changes.
    property bool hushed: false
    property var result: ({ok: false, text: ""})

    width: 0
    height: 0

    function refresh() {
        if (!assist.typing) {
            popup.close();
            return;
        }
        assist.suggestions = expressions.suggest(
            assist.owner, input.text, input.cursorPosition);
        assist.current = 0;
        assist.picked = false;
        assist.result = expressions.evaluate(assist.owner, input.text);
        if (assist.hushed) {
            popup.close();
            return;
        }
        // Opened from this item; on Wayland shifted by where the view
        // really is in FreeCAD's window (expressions.anchor_offset).
        var below = input.mapToItem(assist, 0, input.height + 2);
        var shift = expressions.anchorOffset(assist);
        // Wayland places a popup window against its parent item, not at
        // popup.x/y, so move the parent there and open at its corner.
        anchor.x = below.x + shift.x;
        anchor.y = below.y + shift.y;
        popup.open();
    }

    function accept(index) {
        var chosen = assist.suggestions[index];
        if (!chosen)
            return;
        var done = expressions.complete(input.text, input.cursorPosition,
                                        chosen.insert);
        input.text = done.text;
        input.cursorPosition = done.cursor;
    }

    function handleKey(event) {
        if (!assist.typing || !popup.visible)
            return false;
        var count = assist.suggestions.length;
        if (event.key === Qt.Key_Escape) {
            assist.hushed = true;
            popup.close();
            return true;
        }
        if (count === 0)
            return false;
        if (event.key === Qt.Key_Down) {
            assist.current = (assist.current + 1) % count;
            assist.picked = true;
            return true;
        }
        if (event.key === Qt.Key_Up) {
            assist.current = (assist.current + count - 1) % count;
            assist.picked = true;
            return true;
        }
        if (event.key === Qt.Key_Tab
                || ((event.key === Qt.Key_Return
                     || event.key === Qt.Key_Enter) && assist.picked)) {
            assist.accept(assist.current);
            return true;
        }
        return false;
    }

    Connections {
        target: assist.input
        function onTextChanged() {
            assist.hushed = false;
            assist.refresh();
        }
        function onCursorPositionChanged() { assist.refresh(); }
        function onActiveFocusChanged() { assist.refresh(); }
    }

    Item {
        id: anchor
        width: 1
        height: 1
    }

    ToolTip {
        id: popup
        parent: anchor
        x: 0
        y: 0
        popupType: Popup.Window
        focus: false
        closePolicy: Popup.NoAutoClose
        timeout: -1
        delay: 0
        enter: null
        exit: null
        margins: 4
        padding: 4
        width: Math.max(220, list.implicitWidth + 8)

        background: Rectangle {
            radius: 4
            color: theme.background
            border.width: 1
            border.color: theme.border
        }

        contentItem: Column {
            id: list
            spacing: 1

            Repeater {
                model: assist.suggestions

                Rectangle {
                    id: line
                    required property int index
                    required property var modelData
                    width: Math.max(212, row.implicitWidth + 12)
                    height: theme.fieldHeight
                    radius: 3
                    color: index === assist.current ? theme.accent
                         : lineHover.hovered ? theme.hover : "transparent"

                    Row {
                        id: row
                        x: 6
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 8

                        Text {
                            text: line.modelData.kind === "function" ? "ƒ"
                                : line.modelData.kind === "object" ? "◇"
                                : line.modelData.kind === "constant" ? "π"
                                : "·"
                            width: 10
                            font.pixelSize: theme.fontSmall
                            color: line.index === assist.current
                                   ? theme.accentText : theme.textDim
                        }
                        Text {
                            text: line.modelData.label
                            font.pixelSize: theme.fontSmall
                            color: line.index === assist.current
                                   ? theme.accentText : theme.text
                        }
                        Text {
                            visible: line.modelData.detail.length > 0
                            text: line.modelData.detail
                            font.pixelSize: theme.fontAside
                            color: line.index === assist.current
                                   ? theme.accentText : theme.textDim
                        }
                    }

                    HoverHandler { id: lineHover }
                    TapHandler { onTapped: assist.accept(line.index) }
                }
            }

            // What it gives now, or why nothing.
            Rectangle {
                width: parent.width
                height: 1
                visible: assist.suggestions.length > 0
                color: theme.border
            }
            Text {
                width: Math.max(212, implicitWidth)
                leftPadding: 6
                topPadding: 2
                bottomPadding: 2
                text: assist.result.text.length === 0
                      ? qsTr("Type an expression")
                      : (assist.result.ok ? "= " + assist.result.text
                                          : assist.result.text)
                font.pixelSize: theme.fontSmall
                font.italic: !assist.result.ok
                color: assist.result.ok ? theme.text : theme.danger
                elide: Text.ElideRight
            }
        }
    }
}
