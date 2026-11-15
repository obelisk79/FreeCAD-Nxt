import QtQuick
import Qt.labs.qmlmodels
import Nxt.Controls
import Nxt.Toolbar

// Nxt's tool strip: every command of FreeCAD's shown toolbars in one row,
// wrapping when the window is narrow. Context: `strip` (toolbars/bridge.py)
// and `theme`. Rows carry kind, text, tip, enabled, checkable, checked,
// icon, dropdown, choices and current.
//
// Edit mode (the pen at the end): items are dragged to reorder, dropped
// outside the strip or closed with their x to remove. Escape or Done
// leaves it. Each finished drag is saved by the bridge.
Item {
    id: root

    readonly property int gap: Math.max(1, Math.round(theme.rowHeight * 0.08))
    readonly property int padding: Math.max(2, Math.round(strip.iconSize * 0.2))
    readonly property int itemSize: strip.iconSize + 2 * padding
    //: How far outside the strip a drop removes the item.
    readonly property int removeMargin: Math.round(itemSize / 2)
    readonly property int moveMs: 120
    readonly property bool editing: strip.editing

    implicitHeight: Math.max(flow.implicitHeight, controls.height) + 2 * gap

    focus: editing
    onEditingChanged: if (editing) forceActiveFocus()
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

    // Edit mode's hand: picks an item up, moves it through the strip.
    MouseArea {
        id: hand

        property int dragIndex: -1
        property bool dragging: false
        property point pressedAt
        property point grip
        property int hovered: -1
        readonly property bool outside: dragging
            && (mouseY < -root.removeMargin
                || mouseY > root.height + root.removeMargin)

        anchors.fill: flow
        enabled: root.editing
        hoverEnabled: true
        cursorShape: dragging ? Qt.ClosedHandCursor : Qt.OpenHandCursor
        preventStealing: true

        function at(mouse) {
            return root.delegateAt(mouse.x + flow.x, mouse.y + flow.y);
        }

        onPositionChanged: (mouse) => {
            const over = at(mouse);
            if (!pressed) {
                hovered = over ? over.index : -1;
                return;
            }
            if (!dragging) {
                if (dragIndex < 0 || Math.hypot(mouse.x - pressedAt.x,
                        mouse.y - pressedAt.y) < Qt.styleHints.startDragDistance)
                    return;
                dragging = true;
                hovered = -1;
                strip.beginDrag();
            }
            if (!over || over.index === dragIndex || outside)
                return;
            // Past the target's middle, so swapping items of different
            // widths does not swap them straight back.
            const local = over.mapFromItem(hand, mouse.x, mouse.y);
            const sameRow = Math.abs(over.y - root.delegateOf(dragIndex).y) < 1;
            const forward = over.index > dragIndex;
            if (sameRow && (forward ? local.x < over.width / 2
                                    : local.x > over.width / 2))
                return;
            // Read before moving: the move renumbers `over`.
            const to = over.index;
            strip.move(dragIndex, to);
            dragIndex = to;
        }

        onPressed: (mouse) => {
            const over = at(mouse);
            dragIndex = over ? over.index : -1;
            pressedAt = Qt.point(mouse.x, mouse.y);
            if (over)
                grip = over.mapFromItem(hand, mouse.x, mouse.y);
        }

        onReleased: {
            if (dragging)
                strip.endDrag(dragIndex, outside);
            dragging = false;
            dragIndex = -1;
        }

        onCanceled: {
            if (dragging)
                strip.endDrag(dragIndex, false);
            dragging = false;
            dragIndex = -1;
        }

        // The pointer may have moved onto the item's x: look a turn later.
        onExited: leaving.restart()

        Timer {
            id: leaving
            interval: 0
            onTriggered: if (!hand.pressed && !hand.containsMouse
                                 && !removeButton.hovered)
                             hand.hovered = -1
        }
    }

    // Where the dragged item will land.
    Rectangle {
        readonly property Item held: hand.dragging
                                     ? root.delegateOf(hand.dragIndex) : null
        visible: held !== null
        x: held ? held.x + flow.x : 0
        y: held ? held.y + flow.y : 0
        width: held ? held.width : 0
        height: held ? held.height : 0
        radius: 4
        color: theme.background
        border.color: hand.outside ? theme.danger : theme.accent
        border.width: 1
    }

    // The dragged item, under the pointer.
    ShaderEffectSource {
        id: ghost
        readonly property Item held: hand.dragging
                                     ? root.delegateOf(hand.dragIndex) : null
        visible: held !== null
        sourceItem: held
        hideSource: true
        live: true
        width: held ? held.width : 0
        height: held ? held.height : 0
        x: hand.mouseX + flow.x - hand.grip.x
        y: hand.mouseY + flow.y - hand.grip.y
        opacity: hand.outside ? 0.4 : 0.9
    }

    // Closes the item under the pointer in edit mode.
    IconButton {
        id: removeButton
        readonly property Item over: root.editing && !hand.dragging
                                     ? root.delegateOf(hand.hovered) : null
        visible: over !== null
        width: Math.round(root.itemSize * 0.45)
        x: over ? over.x + flow.x + over.width - width * 0.75 : 0
        y: over ? over.y + flow.y - height * 0.25 : 0
        iconScale: 0.7
        tip: qsTr("Remove from the toolbar")
        paint: Glyphs.remove
        onClicked: strip.removeItem(hand.hovered)
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
