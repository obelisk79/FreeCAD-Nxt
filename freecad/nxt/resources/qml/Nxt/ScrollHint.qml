import QtQuick

// Minimal scrollbar. Appears while the view moves, fades out after. Written
// by hand so the panel has no dependency on whichever QtQuick.Controls style
// the host application happens to have loaded.
Item {
    id: root

    property Flickable target

    anchors.fill: target ? target : undefined
    visible: target && target.contentHeight > target.height

    Rectangle {
        id: bar
        anchors.right: parent.right
        anchors.rightMargin: 2
        width: 4
        radius: 2
        color: theme.textDim

        y: root.target
           ? root.target.visibleArea.yPosition * root.target.height
           : 0
        height: root.target
                ? Math.max(24, root.target.visibleArea.heightRatio * root.target.height)
                : 0

        opacity: (root.target && root.target.moving) ? 0.55 : 0.0
        Behavior on opacity { NumberAnimation { duration: 320 } }
    }
}
