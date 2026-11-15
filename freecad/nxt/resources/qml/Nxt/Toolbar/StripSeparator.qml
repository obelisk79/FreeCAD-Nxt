import QtQuick

// A thin divider between groups of the tool strip.
Item {
    implicitWidth: Math.max(3, Math.round(height * 0.3))

    Rectangle {
        anchors.centerIn: parent
        width: 1
        height: Math.round(parent.height * 0.6)
        color: theme.border
    }
}
