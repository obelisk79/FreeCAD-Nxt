import QtQuick

// A Body's rollback bar, draggable through the timeline. See DESIGN.md rule 10.
Item {
    id: bar

    property string body: ""
    property int pos: 0
    property int minPos: 0
    property int maxPos: 0
    property real rowHeight: 20
    property real listTopMargin: 0
    property int realised: 0
    // Rows vary in height; row-height arithmetic is only a fallback.
    property var list: null
    property real fullWidth: 200

    property color ink: theme.branchInk

    property bool dragging: false
    property int dragPos: pos
    readonly property int effectivePos: dragging ? dragPos : pos

    // Drawn position follows the pointer; only the slot quantises.
    property real dragY: 0
    property real grabOffset: 0
    // The item the list scrolls under (tipLayer): the pointer is kept in
    // its coordinates, so scrolling mid-drag moves the bar with the rows.
    property Item stage: null
    property real pointerY: 0

    // Edge scrolling: the band at each end of the list, how far a frame
    // moves at its edge, and how quickly holding there speeds it up.
    readonly property real edgeBand: bar.rowHeight * 1.5
    readonly property real edgeStep: 14
    readonly property real edgeAccelMs: 400
    readonly property real edgeMaxBoost: 6
    property double edgeSince: 0

    height: Math.max(9, Math.round(rowHeight * 0.45), knob + 3)

    // itemAtIndex() is not reactive; reading realised and relayouts makes
    // bindings re-run when rows move. Not contentHeight itself: a fast
    // scroll re-estimates it while the bar's position is being worked
    // out, which QML reports as a binding loop on y.
    property int relayouts: 0
    function relaidOut() { bar.relayouts += 1; }

    function rowAt(index) {
        var watch = bar.realised + bar.relayouts;
        return bar.list ? bar.list.itemAtIndex(index) : null;
    }

    function boundaryY(index) {
        var item = bar.rowAt(index);
        var edge = item ? item.y + item.height
                        : (index + 1) * bar.rowHeight;
        // Middle of a gap this bar opened.
        var opened = (item && item.gap) ? item.gap : 0;
        return bar.listTopMargin + edge - opened / 2
             - bar.height / 2;
    }

    readonly property real topY: boundaryY(minPos)
    readonly property real bottomY: boundaryY(maxPos)

    function clampY(value) {
        return Math.max(bar.topY, Math.min(bar.bottomY, value));
    }

    // Rest position in content coordinates so scrolling isn't animated;
    // only resting-place changes are eased via settleOffset.
    readonly property real restContentY: bar.boundaryY(bar.effectivePos)
    property real settleOffset: 0
    property real lastRest: NaN

    y: bar.dragging ? bar.dragY
                    : bar.restContentY + bar.settleOffset

    function settleFrom(offset) {
        bar.settleOffset = offset;
        settle.restart();
    }

    onRestContentYChanged: {
        if (!bar.dragging && !isNaN(bar.lastRest))
            bar.settleFrom(bar.settleOffset + bar.lastRest - bar.restContentY);
        bar.lastRest = bar.restContentY;
    }
    Component.onCompleted: bar.lastRest = bar.restContentY
    onDraggingChanged: if (!bar.dragging)
        bar.settleFrom(bar.dragY - bar.restContentY)

    NumberAnimation {
        id: settle
        target: bar
        property: "settleOffset"
        to: 0
        duration: 110
        easing.type: Easing.OutCubic
    }

    // In overlay mode, stop just past the wider neighbouring pill.
    readonly property real neighbourEdge: {
        if (!theme.overlay)
            return 0;       // docked, the bar spans the list and never asks
        var above = bar.rowAt(bar.effectivePos);
        var below = bar.rowAt(bar.effectivePos + 1);
        var edge = 0;
        if (above && above.pillRight !== undefined)
            edge = Math.max(edge, above.pillRight);
        if (below && below.pillRight !== undefined)
            edge = Math.max(edge, below.pillRight);
        return edge;
    }

    width: neighbourEdge > 0 ? Math.max(60, neighbourEdge + 12 - x)
                             : Math.max(40, fullWidth - x - 6)

    // Translucent QQuickWidget: repaint behind on move.
    onYChanged: if (theme.overlay) host.repaintBehind()
    onWidthChanged: if (theme.overlay) host.repaintBehind()

    // -- line and knobs --

    readonly property real knob: Math.max(6, Math.round(rowHeight * 0.34))

    Rectangle {
        id: line
        anchors.verticalCenter: parent.verticalCenter
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.leftMargin: bar.knob / 2
        anchors.rightMargin: bar.knob / 2
        height: bar.dragging ? 3 : 2
        radius: height / 2
        color: bar.ink
        opacity: bar.dragging ? 1.0 : (hover.hovered ? 0.95 : 0.8)

        Behavior on opacity { NumberAnimation { duration: 90 } }
    }

    Repeater {
        model: 2

        Rectangle {
            required property int index

            anchors.verticalCenter: parent.verticalCenter
            anchors.left: index === 0 ? parent.left : undefined
            anchors.right: index === 0 ? undefined : parent.right
            width: bar.knob + (bar.dragging || hover.hovered ? 2 : 0)
            height: width
            radius: width / 2
            color: bar.ink
            opacity: bar.dragging ? 1.0 : (hover.hovered ? 0.95 : 0.8)

            Behavior on width { NumberAnimation { duration: 90 } }
            Behavior on opacity { NumberAnimation { duration: 90 } }
        }
    }

    function follow() {
        if (!bar.dragging)
            return;
        // Past either end of the list the bar waits at that end while the
        // list scrolls under it.
        var shown = Math.max(bar.listTopMargin, Math.min(
            bar.listTopMargin + bar.list.height, bar.pointerY));
        var y = shown - bar.parent.y;
        bar.dragY = bar.clampY(y - bar.grabOffset);
        var slot = bar.slotAt(y);
        if (slot === bar.dragPos)
            return;
        bar.dragPos = slot;
        // Once per row crossed; the bridge coalesces a burst.
        nxt.previewTipRow(bar.body, slot);
    }

    // Deferred, and coalesced: the list is mid-layout when these fire.
    Connections {
        target: bar.list
        function onContentYChanged() {
            if (bar.dragging)
                Qt.callLater(bar.follow);
        }
        function onContentHeightChanged() { Qt.callLater(bar.relaidOut); }
    }

    // Held near or past an end of the list, the list scrolls, faster the
    // deeper and the longer the pointer stays there.
    Timer {
        interval: 16
        repeat: true
        running: bar.dragging && bar.list !== null && bar.stage !== null
        onRunningChanged: bar.edgeSince = 0
        onTriggered: {
            var list = bar.list;
            var inList = bar.pointerY - bar.listTopMargin;
            var depth = inList < bar.edgeBand
                ? inList - bar.edgeBand
                : inList > list.height - bar.edgeBand
                ? inList - list.height + bar.edgeBand : 0;
            // Nothing past the Body's first or last step: stop there.
            if ((depth > 0 && bar.dragY >= bar.bottomY - 0.5)
                    || (depth < 0 && bar.dragY <= bar.topY + 0.5))
                depth = 0;
            if (depth === 0) {
                bar.edgeSince = 0;
                return;
            }
            var now = Date.now();
            if (bar.edgeSince === 0)
                bar.edgeSince = now;
            var boost = Math.min(bar.edgeMaxBoost,
                                 1 + (now - bar.edgeSince) / bar.edgeAccelMs);
            var reach = Math.min(2, Math.abs(depth) / bar.edgeBand);
            var top = list.originY;
            var bottom = Math.max(top, top + list.contentHeight
                                       - list.height);
            // Scrolling carries the bar as far: never past its last step.
            var step = Math.sign(depth) * bar.edgeStep * reach * boost;
            step = depth > 0 ? Math.min(step, bar.bottomY - bar.dragY)
                             : Math.max(step, bar.topY - bar.dragY);
            list.contentY = Math.max(top, Math.min(bottom,
                                                   list.contentY + step));
        }
    }

    function slotAt(localY) {
        var cy = localY - listTopMargin;
        if (!list)
            return clampSlot(Math.round(cy / rowHeight) - 1);
        var idx = list.indexAt(4, cy);
        var item = idx >= 0 ? list.itemAtIndex(idx) : null;
        if (!item) {
            // Past the rows, or over one not yet made while scrolling.
            return cy < list.originY ? minPos
                 : cy >= list.originY + list.contentHeight ? maxPos
                 : bar.dragPos;
        }
        // The row's own halves decide, not the gap this bar opened
        // under it: opening the gap must not move the slot.
        var opened = item.gap || 0;
        return clampSlot(cy > item.y + (item.height - opened) / 2
                         ? idx : idx - 1);
    }

    function clampSlot(slot) {
        return Math.max(minPos, Math.min(maxPos, slot));
    }

    HoverHandler {
        id: hover
        cursorShape: bar.dragging ? Qt.ClosedHandCursor : Qt.OpenHandCursor
    }

    MouseArea {
        anchors.fill: parent
        cursorShape: bar.dragging ? Qt.ClosedHandCursor : Qt.OpenHandCursor
        preventStealing: true

        onPressed: function (mouse) {
            // dragY before dragging, or one frame draws at y = 0.
            bar.grabOffset = mouse.y;
            bar.pointerY = mapToItem(bar.stage, mouse.x, mouse.y).y;
            bar.dragY = bar.y;
            bar.dragPos = bar.pos;
            bar.dragging = true;
            nxt.beginTipDrag(bar.body);
        }

        onPositionChanged: function (mouse) {
            if (!bar.dragging)
                return;
            // Fixed coordinates: this item and the rows move mid-drag.
            bar.pointerY = mapToItem(bar.stage, mouse.x, mouse.y).y;
            bar.follow();
        }

        onReleased: {
            bar.dragging = false;
            nxt.endTipDrag(bar.body);
        }

        onCanceled: {
            bar.dragging = false;
            bar.dragPos = bar.pos;
            nxt.cancelTipDrag(bar.body);
        }
    }
}
