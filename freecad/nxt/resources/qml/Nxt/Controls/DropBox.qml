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
    // Inside a field it still reads as a button: a chip's fill, and the
    // focus ring a field has.
    color: tap.pressed ? theme.pressed
         : hover.hovered && enabled ? theme.hover
         : box.inset ? theme.chip
         : theme.overlay ? theme.chip : theme.background
    border.width: activeFocus ? 2 : box.inset ? 0 : 1
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
        color: hover.hovered || box.activeFocus ? theme.text : theme.textDim
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
    // As a combo box opens: Space, Return, Down (Alt+Down too) and F4.
    Keys.onSpacePressed: box.opened()
    Keys.onReturnPressed: box.opened()
    Keys.onEnterPressed: box.opened()
    Keys.onDownPressed: box.opened()
    Keys.onPressed: function (event) {
        if (event.key === Qt.Key_F4) {
            box.opened();
            event.accepted = true;
        }
    }

    Accessible.role: Accessible.ComboBox
    Accessible.name: box.text
}
