import QtQuick

// A warning in a task or the inspector: amber text on an amber wash, and
// an optional button that offers a way out.
Rectangle {
    id: notice

    property string text: ""
    //: The offered fix's label; none when empty.
    property string action: ""
    signal acted()

    readonly property color ink: theme.warning

    visible: notice.text.length > 0
    implicitHeight: visible ? body.implicitHeight + 24 : 0
    radius: 6
    color: Qt.rgba(ink.r, ink.g, ink.b, 0.14)
    border.width: 1
    border.color: ink

    Column {
        id: body
        x: 12
        y: 12
        width: parent.width - 24
        spacing: 8

        Text {
            width: parent.width
            wrapMode: Text.WordWrap
            text: notice.text
            color: notice.ink
            font.pixelSize: theme.fontSmall
        }
        Rectangle {
            visible: notice.action.length > 0
            height: theme.fieldHeight
            width: label.implicitWidth + 20
            radius: 4
            color: area.pressed ? Qt.rgba(notice.ink.r, notice.ink.g,
                                          notice.ink.b, 0.3)
                 : area.containsMouse ? theme.hover : "transparent"
            border.width: 1
            border.color: notice.ink
            Text {
                id: label
                anchors.centerIn: parent
                text: notice.action
                color: notice.ink
                font.pixelSize: theme.fontSmall
            }
            MouseArea {
                id: area
                anchors.fill: parent
                hoverEnabled: true
                onClicked: notice.acted()
            }
        }
    }
}
