import QtQuick

// "Isolated: Pad   [Exit]" - the isolate mode's notice (isolate.py).
Rectangle {
    id: notice

    property string text: ""
    signal exitRequested()

    implicitWidth: row.implicitWidth + 24
    implicitHeight: Math.round(theme.rowHeight * 1.25)
    radius: 5
    color: theme.surface
    border.width: 1
    border.color: theme.accent

    Row {
        id: row
        anchors.centerIn: parent
        spacing: 12

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: notice.text
            font.pixelSize: theme.fontSmall
            font.bold: true
            color: theme.text
        }

        Rectangle {
            id: exit
            anchors.verticalCenter: parent.verticalCenter
            width: exitLabel.implicitWidth + 16
            height: Math.round(notice.height * 0.7)
            radius: 3
            color: exitMouse.pressed ? Qt.darker(theme.accent, 1.15)
                 : exitMouse.containsMouse ? theme.accent
                 : "transparent"
            border.width: 1
            border.color: theme.accent

            Text {
                id: exitLabel
                anchors.centerIn: parent
                text: qsTr("Exit")
                font.pixelSize: theme.fontSmall
                color: exitMouse.containsMouse ? theme.accentText
                                               : theme.text
            }

            MouseArea {
                id: exitMouse
                anchors.fill: parent
                hoverEnabled: true
                onClicked: notice.exitRequested()
            }

            Accessible.role: Accessible.Button
            Accessible.name: qsTr("Exit isolation")
        }
    }
}
