import QtQuick

// What a link holds, a chip each, removable; and a + that picks more in
// the tree or 3D view (lit while picking).
Flow {
    id: chips

    property var items: []          // [{key, label, sub}]
    property bool editable: true
    property bool picking: false
    //: What to pick, said while picking.
    property string hint: ""
    signal removed(string key)
    //: A chip double-clicked: open what it links (a sketch to edit).
    signal opened(string key)
    signal pickRequested()

    spacing: 4

    Repeater {
        model: chips.items

        Rectangle {
            id: chip
            required property var modelData
            height: theme.fieldHeight
            width: row.implicitWidth + 14
            radius: height / 2
            color: chipTap.pressed ? theme.pressed
                 : chipHover.hovered ? theme.hover : theme.chip
            border.width: 1
            border.color: chipHover.hovered ? theme.textDim : theme.border

            HoverHandler {
                id: chipHover
            }
            TapHandler {
                id: chipTap
                enabled: !!chip.modelData.sketch
                onDoubleTapped: chips.opened(chip.modelData.key)
            }
            NxtToolTip {
                shown: chipHover.hovered && !!chip.modelData.sketch
                       && !removeHover.hovered
                text: qsTr("Double-click to edit the sketch")
            }

            Row {
                id: row
                x: 8
                anchors.verticalCenter: parent.verticalCenter
                spacing: 4
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "◇"
                    font.pixelSize: theme.fontAside
                    color: theme.textDim
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: chip.modelData.label
                    font.pixelSize: theme.fontSmall
                    color: theme.text
                }
                Rectangle {
                    visible: chips.editable
                    anchors.verticalCenter: parent.verticalCenter
                    width: 16
                    height: 16
                    radius: 8
                    color: removeTap.pressed ? theme.pressed
                         : removeHover.hovered ? theme.border : "transparent"
                    Text {
                        anchors.centerIn: parent
                        text: "×"
                        font.pixelSize: theme.fontRow
                        color: removeHover.hovered ? theme.text : theme.textDim
                    }
                    HoverHandler { id: removeHover }
                    TapHandler {
                        id: removeTap
                        onTapped: chips.removed(chip.modelData.key)
                    }
                    NxtToolTip {
                        shown: removeHover.hovered
                        text: qsTr("Remove %1").arg(chip.modelData.label)
                    }
                    Accessible.role: Accessible.Button
                    Accessible.name: qsTr("Remove %1").arg(chip.modelData.label)
                }
            }
        }
    }

    Text {
        visible: chips.items.length === 0 && !chips.editable
        height: theme.fieldHeight
        verticalAlignment: Text.AlignVCenter
        text: qsTr("none")
        font.pixelSize: theme.fontSmall
        font.italic: true
        color: theme.textDim
    }

    Rectangle {
        id: plus
        visible: chips.editable
        width: theme.fieldHeight
        height: theme.fieldHeight
        radius: height / 2
        activeFocusOnTab: true
        color: plusTap.pressed ? theme.pressed
             : chips.picking ? theme.accent
             : plusHover.hovered ? theme.hover : "transparent"
        border.width: plus.activeFocus ? 2 : 1
        border.color: chips.picking || plus.activeFocus ? theme.accent
                    : plusHover.hovered ? theme.textDim : theme.border
        Text {
            anchors.centerIn: parent
            text: chips.picking ? "✓" : "+"
            font.pixelSize: theme.fontRow
            color: chips.picking ? theme.accentText : theme.text
        }
        HoverHandler { id: plusHover }
        TapHandler { id: plusTap; onTapped: chips.pickRequested() }
        Keys.onSpacePressed: chips.pickRequested()
        Keys.onEscapePressed: if (chips.picking) chips.pickRequested()
        NxtToolTip {
            shown: plusHover.hovered
            text: chips.picking ? qsTr("Done picking")
                                : qsTr("Pick in the tree or 3D view")
        }
        Accessible.role: Accessible.Button
        Accessible.name: chips.picking ? qsTr("Done picking") : qsTr("Pick")
    }

    Text {
        visible: chips.picking
        height: theme.fieldHeight
        verticalAlignment: Text.AlignVCenter
        text: chips.hint || qsTr("Pick in the tree or 3D view")
        font.pixelSize: theme.fontAside
        font.italic: true
        color: theme.accent
    }
}
