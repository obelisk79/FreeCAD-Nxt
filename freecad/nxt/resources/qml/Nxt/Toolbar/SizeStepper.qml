import QtQuick
import Nxt.Controls

// An icon size, stepped through `sizes`: minus, the size, plus.
Row {
    id: stepper

    property int size: 24
    property var sizes: []
    property string label: ""
    readonly property int place: sizes.indexOf(size)

    signal picked(int size)

    spacing: Math.max(2, Math.round(theme.rowHeight * 0.15))

    Text {
        visible: stepper.label !== ""
        anchors.verticalCenter: parent.verticalCenter
        text: stepper.label
        color: theme.textDim
        font.pixelSize: theme.fontSmall
    }

    TextButton {
        text: "\u2212"
        Accessible.name: qsTr("Smaller icons")
        onClicked: if (stepper.place > 0)
                       stepper.picked(stepper.sizes[stepper.place - 1])
    }

    Text {
        anchors.verticalCenter: parent.verticalCenter
        text: qsTr("%1 px").arg(stepper.size)
        color: theme.text
        font.pixelSize: theme.fontSmall
    }

    TextButton {
        text: "+"
        Accessible.name: qsTr("Larger icons")
        onClicked: if (stepper.place >= 0
                           && stepper.place < stepper.sizes.length - 1)
                       stepper.picked(stepper.sizes[stepper.place + 1])
    }
}
