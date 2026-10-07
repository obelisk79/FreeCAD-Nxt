import QtQuick

// A value field floating in the 3D view beside a feature's drag arrow.
//
// What it shows and what it sets belong to the task panel's own field -
// the Pad's Length, say - through `field` (tree/float_input.py): typing
// here types there, so units, expressions and FreeCAD's validation all
// work as they do in the panel. A click takes the keyboard; a double
// click selects the whole value to type over. Enter keeps the value and
// closes the edit, as the task's OK does; clicking away keeps it and
// recomputes; Escape puts the value back as it was; Tab moves to the
// next box; the mouse wheel steps the value.
Rectangle {
    id: box

    // Tab, handed over by the widget (float_input.py's event filter): Qt
    // takes Tab for its own focus chain before a key handler here sees
    // it, and the keyboard went off into FreeCAD's window.
    function tab(backward) {
        input.tabOn(backward);
    }

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

    // The wheel steps the value, a notch a step and ten with Ctrl, by
    // the panel field's own step. Part notches from a touchpad add up
    // until they make a whole one. Only the text here changes while the
    // wheel turns: setting the feature on every notch would recompute
    // the model on every notch. The value is set once the wheel rests.
    WheelHandler {
        id: wheel
        property real pending: 0
        property int steps: 0
        acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
        onWheel: function (event) {
            box.turn(event.angleDelta.y,
                     (event.modifiers & Qt.ControlModifier) !== 0);
        }
    }
    // Also called by the widget (float_input.py's event filter), which
    // takes the wheel before it gets here: left to arrive on its own, it
    // went on to the 3D view as well and zoomed it.
    function turn(angle, tenfold) {
        wheel.pending += angle / 120;
        var notches = wheel.pending > 0 ? Math.floor(wheel.pending)
                                        : Math.ceil(wheel.pending);
        if (notches === 0)
            return;
        wheel.pending -= notches;
        wheel.steps += notches * (tenfold ? 10 : 1);
        input.text = field.stepped(wheel.steps);
        wheelRest.restart();
    }
    Timer {
        id: wheelRest
        interval: 400
        onTriggered: {
            wheel.steps = 0;
            wheel.pending = 0;
            if (input.text !== field.text) {
                field.commit(input.text);
                input.text = field.text;
            }
        }
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
        // Tab and Shift+Tab move between the boxes of a feature with
        // several handles. What was typed is kept first, and shown back
        // as the panel formats it, so losing the keyboard next finds
        // nothing changed.
        function tabOn(backward) {
            if (text !== field.text) {
                field.commit(text);
                text = field.text;
            }
            field.tab(backward);
        }
        Keys.onTabPressed: tabOn(false)
        Keys.onBacktabPressed: tabOn(true)
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
