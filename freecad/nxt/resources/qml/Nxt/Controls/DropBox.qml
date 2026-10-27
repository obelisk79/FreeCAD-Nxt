import QtQuick

// A drop-down's closed face, drawn as a field: the chosen label and a
// dart. `opened` asks the owner for the list (ChoiceList).
Rectangle {
    id: box

    property string text: ""
    property bool active: false
    //: Inside another field: no frame of its own, a divider after it.
    property bool inset: false
    signal opened()

    implicitWidth: label.implicitWidth + dart.implicitWidth + 18
    implicitHeight: theme.fieldHeight
    radius: 3
    activeFocusOnTab: enabled
    color: tap.pressed ? theme.pressed
         : box.inset ? (hover.hovered ? theme.hover : "transparent")
         : hover.hovered && enabled ? theme.hover
         : theme.overlay ? theme.chip : theme.background
    border.width: box.inset ? 0 : activeFocus ? 2 : 1
    border.color: box.active || activeFocus ? theme.accent
                : hover.hovered ? theme.textDim : theme.border
    opacity: enabled ? 1.0 : 0.5

    Text {
        id: label
        x: 7
        width: parent.width - dart.width - 16
        anchors.verticalCenter: parent.verticalCenter
        text: box.text
        elide: Text.ElideRight
        font.pixelSize: theme.fontSmall
        color: box.inset ? theme.textDim : theme.text
    }
    Text {
        id: dart
        anchors.right: parent.right
        anchors.rightMargin: 6
        anchors.verticalCenter: parent.verticalCenter
        text: "▾"
        font.pixelSize: theme.fontSmall
        color: theme.textDim
    }
    Rectangle {
        visible: box.inset
        anchors.right: parent.right
        width: 1
        height: parent.height - 8
        anchors.verticalCenter: parent.verticalCenter
        color: theme.border
    }

    HoverHandler {
        id: hover
        enabled: box.enabled
    }
    TapHandler {
        id: tap
        enabled: box.enabled
        onTapped: box.opened()
    }
    Keys.onSpacePressed: box.opened()
    Keys.onReturnPressed: box.opened()

    Accessible.role: Accessible.ComboBox
    Accessible.name: box.text
}
