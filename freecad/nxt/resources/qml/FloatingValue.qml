import QtQuick

// A value field floating in the 3D view beside a feature's drag arrow.
//
// What it shows and what it sets belong to the task panel's own field -
// the Pad's Length, say - through `field` (tree/float_input.py): typing
// here types there, so units, expressions and FreeCAD's validation all
// work as they do in the panel. A click takes the keyboard; a double
// click selects the whole value to type over. Enter keeps the value and
// closes the edit, as the task's OK does; clicking away keeps it and
// recomputes; Escape puts the value back as it was.
Rectangle {
    id: box

    function takeKeyboard(selectAll) {
        field.grab();
        input.forceActiveFocus();
        if (selectAll)
            input.selectAll();
    }

    // Over the whole box, label included, so the target is generous, and
    // above the text so a double click selects the whole value rather
    // than the word under the pointer ("50.00" of "50.00 mm").
    MouseArea {
        anchors.fill: parent
        z: 1
        cursorShape: Qt.IBeamCursor
        onPressed: function (mouse) {
            box.takeKeyboard(false);
            input.cursorPosition = input.positionAt(
                mouse.x - input.x, input.height / 2);
        }
        onDoubleClicked: box.takeKeyboard(true)
    }

    implicitWidth: Math.max(96, input.contentWidth + caption.width + 22)
    implicitHeight: theme.fieldHeight + 6
    radius: 4
    color: theme.background
    border.width: input.activeFocus ? 2 : 1
    border.color: input.activeFocus ? theme.accent : theme.border

    Text {
        id: caption
        anchors.left: parent.left
        anchors.leftMargin: 7
        anchors.verticalCenter: parent.verticalCenter
        text: field.label
        font.pixelSize: theme.fontAside
        color: theme.textDim
    }

    TextInput {
        id: input
        anchors.left: caption.right
        anchors.leftMargin: 6
        anchors.right: parent.right
        anchors.rightMargin: 7
        anchors.verticalCenter: parent.verticalCenter
        font.pixelSize: theme.fontRow
        color: theme.text
        clip: true
        horizontalAlignment: TextInput.AlignRight

        // Follows the task panel's value, except while being typed in.
        text: field.text
        Connections {
            target: field
            function onTextChanged() {
                if (!input.activeFocus)
                    input.text = field.text;
            }
            // When an edit begins: the keyboard, and the value selected.
            function onFocusRequested(selectAll) {
                box.takeKeyboard(selectAll);
            }
        }

        // Losing the keyboard - a click in the 3D view, say - keeps what
        // was typed, as leaving a field in the task panel does.
        onActiveFocusChanged: {
            if (activeFocus)
                selectAll();
            else if (text !== field.text)
                field.commit(text);
        }
        // Enter keeps the value and closes the edit, as the task's OK.
        // The panel's own formatting of the value is shown back first
        // ("75" becomes "75.00 mm"), so losing the keyboard next finds
        // nothing changed.
        Keys.onReturnPressed: {
            field.finish(text); text = field.text; field.release();
        }
        Keys.onEnterPressed: {
            field.finish(text); text = field.text; field.release();
        }
        // Escape puts the value back first, so losing the keyboard next
        // has nothing to commit.
        Keys.onEscapePressed: { text = field.text; field.release(); }
        // Each keystroke goes through, as it does in the panel: the model
        // previews while typing.
        onTextEdited: field.preview(text)
    }

    Accessible.role: Accessible.EditableText
    Accessible.name: field.label
}
