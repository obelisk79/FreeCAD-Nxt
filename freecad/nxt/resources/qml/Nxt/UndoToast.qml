import QtQuick

// What the panel just did, with a way back: "Moved Pocket after Pad ·
// Undo". Shown after a drag, a rename or a tip move - gestures that change
// the model at once, with nothing to confirm - and gone by itself after a
// few seconds, or as soon as it is used or dismissed.
Rectangle {
    id: toast

    property string message: ""
    //: How long it stays, in milliseconds. Longer while pointed at.
    property int stay: 6000
    signal undoRequested()

    function show(text) {
        message = text;
        opacity = 1;
        timer.restart();
    }
    function dismiss() {
        timer.stop();
        opacity = 0;
    }

    visible: opacity > 0
    opacity: 0
    //: Kept clear of the edges of whatever it is shown in.
    property int margin: 10
    //: Space at each end, and between the message and the two buttons.
    readonly property int pad: 12
    // Sized from the parts' own widths, never from this item's width:
    // the message's width was once worked out from the toast's, and the
    // toast's from the message's, and the two settled on nothing - a
    // box a few pixels wide with the text spilling out of it.
    readonly property real room:
        (parent ? parent.width - 2 * margin : 400)
        - undo.implicitWidth - close.implicitWidth - 4 * pad
    implicitWidth: label.width + undo.implicitWidth + close.implicitWidth
                   + 4 * pad
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
    Text {
        id: undo
        objectName: "toastUndo"
        anchors.verticalCenter: parent.verticalCenter
        x: label.x + label.width + toast.pad
        text: qsTr("Undo")
        font.pixelSize: theme.fontRow
        font.bold: true
        font.underline: undoMouse.containsMouse
        color: theme.accent

        MouseArea {
            id: undoMouse
            anchors.fill: parent
            anchors.margins: -4
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: {
                toast.dismiss();
                toast.undoRequested();
            }
        }
        Accessible.role: Accessible.Button
        Accessible.name: qsTr("Undo")
    }
    Text {
        id: close
        anchors.verticalCenter: parent.verticalCenter
        x: undo.x + undo.implicitWidth + toast.pad
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
