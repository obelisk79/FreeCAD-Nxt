import QtQuick
import Nxt.Controls

// A row of choices, one current: the workbench selector FreeCAD shows as
// tabs. Each choice is its icon, or its name if it has none; the name is
// the tooltip. `chosen` is announced a frame after the click is drawn.
Item {
    id: bar

    property int size: 24
    property int iconSize: 16
    property var choices: []
    property int current: -1
    //: Framed, and its clicks left to the strip's hand.
    property bool editing: false
    readonly property int padding: Math.round((size - iconSize) / 2)
    readonly property int announceMs: 30

    signal chosen(int index)

    implicitWidth: choiceRow.implicitWidth
    implicitHeight: size

    Rectangle {
        anchors.fill: parent
        visible: bar.editing
        radius: 4
        color: "transparent"
        border.color: theme.border
        border.width: 1
    }

    Row {
        id: choiceRow
        spacing: 1

        Repeater {
            model: bar.choices.length

            delegate: Item {
                id: choice

                required property int index
                readonly property var entry: bar.choices[index]
                readonly property bool isCurrent: index === bar.current

                width: (entry.icon !== "" ? bar.iconSize : label.implicitWidth)
                       + 2 * bar.padding
                height: bar.size

                Rectangle {
                    anchors.fill: parent
                    radius: 4
                    color: press.pressed || choice.isCurrent ? theme.pressed
                                                             : theme.hover
                    border.color: choice.isCurrent ? theme.accent : "transparent"
                    border.width: choice.isCurrent ? 1 : 0
                    visible: choice.isCurrent || hover.hovered || press.pressed
                }

                Image {
                    visible: choice.entry.icon !== ""
                    anchors.centerIn: parent
                    width: bar.iconSize
                    height: bar.iconSize
                    sourceSize: Qt.size(bar.iconSize * 2, bar.iconSize * 2)
                    source: choice.entry.icon
                    smooth: true
                    mipmap: true
                }

                Text {
                    id: label
                    visible: choice.entry.icon === ""
                    anchors.centerIn: parent
                    text: choice.entry.text
                    color: theme.text
                    font.pixelSize: theme.fontSmall
                }

                HoverHandler { id: hover }

                MouseArea {
                    id: press
                    anchors.fill: parent
                    enabled: bar.enabled && !bar.editing && !choice.isCurrent
                    onClicked: announce.restart()
                }

                Timer {
                    id: announce
                    interval: bar.announceMs
                    onTriggered: bar.chosen(choice.index)
                }

                NxtToolTip {
                    shown: hover.hovered && !press.pressed && !bar.editing
                    text: choice.entry.text
                }

                Accessible.role: Accessible.PageTab
                Accessible.name: choice.entry.text
                Accessible.selected: choice.isCurrent
            }
        }
    }
}
