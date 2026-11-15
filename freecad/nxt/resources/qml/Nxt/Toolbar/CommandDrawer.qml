import QtQuick
import Nxt.Controls

// The tool strip's drawer in edit mode: FreeCAD's commands, searched as
// typed (letters in order: "pdpad" finds Pad) and filtered by workbench.
// Double-click adds to the end of the strip; dragging places it. Context:
// `strip` and `theme`; the owner handles drags through `dragStarted`.
Item {
    id: drawer

    property int itemSize: 24
    property int iconSize: 16
    property int rows: 4
    readonly property int gap: Math.max(2, Math.round(theme.rowHeight * 0.15))
    readonly property int cellWidth: Math.round(theme.rowHeight * 8)
    readonly property real placedOpacity: 0.45
    //: The keys the separator and New group tiles drag as.
    readonly property string separatorKey: "|"
    readonly property string groupKey: "+group"

    //: (key, the tile under the pointer, the pointer in the tile)
    signal dragStarted(string key, Item tile, point grip)
    signal dragMoved(Item tile, point at)
    signal dragEnded()

    implicitHeight: header.height + gap + grid.height

    function focusSearch() { search.input.forceActiveFocus() }

    // One draggable tile: an icon and a name.
    component Tile: Rectangle {
        id: tile

        property string key: ""
        property string label: ""
        property string icon: ""
        property string tip: ""
        property bool placed: false
        property point pressedAt
        property bool dragging: false

        width: drawer.cellWidth - drawer.gap
        height: drawer.itemSize
        radius: 4
        color: hand.containsMouse && !placed ? theme.hover : "transparent"
        border.color: theme.border
        border.width: 1
        opacity: placed ? drawer.placedOpacity : 1

        Row {
            x: drawer.gap
            anchors.verticalCenter: parent.verticalCenter
            spacing: drawer.gap

            Image {
                visible: tile.icon !== ""
                width: drawer.iconSize
                height: drawer.iconSize
                sourceSize: Qt.size(drawer.iconSize * 2, drawer.iconSize * 2)
                source: tile.icon
                mipmap: true
            }

            Text {
                anchors.verticalCenter: parent.verticalCenter
                width: tile.width - drawer.iconSize - 3 * drawer.gap
                text: tile.label
                elide: Text.ElideRight
                color: theme.text
                font.pixelSize: theme.fontSmall
            }
        }

        MouseArea {
            id: hand
            anchors.fill: parent
            hoverEnabled: true
            enabled: !tile.placed
            preventStealing: true
            cursorShape: tile.dragging ? Qt.ClosedHandCursor : Qt.OpenHandCursor
            onPressed: (mouse) => tile.pressedAt = Qt.point(mouse.x, mouse.y)
            onPositionChanged: (mouse) => {
                if (!pressed)
                    return;
                if (!tile.dragging) {
                    if (Math.hypot(mouse.x - tile.pressedAt.x,
                                   mouse.y - tile.pressedAt.y)
                            < Qt.styleHints.startDragDistance)
                        return;
                    tile.dragging = true;
                    drawer.dragStarted(tile.key, tile, tile.pressedAt);
                }
                drawer.dragMoved(tile, Qt.point(mouse.x, mouse.y));
            }
            onReleased: {
                if (tile.dragging)
                    drawer.dragEnded();
                tile.dragging = false;
            }
            onCanceled: {
                if (tile.dragging)
                    drawer.dragEnded();
                tile.dragging = false;
            }
            onDoubleClicked: {
                if (tile.key === drawer.separatorKey)
                    strip.appendSeparator();
                else if (tile.key === drawer.groupKey)
                    strip.insertGroup(-1);
                else
                    strip.appendCommand(tile.key);
            }
        }

        NxtToolTip {
            shown: hand.containsMouse && !hand.pressed
            text: tile.placed ? qsTr("Already on the toolbar")
                              : (tile.tip || tile.label)
        }
    }

    Row {
        id: header
        width: parent.width
        spacing: drawer.gap

        TextField {
            id: search
            width: drawer.cellWidth
            placeholder: qsTr("Search commands")
            clearable: true
            onDismissed: text === "" ? strip.setEditing(false) : text = ""
        }

        Tile {
            key: drawer.separatorKey
            label: qsTr("Separator")
            tip: qsTr("Drag a separator onto the toolbar")
            width: Math.round(drawer.cellWidth / 2)
            height: search.height
        }

        Tile {
            key: drawer.groupKey
            label: qsTr("New group")
            tip: qsTr("Drag onto the toolbar, then drop commands on it")
            width: Math.round(drawer.cellWidth / 2)
            height: search.height
        }

        Flow {
            width: parent.width - search.width - drawer.cellWidth
                   - fileButtons.width - 4 * drawer.gap
            spacing: drawer.gap

            Repeater {
                model: strip.filters

                delegate: Rectangle {
                    id: chip
                    required property var modelData
                    readonly property bool chosen: strip.filter === modelData.id
                    width: chipLabel.implicitWidth + 2 * drawer.gap
                    height: theme.fieldHeight
                    radius: height / 2
                    color: chosen ? theme.pressed
                                  : chipHover.hovered ? theme.hover : "transparent"
                    border.color: chosen ? theme.accent : theme.border
                    border.width: 1

                    Text {
                        id: chipLabel
                        anchors.centerIn: parent
                        text: chip.modelData.label
                        color: theme.text
                        font.pixelSize: theme.fontSmall
                    }

                    HoverHandler { id: chipHover }
                    TapHandler { onTapped: strip.setFilter(chip.modelData.id) }
                    Accessible.role: Accessible.RadioButton
                    Accessible.name: chip.modelData.label
                    Accessible.checked: chip.chosen
                }
            }
        }

        // Every workbench's layout, to another computer or a backup.
        Row {
            id: fileButtons
            spacing: drawer.gap

            TextButton {
                text: qsTr("Import…")
                onClicked: strip.importLayouts()
            }

            TextButton {
                text: qsTr("Export…")
                onClicked: strip.exportLayouts()
            }
        }
    }

    Connections {
        target: search.input
        function onTextChanged() { strip.setQuery(search.text) }
    }

    GridView {
        id: grid
        y: header.height + drawer.gap
        width: parent.width
        height: drawer.rows * cellHeight
        cellWidth: drawer.cellWidth
        cellHeight: drawer.itemSize + drawer.gap
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        model: strip.catalogModel

        delegate: Tile {
            required property var model
            key: model.key
            label: model.text
            icon: model.icon
            tip: model.tip
            placed: model.placed
        }

        Text {
            anchors.centerIn: parent
            visible: strip.loading || grid.count === 0
            text: strip.loading ? qsTr("Reading commands…")
                                : qsTr("No command matches")
            color: theme.textDim
            font.pixelSize: theme.fontSmall
        }
    }
}
