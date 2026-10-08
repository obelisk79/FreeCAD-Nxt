import QtQuick

// "Bracket › Body › Pocket001": the containers the top of the list is
// inside, once their own rows have scrolled away. Pinned over the top of
// the list; a name scrolls back to its row. Hidden with nothing to say.
Item {
    id: bar

    //: Outermost first: [{row, label}].
    property var crumbs: []
    signal crumbClicked(int row)

    //: Space at each end, and either side of a separator.
    readonly property int pad: theme.rowPad + 4
    readonly property int gap: 6
    readonly property bool overflows: path.width > width - 2 * pad

    height: theme.rowHeight + 4
    visible: crumbs.length > 0
    clip: true

    // Docked, a strip of the panel with a divider under it; in Nxt's
    // overlay a pill, as the header and the rows are there.
    Rectangle {
        anchors.fill: parent
        anchors.margins: theme.overlay ? 2 : 0
        radius: theme.overlay ? 4 : 0
        color: theme.overlay ? theme.pill : theme.background
        border.width: theme.overlay ? 1 : 0
        border.color: theme.pillBorder
    }
    Rectangle {
        anchors.bottom: parent.bottom
        width: parent.width
        height: 1
        visible: !theme.overlay
        color: theme.border
    }

    // Too long to fit, it keeps its end in view: the innermost names are
    // the ones that say where the list is.
    Row {
        id: path
        anchors.verticalCenter: parent.verticalCenter
        x: bar.overflows ? bar.width - bar.pad - width : bar.pad
        spacing: bar.gap

        Repeater {
            model: bar.crumbs

            Row {
                required property int index
                required property var modelData
                readonly property bool innermost:
                    index === bar.crumbs.length - 1

                spacing: bar.gap

                Text {
                    visible: index > 0
                    text: "›"
                    font.pixelSize: theme.fontRow
                    color: theme.textDim
                }
                Text {
                    objectName: "crumb"
                    text: modelData.label
                    font.pixelSize: theme.fontRow
                    font.bold: innermost
                    font.underline: crumbMouse.containsMouse
                    color: innermost ? theme.text : theme.textDim

                    MouseArea {
                        id: crumbMouse
                        anchors.fill: parent
                        anchors.margins: -3
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: bar.crumbClicked(modelData.row)
                    }
                    Accessible.role: Accessible.Link
                    Accessible.name: modelData.label
                }
            }
        }
    }
}
