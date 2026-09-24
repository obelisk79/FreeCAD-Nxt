import QtQuick
import Nxt

// The Property Inspector's contents: every property of the selection, laid out
// from what the objects say about themselves (see inspector.py).
//
// Groups are FreeCAD's own and sit on tinted cards. Inside one, compact
// editors take half a row and wide ones a full row, so a group reads as a
// short form rather than a long list.
Rectangle {
    id: root
    color: theme.background
    implicitWidth: 330
    implicitHeight: 480

    readonly property int pad: 8
    readonly property int gap: 8

    // --- filter and Data / View ----------------------------------------- #

    Row {
        id: top
        x: root.pad
        y: root.pad
        width: root.width - 2 * root.pad
        spacing: root.gap
        height: theme.fieldHeight

        TextField {
            id: filter
            width: parent.width - tabs.width - root.gap
            placeholder: qsTr("Filter")
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
                // Keys to the bridge; labels to the user.
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

    // --- the groups ------------------------------------------------------- #

    ListView {
        id: groups
        anchors.top: top.bottom
        anchors.topMargin: root.gap
        anchors.bottom: parent.bottom
        width: root.width
        clip: true
        spacing: root.gap
        boundsBehavior: Flickable.StopAtBounds
        model: inspector.groups
        bottomMargin: root.pad

        delegate: Rectangle {
            id: group
            required property var modelData
            property bool opened: modelData.open

            x: root.pad
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
                    spacing: 5
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
                        color: theme.text
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
                        text: group.modelData.items.length
                        font.pixelSize: theme.fontSmall
                        color: theme.textDim
                    }
                }

                // Half-width items pair up; a wide one takes the row.
                Flow {
                    visible: group.opened
                    width: parent.width
                    spacing: root.gap

                    Repeater {
                        model: group.opened ? group.modelData.items.length
                                            : 0

                        Column {
                            id: item
                            required property int index
                            readonly property var spec:
                                group.modelData.items[index]

                            width: item.spec.wide
                                   ? groupBody.width
                                   : (groupBody.width - root.gap) / 2
                            spacing: 2

                            Row {
                                spacing: 4
                                Text {
                                    text: item.spec.label
                                    font.pixelSize: theme.fontAside
                                    color: theme.textDim
                                    width: Math.min(implicitWidth,
                                                    item.width - 12)
                                    elide: Text.ElideRight
                                }
                                Text {
                                    // An expression drives this value.
                                    visible: item.spec.expression.length > 0
                                    text: "ƒ"
                                    font.pixelSize: theme.fontAside
                                    font.italic: true
                                    font.bold: true
                                    color: theme.textDim
                                }
                            }

                            ValueEditor {
                                width: item.width
                                spec: item.spec
                                onEdited: function (value) {
                                    inspector.setValue(item.spec.name, value,
                                                  item.spec.unit);
                                }
                                onPartEdited: function (path, text) {
                                    inspector.setPart(item.spec.name, path, text);
                                }
                                onColourRequested:
                                    inspector.pickColour(item.spec.name,
                                                    item.spec.text)
                                onNativeRequested:
                                    inspector.editNative(item.spec.name)
                            }
                        }
                    }
                }
            }
        }
    }

    Text {
        anchors.centerIn: groups
        visible: groups.count === 0
        text: inspector.title.length === 0 ? qsTr("Select an object")
                                      : qsTr("No matching properties")
        font.pixelSize: theme.fontSmall
        font.italic: true
        color: theme.textDim
    }
}
