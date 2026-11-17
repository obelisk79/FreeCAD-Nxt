import QtQuick

// A thin divider between groups of a tool strip, across a row (top) or a
// column (sides); wider and framed in edit mode, so it can be picked up.
Item {
    id: separator

    property bool across: true
    property bool editing: false
    property int size: 24
    readonly property int thickness: Math.max(3, Math.round(
        size * (editing ? 0.4 : 0.3)))

    implicitWidth: across ? thickness : size
    implicitHeight: across ? size : thickness

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
        width: separator.across ? 1 : Math.round(separator.size * 0.6)
        height: separator.across ? Math.round(separator.size * 0.6) : 1
        color: theme.border
    }
}
