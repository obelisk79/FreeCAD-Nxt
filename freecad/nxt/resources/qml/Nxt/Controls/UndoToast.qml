import QtQuick

// What Nxt just did, with a way back: "Moved Pocket after Pad · Undo".
// Fades after a few seconds unless `sticky`.
Rectangle {
    id: toast

    property string message: ""
    //: Button labels, in order.
    property var actions: []
    property bool sticky: false
    //: Milliseconds; longer while hovered.
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
    //: Host width; kept current by the host.
    property real available: 400
    property int margin: 10
    readonly property int pad: 12
    // Sized from the parts' own widths, never this item's: a circular binding
    // collapsed it to a few pixels.
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
                opacity: actionMouse.pressed ? 0.6 : 1.0
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
        opacity: closeMouse.pressed ? 0.6 : 1.0

        MouseArea {
            id: closeMouse
            anchors.fill: parent
            anchors.margins: -4
            hoverEnabled: true
            onClicked: toast.dismiss()
        }
        Accessible.role: Accessible.Button
        Accessible.name: qsTr("Dismiss")
    }
}
