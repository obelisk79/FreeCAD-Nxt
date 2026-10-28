import QtQuick

// A small worded button: hover and press shade it at once.
Rectangle {
    id: button

    property alias text: label.text
    //: Accent text, for the action the form is for.
    property bool primary: false
    readonly property bool hovered: hover.hovered

    signal clicked()

    implicitWidth: label.implicitWidth + 2 * Math.round(theme.fieldHeight / 3)
    implicitHeight: theme.fieldHeight
    radius: 3
    color: press.pressed ? theme.pressed : hover.hovered ? theme.hover
                                                         : "transparent"
    Accessible.role: Accessible.Button
    Accessible.name: label.text

    Text {
        id: label
        anchors.centerIn: parent
        font.pixelSize: theme.fontSmall
        color: button.primary ? theme.link : theme.text
    }

    HoverHandler { id: hover }
    TapHandler {
        id: press
        onTapped: button.clicked()
    }
}
