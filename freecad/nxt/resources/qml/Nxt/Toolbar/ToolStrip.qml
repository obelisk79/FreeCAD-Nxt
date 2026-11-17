import QtQuick
import Qt.labs.qmlmodels
import Nxt.Controls
import Nxt.Toolbar

// One of Nxt's tool strips: the commands of FreeCAD's shown toolbars in
// rows (top) or columns (left, right). Context: `strip` (toolbars/
// bridge.py), `area` ("top", "left" or "right") and `theme`. Rows carry
// kind, text, tip, enabled, checkable, checked, icon, dropdown, choices,
// current, style, more, editable and members.
//
// Edit mode (the pencil, on the top strip): items drag to reorder; onto a
// row's end zone, or the zone after the last row, to start a new row; out
// of the strip's view to another strip (the view keeps the pointer and
// the bridge shows the drag on the strip under it); onto the drawer,
// or with their x, to remove. The drawer and group editor sit under the
// top strip. Escape or Done leaves edit mode; each change is saved.
Item {
    id: root

    readonly property bool across: area === "top"
    readonly property var stripModel: strip.modelOf(area)
    readonly property int gap: Math.max(1, Math.round(theme.rowHeight * 0.08))
    //: The top strip's first row has its own icon size; every other row,
    //: the side strips' too, shares one.
    readonly property int iconSize: across ? strip.iconSize
                                           : strip.otherIconSize
    readonly property int itemSize: itemFor(iconSize)
    readonly property int otherItemSize: itemFor(strip.otherIconSize)
    //: The row end closing the first row, or -1 while there is one row.
    readonly property int firstRowEnd: across && changes >= 0
                                       ? firstBreak() : -1
    //: What this strip locks: the top strip's first row, or a side strip.
    readonly property string lockUnit: across ? "first-row" : area
    readonly property bool locked: strip
        ? strip.lockedUnits.indexOf(lockUnit) >= 0 : false
    //: How far past the items a drop still lands on the strip.
    readonly property int removeMargin: Math.round(itemSize / 2)
    readonly property int moveMs: 120
    readonly property bool editing: strip.editing
    //: Counts the model's changes: a row end finds its neighbour again
    //: whenever items move, though its own index may not change.
    property int changes: 0

    Connections {
        target: root.stripModel
        function onRowsMoved() { ++root.changes }
        function onRowsInserted() { ++root.changes }
        function onRowsRemoved() { ++root.changes }
        function onModelReset() { ++root.changes }
    }

    // The drag in progress: a strip row, or a drawer key not placed yet.
    property bool dragging: false
    property int dragIndex: -1
    property string pendingKey: ""
    property Item ghostSource: null
    property point grip
    property point pointer
    //: The group a command will drop into, or -1.
    property int intoGroup: -1
    //: The row end a drop starts a new row after; -1 the last; -2 none.
    property int newRowAfter: -2
    //: Where a drag from another view would land, or -1.
    property int dropAt: -1
    //: This strip's drag left its view: the strip under the pointer
    //: shows where it lands, as this view keeps the pointer.
    property bool carrying: false
    //: A drag from another view is over this strip, at carryPoint.
    property bool carriedHere: false
    property point carryPoint: Qt.point(0, 0)
    readonly property int notNewRow: -2
    //: Where on a group, along the strip, a drop goes in.
    readonly property real intoFrom: 0.25
    readonly property real intoTo: 0.75
    readonly property bool outside: dragging && across
        && pointer.y > items.y + items.height + removeMargin

    implicitHeight: across
        ? Math.max(items.height, controls.height) + 2 * gap
          + (groupEditor.visible ? groupEditor.implicitHeight + gap : 0)
          + (editing ? drawer.implicitHeight + gap : 0)
        : 0
    implicitWidth: across ? 0 : items.width + 2 * gap

    onEditingChanged: if (editing && across) drawer.focusSearch()
    Keys.onEscapePressed: strip.setEditing(false)

    // Along the strip, how far into `item` the point is: 0 to 1.
    function along(item, point) {
        const local = item.mapFromItem(root, point.x, point.y);
        return across ? local.x / item.width : local.y / item.height;
    }

    // Empty space past a line's last item: the drop ends that line.
    function toLineEnd(last) {
        if (pendingKey !== "") {
            place(last.index + 1);
            return;
        }
        const to = dragIndex <= last.index ? last.index : last.index + 1;
        if (to === dragIndex)
            return;
        strip.move(dragIndex, to, area);
        dragIndex = to;
    }

    // A drawer item enters the strip at `at`; the drag carries it on.
    function place(at) {
        const row = pendingKey === drawer.separatorKey
                    ? strip.insertSeparator(at, area)
                    : pendingKey === drawer.groupKey
                    ? strip.insertGroup(at, area)
                    : strip.insertCommand(pendingKey, at, area);
        if (row < 0)
            return;
        pendingKey = "";
        dragIndex = row;
        ghostSource = delegateOf(row);
        if (ghostSource)
            grip = Qt.point(ghostSource.width / 2, ghostSource.height / 2);
    }

    function sameLine(a, b) {
        return across ? Math.abs(a.y - b.y) < 1 : Math.abs(a.x - b.x) < 1;
    }

    function delegateAt(x, y) {
        const at = flow.mapFromItem(root, x, y);
        const child = flow.childAt(at.x, at.y);
        return child && child.index !== undefined ? child : null;
    }

    // What the items of the row ending at `index` take up, with spacing.
    function rowExtent(index) {
        let used = 0;
        for (let i = index - 1; i >= 0; --i) {
            const item = delegateOf(i);
            if (!item || item.kind === "break")
                break;
            used += (across ? item.width : item.height) + gap;
        }
        return used;
    }

    // The last item on the line through `point`, before it there.
    function lastInLine(point) {
        const at = flow.mapFromItem(root, point.x, point.y);
        let last = null;
        for (let i = 0; i < flow.children.length; ++i) {
            const child = flow.children[i];
            if (child.index === undefined || child.kind === "break"
                    || !child.visible)
                continue;
            const onLine = across
                ? at.y >= child.y && at.y < child.y + child.height
                  && at.x >= child.x + child.width
                : at.x >= child.x && at.x < child.x + child.width
                  && at.y >= child.y + child.height;
            if (onLine && (!last || child.index > last.index))
                last = child;
        }
        return last;
    }

    function itemFor(icon) {
        return icon + 2 * Math.max(2, Math.round(icon * 0.2));
    }

    function firstBreak() {
        let first = -1;
        for (let i = 0; i < flow.children.length; ++i) {
            const child = flow.children[i];
            if (child.kind === "break" && (first < 0 || child.index < first))
                first = child.index;
        }
        return first;
    }

    function inFirstRow(index) {
        return firstRowEnd < 0 || index <= firstRowEnd;
    }

    function iconAt(index) {
        return inFirstRow(index) ? iconSize : strip.otherIconSize;
    }

    function itemSizeAt(index) {
        return inFirstRow(index) ? itemSize : otherItemSize;
    }

    function delegateOf(index) {
        for (let i = 0; i < flow.children.length; ++i) {
            const child = flow.children[i];
            if (child.index === index)
                return child;
        }
        return null;
    }

    function inView(point) {
        return point.x >= 0 && point.y >= 0
            && point.x <= width && point.y <= height;
    }

    function inEndZone(point) {
        if (!endZone.visible)
            return false;
        const at = endZone.mapFromItem(root, point.x, point.y);
        return endZone.contains(at);
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

    function resetDrag() {
        dragging = false;
        carrying = false;
        dragIndex = -1;
        pendingKey = "";
        ghostSource = null;
        intoGroup = -1;
        newRowAfter = notNewRow;
    }

    // Out of this strip's view: the bridge follows it to the strip under
    // the pointer.
    function carry(point) {
        if (!carrying) {
            const look = ghostSource;
            const icon = look && look.icon ? look.icon : "";
            const text = look ? (look.label || look.text || "") : "";
            if (pendingKey !== "")
                strip.carryKey(pendingKey, icon, text);
            else
                strip.carryRow(area, dragIndex, icon, text);
            carrying = true;
        }
        strip.carryTo(area, point.x, point.y);
    }

    // Where a carried item would land at `point`: a row, or a new row.
    function landing(point) {
        newRowAfter = notNewRow;
        if (inEndZone(point)) {
            newRowAfter = -1;
            return stripModel.rowCount();
        }
        const over = delegateAt(point.x, point.y);
        if (over && over.kind === "break") {
            newRowAfter = over.index;
            return over.index;
        }
        if (!over) {
            const last = lastInLine(point);
            return last ? last.index + 1 : stripModel.rowCount();
        }
        return along(over, point) > 0.5 ? over.index + 1 : over.index;
    }

    function overDrawer(point) {
        return drawer.visible
            && drawer.contains(drawer.mapFromItem(root, point.x, point.y));
    }

    function leaveCarry() {
        carriedHere = false;
        dropAt = -1;
        newRowAfter = notNewRow;
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
        const at = along(over, point);
        return at >= intoFrom && at <= intoTo ? over.index : -1;
    }

    function dragTo(point) {
        if (!dragging)
            return;
        pointer = point;
        intoGroup = -1;
        newRowAfter = notNewRow;
        if (carrying || !inView(point)) {
            carry(point);
            return;
        }
        if (outside)
            return;
        if (inEndZone(point)) {
            newRowAfter = -1;
            return;
        }
        const over = delegateAt(point.x, point.y);
        if (over && over.kind === "break") {
            newRowAfter = over.index;
            return;
        }
        if (!over) {
            const last = lastInLine(point);
            if (last)
                toLineEnd(last);
            return;
        }
        intoGroup = groupUnder(over, point);
        if (intoGroup >= 0)
            return;
        if (pendingKey !== "") {
            place(over ? over.index : stripModel.rowCount());
            return;
        }
        if (!over || over.index === dragIndex)
            return;
        const held = delegateOf(dragIndex);
        const forward = over.index > dragIndex;
        // Past the target's middle (a group's drop-in band), so swapping
        // items of different sizes does not swap them straight back.
        const edge = over.kind === "group" && over.groupEditable
                     && draggingCommand() ? (forward ? intoTo : intoFrom)
                                          : 0.5;
        const at = along(over, point);
        if (held && sameLine(over, held) && (forward ? at < edge : at > edge))
            return;
        // Read before moving: the move renumbers `over`.
        const to = over.index;
        strip.move(dragIndex, to, area);
        dragIndex = to;
    }

    function endDrag() {
        if (carrying) {
            resetDrag();
            strip.carryEnd();
            return;
        }
        if (newRowAfter !== notNewRow) {
            if (pendingKey !== "")
                strip.addInNewRow(pendingKey, newRowAfter, area);
            else
                strip.moveToNewRow(dragIndex, newRowAfter, area);
        } else if (intoGroup >= 0 && pendingKey !== "") {
            strip.cancelDrag();
            strip.addToGroup(pendingKey, intoGroup, area);
        } else if (intoGroup >= 0) {
            strip.dropIntoGroup(dragIndex, intoGroup, area);
        } else if (pendingKey !== "") {
            strip.cancelDrag();
        } else {
            strip.endDrag(dragIndex, outside, area);
        }
        resetDrag();
    }

    // The items, and the zone after the last row that starts another.
    Item {
        id: items
        x: root.gap
        y: root.gap
        width: root.across ? Math.max(0, controls.x - root.gap - x)
                           : flow.width + (endZone.visible
                                           ? endZone.width + root.gap : 0)
        height: root.across ? flow.height + (endZone.visible
                                             ? endZone.height + root.gap : 0)
                            : Math.max(0, root.height - 2 * root.gap
                                       - (root.editing ? root.itemSize
                                                         + root.gap : 0))

        Flow {
            id: flow
            flow: root.across ? Flow.LeftToRight : Flow.TopToBottom
            width: root.across ? items.width
                               : Math.max(implicitWidth, root.itemSize)
            // A side strip's end zone sits beside its items, not below.
            height: root.across ? Math.max(implicitHeight, root.itemSize)
                                : items.height
            spacing: root.gap

            move: Transition {
                NumberAnimation {
                    properties: "x,y"
                    duration: root.moveMs
                    easing.type: Easing.OutCubic
                }
            }

            Repeater {
                model: root.stripModel

                delegate: DelegateChooser {
                    role: "kind"

                    DelegateChoice {
                        roleValue: "separator"
                        StripSeparator {
                            required property int index
                            readonly property string kind: "separator"
                            across: root.across
                            size: root.itemSizeAt(index)
                            editing: root.editing
                        }
                    }

                    DelegateChoice {
                        roleValue: "break"
                        StripBreak {
                            required property int index
                            readonly property string kind: "break"
                            across: root.across
                            editing: root.editing
                            size: root.itemSizeAt(index)
                            line: flow
                            used: root.changes >= 0
                                  ? root.rowExtent(index) : 0
                            targeted: root.newRowAfter === index
                        }
                    }

                    DelegateChoice {
                        roleValue: "choice"
                        ChoiceBar {
                            required property int index
                            required property var model
                            readonly property string kind: "choice"
                            size: root.itemSizeAt(index)
                            iconSize: root.iconAt(index)
                            choices: model.choices
                            current: model.current
                            style: model.style
                            more: model.more
                            enabled: model.enabled || root.editing
                            editing: root.editing
                            onChosen: (choice) => strip.choose(index, choice,
                                                               area)
                            onMenuRequested: (at) => strip.openMenu(
                                index, at.x, at.y, area)
                            onMoreRequested: (at) => strip.openMore(
                                index, at.x, at.y, area)
                        }
                    }

                    DelegateChoice {
                        ToolItem {
                            required property int index
                            required property var model
                            kind: model.kind
                            groupEditable: model.editable
                            // An empty group shows only while it can be
                            // filled.
                            visible: model.kind !== "group"
                                     || model.members > 0 || root.editing
                            size: root.itemSizeAt(index)
                            iconSize: root.iconAt(index)
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
                                strip.activate(index, at.x, at.y, area);
                            }
                            onMenuRequested: (at) => strip.openMenu(
                                index, at.x, at.y, area)
                        }
                    }
                }
            }
        }

        StripBreak {
            id: endZone
            visible: root.editing
            x: root.across ? 0 : flow.width + root.gap
            y: root.across ? flow.height + root.gap : 0
            across: root.across
            editing: true
            size: Math.round(root.itemSize / 2)
            line: items
            targeted: root.newRowAfter === -1
        }
    }

    // Edit mode's hand over the strip: picks an item up and moves it.
    MouseArea {
        id: hand

        property int pressedIndex: -1
        property point pressedAt

        anchors.fill: items
        enabled: root.editing
        hoverEnabled: true
        cursorShape: root.dragging ? Qt.ClosedHandCursor : Qt.OpenHandCursor
        preventStealing: true

        function inRoot(mouse) {
            return mapToItem(root, mouse.x, mouse.y);
        }

        onPressed: (mouse) => {
            const at = inRoot(mouse);
            const over = root.delegateAt(at.x, at.y);
            pressedIndex = over && over.kind !== "break" ? over.index : -1;
            pressedAt = Qt.point(mouse.x, mouse.y);
        }

        onPositionChanged: (mouse) => {
            const point = inRoot(mouse);
            if (!pressed) {
                const over = root.delegateAt(point.x, point.y);
                hover.index = over && over.kind !== "break" ? over.index : -1;
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
                                && strip.editedArea === area
                                ? -1 : pressedIndex, area);
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

    // A drag from another strip's view, told by the bridge.
    Connections {
        target: strip

        function onCarriedOver(target, x, y) {
            if (target !== area) {
                if (root.carriedHere)
                    root.leaveCarry();
                return;
            }
            root.carriedHere = true;
            root.carryPoint = Qt.point(x, y);
            root.dropAt = root.overDrawer(root.carryPoint)
                ? -1 : root.landing(root.carryPoint);
        }

        function onCarriedDropped(target, x, y) {
            if (target !== area)
                return;
            const point = Qt.point(x, y);
            if (root.overDrawer(point)) {
                strip.removeCarried();
            } else {
                const at = root.landing(point);
                strip.dropCarried(area, at, root.newRowAfter);
            }
            root.leaveCarry();
        }
    }

    QtObject {
        id: hover
        property int index: -1
    }

    GroupEditor {
        id: groupEditor
        visible: root.across && root.editing && strip.editedGroup >= 0
        x: root.gap
        y: items.y + items.height + root.gap
        width: root.width - 2 * root.gap
        itemSize: root.itemSize
        iconSize: strip.iconSize
    }

    CommandDrawer {
        id: drawer
        visible: root.across && root.editing
        x: root.gap
        y: (groupEditor.visible ? groupEditor.y + groupEditor.height
                                : items.y + items.height) + root.gap
        width: root.width - 2 * root.gap
        itemSize: root.itemSize
        iconSize: strip.iconSize
        onDragStarted: (key, tile, at) => {
            root.startDrag(-1, key, tile, at, tile.mapToItem(root, at.x, at.y));
        }
        onDragMoved: (tile, at) => root.dragTo(tile.mapToItem(root, at.x, at.y))
        onDragEnded: root.endDrag()
    }

    // The group a drop goes into, and the group open in the editor.
    Repeater {
        model: [root.intoGroup,
                root.editing && strip.editedArea === area
                ? strip.editedGroup : -1]

        delegate: Rectangle {
            required property int modelData
            readonly property Item target: modelData >= 0
                                           ? root.delegateOf(modelData) : null
            visible: target !== null
            x: target ? target.mapToItem(root, 0, 0).x - 1 : 0
            y: target ? target.mapToItem(root, 0, 0).y - 1 : 0
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
        readonly property point at: held ? held.mapToItem(root, 0, 0)
                                         : Qt.point(0, 0)
        visible: held !== null
        x: at.x
        y: at.y
        width: held ? held.width : 0
        height: held ? held.height : 0
        radius: 4
        color: theme.background
        border.color: root.outside ? theme.danger : theme.accent
        border.width: 1
        opacity: root.intoGroup >= 0 || root.newRowAfter !== root.notNewRow
                 ? 0 : 1
    }

    // The dragged item, under the pointer.
    ShaderEffectSource {
        visible: root.ghostSource !== null && root.dragIndex >= 0
                 && !root.carrying
        sourceItem: root.ghostSource
        hideSource: root.dragIndex >= 0
        live: true
        width: root.ghostSource ? root.ghostSource.width : 0
        height: root.ghostSource ? root.ghostSource.height : 0
        x: root.pointer.x - root.grip.x
        y: root.pointer.y - root.grip.y
        opacity: root.outside ? 0.4 : 0.9
    }

    // Where a drag from another view lands: a bar before that item, or
    // after the last.
    Rectangle {
        readonly property Item before: root.dropAt >= 0
                                       ? root.delegateOf(root.dropAt) : null
        readonly property Item after: !before && root.dropAt > 0
                                      ? root.delegateOf(root.dropAt - 1)
                                      : null
        readonly property Item next: before || after
        readonly property point at: next
            ? next.mapToItem(root, after ? next.width : 0,
                             after && !root.across ? next.height : 0)
            : Qt.point(0, 0)
        visible: next !== null && root.newRowAfter === root.notNewRow
        color: theme.accent
        width: root.across ? 2 : root.itemSize
        height: root.across ? root.itemSize : 2
        x: root.across ? at.x - width / 2 : at.x
        y: root.across ? at.y : at.y - height / 2
    }

    // A drawer item not in the strip yet, drawn as the strip will show
    // it, centred on the pointer.
    ToolItem {
        objectName: "dragGhost"
        visible: root.dragging && root.pendingKey !== ""
                 && root.ghostSource !== null && !root.carrying
        enabled: false
        dimmed: false
        size: root.itemSize
        iconSize: root.iconSize
        icon: root.ghostSource ? root.ghostSource.icon || "" : ""
        text: icon === "" && root.ghostSource
              ? root.ghostSource.label || "" : ""
        x: root.pointer.x - width / 2
        y: root.pointer.y - height / 2
        opacity: root.outside ? 0.4 : 0.9
    }

    // An item carried here from another view, centred on the pointer.
    ToolItem {
        objectName: "dragGhost"
        visible: root.carriedHere
        enabled: false
        dimmed: false
        size: root.itemSize
        iconSize: root.iconSize
        icon: strip.carriedIcon
        text: icon === "" ? strip.carriedText : ""
        x: root.carryPoint.x - width / 2
        y: root.carryPoint.y - height / 2
        opacity: 0.9
    }

    // Closes the item under the pointer in edit mode.
    IconButton {
        id: removeButton
        readonly property Item over: root.editing && !root.dragging
                                     ? root.delegateOf(hover.index) : null
        readonly property point at: over ? over.mapToItem(root, 0, 0)
                                         : Qt.point(0, 0)
        visible: over !== null
        width: Math.round(root.itemSize * 0.45)
        x: over ? at.x + over.width - width * 0.75 : 0
        y: over ? at.y - height * 0.25 : 0
        iconScale: 0.7
        tip: qsTr("Remove from the toolbar")
        paint: Glyphs.remove
        onClicked: strip.removeItem(hover.index, area)
    }

    // The lock in edit mode: the first row or side strip the same in
    // every workbench.
    component LockButton: IconButton {
        width: root.itemSize
        iconScale: 0.55
        highlighted: root.locked
        tip: root.locked ? qsTr("Locked: the same in every workbench")
                         : qsTr("Lock: the same in every workbench")
        paint: root.locked ? Glyphs.lock : Glyphs.unlock
        onClicked: strip.setLocked(root.lockUnit, !root.locked)
    }

    // The top strip's end: the pencil, or in edit mode the first row's
    // lock and size.
    Row {
        id: controls
        visible: root.across
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

        LockButton { visible: root.editing }

        SizeStepper {
            visible: root.editing
            anchors.verticalCenter: parent.verticalCenter
            size: strip.iconSize
            sizes: strip.iconSizes
            onPicked: (size) => strip.setIconSize(size)
        }
    }

    // A side strip's lock, at its far end in edit mode.
    LockButton {
        visible: !root.across && root.editing
        anchors.bottom: parent.bottom
        anchors.bottomMargin: root.gap
        x: root.gap
    }
}
