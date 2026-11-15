import QtQuick
import Nxt.Controls

// The group open in edit mode: its name, its commands (drag to reorder,
// x to remove), Ungroup and Close. Reordering moves a local copy, so the
// tiles survive the drag; the order is sent to `strip` on release.
Item {
    id: editor

    property int itemSize: 24
    property int iconSize: 16
    readonly property int gap: Math.max(2, Math.round(theme.rowHeight * 0.15))
    readonly property int moveMs: 120
    property bool dragging: false

    implicitHeight: itemSize + 2 * gap

    function sync() {
        if (dragging)
            return;
        members.clear();
        for (const member of strip.groupMembers)
            members.append(member);
        groupName.text = strip.groupName;
    }

    function order() {
        const keys = [];
        for (let i = 0; i < members.count; ++i)
            keys.push(members.get(i).key);
        return keys;
    }

    Component.onCompleted: sync()

    Connections {
        target: strip
        function onGroupChanged() { editor.sync() }
    }

    ListModel { id: members }

    Rectangle {
        anchors.fill: parent
        radius: 4
        color: "transparent"
        border.color: theme.accent
        border.width: 1
    }

    Row {
        x: editor.gap
        anchors.verticalCenter: parent.verticalCenter
        spacing: editor.gap

        TextField {
            id: groupName
            anchors.verticalCenter: parent.verticalCenter
            width: Math.round(theme.rowHeight * 6)
            placeholder: qsTr("Group name")
            onAccepted: strip.renameGroup(text)
            onDismissed: text = strip.groupName
            Connections {
                target: groupName.input
                function onActiveFocusChanged() {
                    if (!groupName.input.activeFocus)
                        strip.renameGroup(groupName.text);
                }
            }
        }

        ListView {
            id: list
            anchors.verticalCenter: parent.verticalCenter
            width: contentWidth
            height: editor.itemSize
            orientation: ListView.Horizontal
            spacing: editor.gap
            interactive: false
            model: members

            moveDisplaced: Transition {
                NumberAnimation { properties: "x"; duration: editor.moveMs }
            }

            delegate: Rectangle {
                id: member

                required property int index
                required property string key
                required property string text
                required property string icon
                property point pressedAt

                width: content.width + 2 * editor.gap + close.width
                height: editor.itemSize
                radius: 4
                color: grip.pressed ? theme.pressed
                                    : grip.containsMouse ? theme.hover
                                                         : "transparent"
                border.color: theme.border
                border.width: 1

                Row {
                    id: content
                    x: editor.gap
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: editor.gap

                    Image {
                        visible: member.icon !== ""
                        width: editor.iconSize
                        height: editor.iconSize
                        sourceSize: Qt.size(editor.iconSize * 2,
                                            editor.iconSize * 2)
                        source: member.icon
                        mipmap: true
                    }

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: member.text.replace(/&/g, "")
                        color: theme.text
                        font.pixelSize: theme.fontSmall
                    }
                }

                MouseArea {
                    id: grip
                    anchors.fill: parent
                    hoverEnabled: true
                    preventStealing: true
                    cursorShape: editor.dragging ? Qt.ClosedHandCursor
                                                 : Qt.OpenHandCursor
                    onPressed: (mouse) => member.pressedAt = Qt.point(mouse.x, mouse.y)
                    onPositionChanged: (mouse) => {
                        if (!pressed)
                            return;
                        if (!editor.dragging) {
                            if (Math.hypot(mouse.x - member.pressedAt.x,
                                           mouse.y - member.pressedAt.y)
                                    < Qt.styleHints.startDragDistance)
                                return;
                            editor.dragging = true;
                        }
                        const at = mapToItem(list.contentItem, mouse.x, mouse.y);
                        const to = list.indexAt(at.x, list.height / 2);
                        // Read before moving: the move renumbers this tile.
                        const from = member.index;
                        if (to >= 0 && to !== from)
                            members.move(from, to, 1);
                    }
                    onReleased: {
                        if (!editor.dragging)
                            return;
                        editor.dragging = false;
                        strip.setMemberOrder(editor.order());
                    }
                }

                IconButton {
                    id: close
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    width: Math.round(editor.itemSize * 0.6)
                    iconScale: 0.6
                    tip: qsTr("Remove from the group")
                    paint: Glyphs.remove
                    onClicked: strip.removeMember(member.index)
                }
            }
        }

        TextButton {
            anchors.verticalCenter: parent.verticalCenter
            text: qsTr("Ungroup")
            onClicked: strip.ungroup()
        }

        TextButton {
            anchors.verticalCenter: parent.verticalCenter
            text: qsTr("Close")
            onClicked: strip.editGroup(-1)
        }
    }
}
