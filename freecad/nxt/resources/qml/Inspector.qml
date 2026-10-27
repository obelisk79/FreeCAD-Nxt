import QtQuick
import Nxt.Controls
import Nxt.Inspector

// The Property Inspector: every property of the selection (inspector.py),
// in FreeCAD's groups on tinted cards; compact editors take half a row.
Rectangle {
    id: root
    implicitWidth: 330
    implicitHeight: 480

    //: Inside a task dialog: no filter or tabs, no background of its own.
    property bool bare: false
    //: The cards, whose height the task dialog sizes itself to.
    readonly property alias cards: groups
    //: Room the warning above the cards takes.
    readonly property real noticeHeight: alert.visible
                                         ? alert.height + root.gap : 0
    color: bare ? "transparent" : theme.background

    readonly property int pad: 8
    readonly property int gap: 8
    //: "Everything else", behind a template's cards: closed until asked
    //: for, or while filtering.
    property bool restOpened: false
    readonly property bool restShown: restOpened || filter.text.length > 0
    //: Names on the left, editors beside them, alike down every card.
    readonly property real labelWidth: Math.min(96, Math.round(width * 0.28))


    Row {
        id: top
        x: root.pad
        y: root.pad
        width: root.width - 2 * root.pad
        spacing: root.gap
        height: root.bare ? 0 : theme.fieldHeight
        visible: !root.bare

        TextField {
            id: filter
            width: parent.width - tabs.width - root.gap
            placeholder: qsTr("Filter")
            clearable: true
            onEdited: function (value) { inspector.setFilter(value); }
            onDismissed: {
                filter.text = "";
                inspector.setFilter("");
            }
        }

        Row {
            id: tabs
            spacing: 2

            Repeater {
                model: [{key: "Data", label: qsTr("Data")},
                        {key: "View", label: qsTr("View")}]

                Chip {
                    required property var modelData
                    text: modelData.label
                    active: inspector.tab === modelData.key
                    onClicked: inspector.setTab(modelData.key)
                }
            }
        }
    }


    // What is wrong with the object: its recompute failed, or a pick it
    // cannot take.
    Notice {
        id: alert
        anchors.top: top.bottom
        anchors.topMargin: root.bare ? 0 : root.gap
        x: root.pad
        width: root.width - 2 * root.pad
        text: inspector.notice || ""
    }

    ListView {
        id: groups
        anchors.top: alert.visible ? alert.bottom : top.bottom
        anchors.topMargin: root.bare && !alert.visible ? 0 : root.gap
        anchors.bottom: parent.bottom
        width: root.width
        clip: true
        spacing: root.gap
        boundsBehavior: Flickable.StopAtBounds
        model: inspector.groups
        // In a task dialog every card is made, so its height is known.
        cacheBuffer: root.bare ? 100000 : 320
        bottomMargin: root.pad

        delegate: Item {
            id: slot
            required property var modelData
            readonly property bool rest: !!modelData.rest
            readonly property bool tucked: !!modelData.behind && !root.restShown

            width: root.width
            height: slot.tucked ? (slot.rest ? restHeading.height + 4 : 0)
                                : group.y + group.height
            visible: height > 0

            // Behind a template's cards, the generic groups it left.
            Row {
                id: restHeading
                visible: slot.rest
                x: root.pad + 2
                y: 2
                spacing: 5
                Disclosure {
                    anchors.verticalCenter: parent.verticalCenter
                    expanded: root.restShown
                    onToggled: root.restOpened = !root.restOpened
                }
                Text {
                    text: qsTr("Everything else")
                    font.pixelSize: theme.fontAside
                    font.capitalization: Font.AllUppercase
                    font.letterSpacing: 0.6
                    font.underline: restHover.hovered
                    color: theme.textDim
                    HoverHandler {
                        id: restHover
                    }
                    TapHandler { onTapped: root.restOpened = !root.restOpened }
                }
                Text {
                    visible: !root.restShown
                    text: slot.modelData.restCount || ""
                    font.pixelSize: theme.fontAside
                    color: theme.textDim
                }
            }

        Rectangle {
            id: group
            readonly property var modelData: slot.modelData
            readonly property bool headed: modelData.heading !== false
            property bool opened: modelData.open || !headed

            visible: !slot.tucked
            x: root.pad
            y: slot.rest ? restHeading.height + 6 : 0
            width: root.width - 2 * root.pad
            height: groupBody.implicitHeight + 2 * root.pad
            radius: 4
            color: theme.surface

            Column {
                id: groupBody
                x: root.pad
                y: root.pad
                width: parent.width - 2 * root.pad
                spacing: root.gap

                Row {
                    visible: group.headed
                    spacing: 5
                    width: parent.width
                    Disclosure {
                        anchors.verticalCenter: parent.verticalCenter
                        expanded: group.opened
                        onToggled: {
                            group.opened = !group.opened;
                            inspector.setGroupOpen(group.modelData.name,
                                              group.opened);
                        }
                    }
                    Text {
                        text: group.modelData.name
                        font.pixelSize: theme.fontSmall
                        font.bold: true
                        font.underline: titleHover.hovered
                        color: theme.text
                        HoverHandler {
                            id: titleHover
                        }
                        TapHandler {
                            onTapped: {
                                group.opened = !group.opened;
                                inspector.setGroupOpen(group.modelData.name,
                                                  group.opened);
                            }
                        }
                    }
                    Text {
                        visible: !group.opened
                        width: parent.width - x
                        horizontalAlignment: group.modelData.summary
                                             ? Text.AlignRight : Text.AlignLeft
                        elide: Text.ElideRight
                        text: group.modelData.summary
                              || group.modelData.count
                              || group.modelData.items.length
                        font.pixelSize: theme.fontSmall
                        color: theme.textDim
                    }
                }

                Column {
                    visible: group.opened
                    width: parent.width
                    spacing: root.gap

                    Repeater {
                        model: group.opened ? group.modelData.items : []
                        InspectorField {
                            required property var modelData
                            spec: modelData
                            width: groupBody.width
                            labelWidth: root.labelWidth
                        }
                    }
                }

                // A template's columns, one per side of an extrusion,
                // one under the other; headed when there are two.
                Repeater {
                    model: group.opened && group.modelData.columns
                           ? group.modelData.columns : []

                    Column {
                        id: column
                        required property var modelData
                        width: groupBody.width
                        spacing: root.gap

                        Text {
                            visible: column.modelData.title.length > 0
                            text: column.modelData.title
                            font.pixelSize: theme.fontAside
                            font.bold: true
                            color: theme.textDim
                        }
                        Repeater {
                            model: column.modelData.items
                            InspectorField {
                                required property var modelData
                                spec: modelData
                                width: column.width
                                labelWidth: root.labelWidth
                            }
                        }
                    }
                }

                Column {
                    visible: group.opened && !!group.modelData.after
                             && group.modelData.after.length > 0
                    width: parent.width
                    spacing: root.gap

                    Repeater {
                        model: group.opened && group.modelData.after
                               ? group.modelData.after : []
                        InspectorField {
                            required property var modelData
                            spec: modelData
                            width: groupBody.width
                            labelWidth: root.labelWidth
                        }
                    }
                }

                Text {
                    visible: group.opened && !!group.modelData.hint
                    width: parent.width
                    text: group.modelData.hint || ""
                    wrapMode: Text.Wrap
                    font.pixelSize: theme.fontAside
                    color: theme.textDim
                }
            }
        }
        }
    }

    Text {
        anchors.centerIn: groups
        visible: groups.count === 0 && !root.bare
        text: inspector.title.length === 0 ? qsTr("Select an object")
                                      : qsTr("No matching properties")
        font.pixelSize: theme.fontSmall
        font.italic: true
        color: theme.textDim
    }
}
