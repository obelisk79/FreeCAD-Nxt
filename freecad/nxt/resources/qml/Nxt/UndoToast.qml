import QtQuick

// What Nxt just did, with a way back: "Moved Pocket after Pad · Undo".
// Shown after a drag, a rename or a tip move - gestures that change the
// model at once, with nothing to confirm - and gone by itself after a few
// seconds, or as soon as it is used or dismissed.
//
// Also something found that is the user's to act on: "Sketch is not
// closed · Edit". That one is `sticky`, and stays until dismissed.
Rectangle {
    id: toast

    property string message: ""
    //: The label of each button, in order. None: only a message.
    property var actions: []
    //: Stays until used or dismissed.
    property bool sticky: false
    //: How long it stays, in milliseconds. Longer while pointed at.
    property int stay: 6000
    signal actionRequested(int index)

    function show(text) {
        message = text;
        opacity = 1;
        wait();
    }
    function wait() {
        if (sticky)
            timer.stop();
        else
            timer.restart();
    }
    onStickyChanged: if (visible) wait()
    function dismiss() {
        timer.stop();
        opacity = 0;
    }

    visible: opacity > 0
    opacity: 0
    //: Width of whatever it is shown in; its host keeps this current.
    property real available: 400
    //: Kept clear of the edges of whatever it is shown in.
    property int margin: 10
    //: Space at each end, and between the message and each button.
    readonly property int pad: 12
    // Sized from the parts' own widths, never from this item's width:
    // the message's width was once worked out from the toast's, and the
    // toast's from the message's, and the two settled on nothing - a
    // box a few pixels wide with the text spilling out of it.
    // Asked of the list, not the row: a row emptied of its buttons keeps
    // the width it had.
    readonly property real actionsRoom:
        actions.length > 0 ? buttons.width + pad : 0
    readonly property real room:
        available - 2 * margin - actionsRoom - close.implicitWidth - 3 * pad
    implicitWidth: label.width + actionsRoom + close.implicitWidth + 3 * pad
    implicitHeight: theme.rowHeight + 8
    radius: 6
    color: theme.background
    border.width: 1
    border.color: theme.border

    Behavior on opacity { NumberAnimation { duration: 120 } }

    Timer {
        id: timer
        interval: toast.stay
        // Not while it is being read with the pointer on it.
        onTriggered: hover.hovered ? restart() : toast.dismiss()
    }
    HoverHandler { id: hover }

    Text {
        id: label
        anchors.verticalCenter: parent.verticalCenter
        x: toast.pad
        width: Math.max(0, Math.min(implicitWidth, toast.room))
        text: toast.message
        elide: Text.ElideMiddle
        font.pixelSize: theme.fontRow
        color: theme.text
    }
    Row {
        id: buttons
        anchors.verticalCenter: parent.verticalCenter
        x: label.x + label.width + toast.pad
        spacing: toast.pad

        Repeater {
            model: toast.actions

            Text {
                required property int index
                required property string modelData

                objectName: "toastAction"
                text: modelData
                font.pixelSize: theme.fontRow
                font.bold: true
                font.underline: actionMouse.containsMouse
                color: theme.accent

                MouseArea {
                    id: actionMouse
                    anchors.fill: parent
                    anchors.margins: -4
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        toast.dismiss();
                        toast.actionRequested(index);
                    }
                }
                Accessible.role: Accessible.Button
                Accessible.name: modelData
            }
        }
    }
    Text {
        id: close
        anchors.verticalCenter: parent.verticalCenter
        x: buttons.x + toast.actionsRoom
        text: "\u00d7"
        font.pixelSize: theme.fontRow
        color: closeMouse.containsMouse ? theme.text : theme.textDim

        MouseArea {
            id: closeMouse
            anchors.fill: parent
            anchors.margins: -4
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: toast.dismiss()
        }
        Accessible.role: Accessible.Button
        Accessible.name: qsTr("Dismiss")
    }
}
