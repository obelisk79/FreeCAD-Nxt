import QtQuick
import Qt.labs.qmlmodels
import Nxt.Controls
import Nxt.Toolbar

// Nxt's tool strip: every command of FreeCAD's shown toolbars in one row,
// wrapping when the window is narrow. Context: `strip` (toolbars/bridge.py)
// and `theme`. Rows carry kind, text, tip, enabled, checkable, checked,
// icon, dropdown, choices and current.
//
// Edit mode (the pencil at the end): items are dragged to reorder, and
// dropped outside the strip (or on the drawer) or closed with their x to
// remove. The drawer below adds commands and separators. Escape or Done
// leaves it. Each finished drag is saved by the bridge.
Item {
    id: root

    readonly property int gap: Math.max(1, Math.round(theme.rowHeight * 0.08))
    readonly property int padding: Math.max(2, Math.round(strip.iconSize * 0.2))
    readonly property int itemSize: strip.iconSize + 2 * padding
    //: How far past the strip's items a drop still lands on the strip.
    readonly property int removeMargin: Math.round(itemSize / 2)
    readonly property int moveMs: 120
    readonly property bool editing: strip.editing

    // The drag in progress: a strip row, or a drawer key not placed yet.
    property bool dragging: false
    property int dragIndex: -1
    property string pendingKey: ""
    property Item ghostSource: null
    property point grip
    property point pointer
    //: The group a command will drop into, or -1.
    property int intoGroup: -1
    //: Where on a group, as a fraction of its width, a drop goes in.
    readonly property real intoFrom: 0.25
    readonly property real intoTo: 0.75
    readonly property bool outside: dragging
        && (pointer.y < flow.y - removeMargin
            || pointer.y > flow.y + flow.height + removeMargin)

    implicitHeight: Math.max(flow.implicitHeight, controls.height) + 2 * gap
                    + (editing ? drawer.implicitHeight + gap : 0)
                    + (groupEditor.visible ? groupEditor.implicitHeight + gap
                                           : 0)

    onEditingChanged: if (editing) drawer.focusSearch()
    Keys.onEscapePressed: strip.setEditing(false)

    function delegateAt(x, y) {
        const child = flow.childAt(x - flow.x, y - flow.y);
        return child && child.index !== undefined ? child : null;
    }

    function delegateOf(index) {
        for (let i = 0; i < flow.children.length; ++i) {
            const child = flow.children[i];
            if (child.index === index)
                return child;
        }
        return null;
    }

    function startDrag(index, key, source, at, point) {
        dragging = true;
        dragIndex = index;
        pendingKey = key;
        ghostSource = source;
        grip = at;
        pointer = point;
        hover.index = -1;
        strip.beginDrag();
    }

    function draggingCommand() {
        if (pendingKey !== "")
            return pendingKey !== drawer.separatorKey
                   && pendingKey !== drawer.groupKey;
        const held = delegateOf(dragIndex);
        return held !== null && held.kind === "command";
    }

    // Over the middle of a group of the user's: the drop goes in.
    function groupUnder(over, point) {
        if (!over || over.kind !== "group" || !over.groupEditable
                || over.index === dragIndex || !draggingCommand())
            return -1;
        const local = over.mapFromItem(root, point.x, point.y);
        const at = local.x / over.width;
        return at >= intoFrom && at <= intoTo ? over.index : -1;
    }

    function dragTo(point) {
        pointer = point;
        intoGroup = -1;
        if (outside)
            return;
        const over = delegateAt(point.x, point.y);
        intoGroup = groupUnder(over, point);
        if (intoGroup >= 0)
            return;
        if (pendingKey !== "") {
            const at = over ? over.index : items.count;
            const row = pendingKey === drawer.separatorKey
                        ? strip.insertSeparator(at)
                        : pendingKey === drawer.groupKey
                        ? strip.insertGroup(at)
                        : strip.insertCommand(pendingKey, at);
            if (row >= 0) {
                pendingKey = "";
                dragIndex = row;
                ghostSource = delegateOf(row);
            }
            return;
        }
        if (!over || over.index === dragIndex)
            return;
        // Past the target's middle, so swapping items of different
        // widths does not swap them straight back.
        const local = over.mapFromItem(root, point.x, point.y);
        const sameRow = Math.abs(over.y - delegateOf(dragIndex).y) < 1;
        const forward = over.index > dragIndex;
        // A group is passed only beyond its drop-in middle.
        const edge = over.kind === "group" && over.groupEditable
                     && draggingCommand() ? (forward ? intoTo : intoFrom) : 0.5;
        if (sameRow && (forward ? local.x < over.width * edge
                                : local.x > over.width * edge))
            return;
        // Read before moving: the move renumbers `over`.
        const to = over.index;
        strip.move(dragIndex, to);
        dragIndex = to;
    }

    function endDrag() {
        if (intoGroup >= 0 && pendingKey !== "") {
            strip.cancelDrag();
            strip.addToGroup(pendingKey, intoGroup);
        } else if (intoGroup >= 0) {
            strip.dropIntoGroup(dragIndex, intoGroup);
        } else if (pendingKey !== "") {
            strip.cancelDrag();
        } else {
            strip.endDrag(dragIndex, outside);
        }
        intoGroup = -1;
        dragging = false;
        dragIndex = -1;
        pendingKey = "";
        ghostSource = null;
    }

    Flow {
        id: flow
        x: root.gap
        y: root.gap
        width: Math.max(0, controls.x - root.gap - x)
        spacing: root.gap

        move: Transition {
            NumberAnimation {
                properties: "x,y"
                duration: root.moveMs
                easing.type: Easing.OutCubic
            }
        }

        Repeater {
            id: items
            model: strip.model

            delegate: DelegateChooser {
                role: "kind"

                DelegateChoice {
                    roleValue: "separator"
                    StripSeparator {
                        required property int index
                        height: root.itemSize
                        editing: root.editing
                    }
                }

                DelegateChoice {
                    roleValue: "choice"
                    ChoiceBar {
                        required property int index
                        required property var model
                        size: root.itemSize
                        iconSize: strip.iconSize
                        choices: model.choices
                        current: model.current
                        enabled: model.enabled || root.editing
                        editing: root.editing
                        onChosen: (choice) => strip.choose(index, choice)
                    }
                }

                DelegateChoice {
                    ToolItem {
                        required property int index
                        required property var model
                        kind: model.kind
                        groupEditable: model.editable
                        // An empty group shows only while it can be filled.
                        visible: model.kind !== "group" || model.members > 0
                                 || root.editing
                        size: root.itemSize
                        iconSize: strip.iconSize
                        icon: model.icon
                        text: model.kind === "button" || model.icon === ""
                              ? model.text : ""
                        tip: model.tip || model.text
                        enabled: model.enabled || root.editing
                        dimmed: !model.enabled
                        checked: model.checked
                        dropdown: model.dropdown
                        editing: root.editing
                        onActivated: {
                            const at = mapToItem(null, 0, height);
                            strip.activate(index, at.x, at.y);
                        }
                        onMenuRequested: (at) => strip.openMenu(index, at.x, at.y)
                    }
                }
            }
        }
    }

    // Edit mode's hand over the strip: picks an item up and moves it.
    MouseArea {
        id: hand

        property int pressedIndex: -1
        property point pressedAt

        anchors.fill: flow
        enabled: root.editing
        hoverEnabled: true
        cursorShape: root.dragging ? Qt.ClosedHandCursor : Qt.OpenHandCursor
        preventStealing: true

        function inRoot(mouse) {
            return mapToItem(root, mouse.x, mouse.y);
        }

        onPressed: (mouse) => {
            const over = root.delegateAt(inRoot(mouse).x, inRoot(mouse).y);
            pressedIndex = over ? over.index : -1;
            pressedAt = Qt.point(mouse.x, mouse.y);
        }

        onPositionChanged: (mouse) => {
            const point = inRoot(mouse);
            if (!pressed) {
                const over = root.delegateAt(point.x, point.y);
                hover.index = over ? over.index : -1;
                return;
            }
            if (!root.dragging) {
                if (pressedIndex < 0 || Math.hypot(mouse.x - pressedAt.x,
                        mouse.y - pressedAt.y) < Qt.styleHints.startDragDistance)
                    return;
                const held = root.delegateOf(pressedIndex);
                root.startDrag(pressedIndex, "", held,
                               held.mapFromItem(hand, pressedAt.x, pressedAt.y),
                               point);
            }
            root.dragTo(point);
        }

        onReleased: {
            if (root.dragging) {
                root.endDrag();
                return;
            }
            const clicked = root.delegateOf(pressedIndex);
            if (clicked && clicked.kind === "group" && clicked.groupEditable)
                strip.editGroup(strip.editedGroup === pressedIndex
                                ? -1 : pressedIndex);
        }
        onCanceled: if (root.dragging) root.endDrag()
        // The pointer may have moved onto the item's x: look a turn later.
        onExited: leaving.restart()

        Timer {
            id: leaving
            interval: 0
            onTriggered: if (!hand.pressed && !hand.containsMouse
                                 && !removeButton.hovered)
                             hover.index = -1
        }
    }

    QtObject {
        id: hover
        property int index: -1
    }

    GroupEditor {
        id: groupEditor
        visible: root.editing && strip.editedGroup >= 0
        x: root.gap
        y: flow.y + flow.height + root.gap
        width: root.width - 2 * root.gap
        itemSize: root.itemSize
        iconSize: strip.iconSize
    }

    CommandDrawer {
        id: drawer
        visible: root.editing
        x: root.gap
        y: (groupEditor.visible ? groupEditor.y + groupEditor.height
                                : flow.y + flow.height) + root.gap
        width: root.width - 2 * root.gap
        itemSize: root.itemSize
        iconSize: strip.iconSize
        onDragStarted: (key, tile, at) => root.startDrag(
            -1, key, tile, at, tile.mapToItem(root, at.x, at.y))
        onDragMoved: (tile, at) => root.dragTo(tile.mapToItem(root, at.x, at.y))
        onDragEnded: root.endDrag()
    }

    // The group a drop goes into, and the group open in the editor.
    Repeater {
        model: [root.intoGroup, root.editing ? strip.editedGroup : -1]

        delegate: Rectangle {
            required property int modelData
            readonly property Item target: modelData >= 0
                                           ? root.delegateOf(modelData) : null
            visible: target !== null
            x: target ? target.x + flow.x - 1 : 0
            y: target ? target.y + flow.y - 1 : 0
            width: target ? target.width + 2 : 0
            height: target ? target.height + 2 : 0
            radius: 4
            color: "transparent"
            border.color: theme.accent
            border.width: 2
        }
    }

    // Where the dragged item will land.
    Rectangle {
        readonly property Item held: root.dragging && root.dragIndex >= 0
                                     ? root.delegateOf(root.dragIndex) : null
        visible: held !== null
        x: held ? held.x + flow.x : 0
        y: held ? held.y + flow.y : 0
        width: held ? held.width : 0
        height: held ? held.height : 0
        radius: 4
        color: theme.background
        border.color: root.outside ? theme.danger : theme.accent
        border.width: 1
        opacity: root.intoGroup >= 0 ? 0 : 1
    }

    // The dragged item, under the pointer.
    ShaderEffectSource {
        visible: root.ghostSource !== null
        sourceItem: root.ghostSource
        hideSource: root.dragIndex >= 0
        live: true
        width: root.ghostSource ? root.ghostSource.width : 0
        height: root.ghostSource ? root.ghostSource.height : 0
        x: root.pointer.x - root.grip.x
        y: root.pointer.y - root.grip.y
        opacity: root.outside ? 0.4 : 0.9
    }

    // Closes the item under the pointer in edit mode.
    IconButton {
        id: removeButton
        readonly property Item over: root.editing && !root.dragging
                                     ? root.delegateOf(hover.index) : null
        visible: over !== null
        width: Math.round(root.itemSize * 0.45)
        x: over ? over.x + flow.x + over.width - width * 0.75 : 0
        y: over ? over.y + flow.y - height * 0.25 : 0
        iconScale: 0.7
        tip: qsTr("Remove from the toolbar")
        paint: Glyphs.remove
        onClicked: strip.removeItem(hover.index)
    }

    Row {
        id: controls
        anchors.right: parent.right
        anchors.rightMargin: root.gap
        y: root.gap
        spacing: root.gap

        IconButton {
            visible: !root.editing
            width: root.itemSize
            iconScale: 0.5
            tip: qsTr("Edit the toolbar")
            paint: Glyphs.pencil
            onClicked: strip.setEditing(true)
        }

        TextButton {
            visible: root.editing
            anchors.verticalCenter: parent.verticalCenter
            text: qsTr("Reset")
            onClicked: strip.resetLayout()
        }

        TextButton {
            visible: root.editing
            anchors.verticalCenter: parent.verticalCenter
            text: qsTr("Done")
            primary: true
            onClicked: strip.setEditing(false)
        }
    }
}
