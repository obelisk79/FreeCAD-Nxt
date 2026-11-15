import QtQuick

// A thin divider between groups of the tool strip; wider and framed in
// edit mode, so it can be picked up.
Item {
    id: separator

    property bool editing: false

    implicitWidth: Math.max(3, Math.round(height * (editing ? 0.4 : 0.3)))

    Rectangle {
        anchors.fill: parent
        visible: separator.editing
        radius: 4
        color: "transparent"
        border.color: theme.border
        border.width: 1
    }

    Rectangle {
        anchors.centerIn: parent
        width: 1
        height: Math.round(parent.height * 0.6)
        color: theme.border
    }
}
