import QtQuick

// The Body's rollback bar: a boundary between what is built and what is
// not, draggable through the timeline. See DESIGN.md rule 10.
Item {
    id: bar

    property string body: ""
    property int pos: 0
    property int minPos: 0
    property int maxPos: 0
    property real rowHeight: 20
    property real listContentY: 0
    property real listTopMargin: 0
    // The list itself, so the bar can ask where a row actually is. Rows are
    // no longer a uniform height - opening a row's detail strip makes that
    // delegate taller - so multiplying an index by a row height is no
    // longer the same thing as asking. The arithmetic survives only as the
    // fallback for a row the list has not realised, which is off screen and
    // clipped anyway.
    property var list: null
    // What the bar spans when it has nothing better to measure against.
    property real fullWidth: 200

    // The theme's own branch colour, shared with the disclosure dart so the
    // panel's drawn furniture reads as one set. Fixed rather than
    // palette-derived, so like the dart it will not follow a dark
    // stylesheet - set this to `theme.text` to put that back.
    property color ink: theme.branchInk

    property bool dragging: false
    property int dragPos: pos
    readonly property int effectivePos: dragging ? dragPos : pos

    // While the bar is held, it follows the pointer continuously rather
    // than stepping from gap to gap. The slot underneath it still
    // quantises - that is what decides which feature gets set, and it
    // cannot be a fraction - but quantising the *drawing* as well made the
    // bar jump a row at a time under a smoothly moving hand, which reads
    // as the panel stuttering rather than as the bar snapping.
    property real dragY: 0
    //: Where in the bar's height it was taken hold of, so it does not leap
    //: to centre itself under the cursor on the first press.
    property real grabOffset: 0

    // The gap below row `effectivePos`. The grab area is taller than the
    // line so the bar is a realistic target, and never shorter than the
    // knobs it has to contain - the whole strip drags, the knobs say where
    // to take hold of it.
    height: Math.max(9, Math.round(rowHeight * 0.45), knob + 3)

    // itemAtIndex() is a function call, so a binding that used it alone
    // would evaluate once and never re-run. Reading contentHeight and
    // contentY gives it two properties to depend on that change whenever
    // the rows move - which is exactly when these answers go stale.
    function rowAt(index) {
        var watch = bar.listContentY
                  + (bar.list ? bar.list.contentHeight : 0);
        return bar.list ? bar.list.itemAtIndex(index) : null;
    }

    // Where the bar sits when it is resting in the gap below `index`.
    function boundaryY(index) {
        var item = bar.rowAt(index);
        var edge = item ? item.y + item.height
                        : (index + 1) * bar.rowHeight;
        // A row that has opened a gap for this bar has grown downwards, so
        // its bottom edge is now below the space it made. Sit in the middle
        // of the gap rather than under it.
        var opened = (item && item.gap) ? item.gap : 0;
        return bar.listTopMargin + edge - opened / 2
             - bar.listContentY - bar.height / 2;
    }

    // The ends of the bar's travel. Bindings rather than a call inside
    // the move handler: these change when the rows move, not when the
    // pointer does, and working them out per mouse move meant two
    // itemAtIndex() lookups on every frame of a drag to re-derive two
    // numbers that had not changed.
    readonly property real topY: boundaryY(minPos)
    readonly property real bottomY: boundaryY(maxPos)

    function clampY(value) {
        return Math.max(bar.topY, Math.min(bar.bottomY, value));
    }

    // The resting place in the list's content coordinates, which scrolling
    // does not change. Animating `y` itself animated every scroll step too,
    // so the bar trailed the rows and rubber-banded into place after the
    // wheel stopped. Only a change of resting place is eased, as an offset
    // that decays to zero; scrolling moves the bar in lockstep with the rows.
    readonly property real restContentY: bar.boundaryY(bar.effectivePos)
                                         + bar.listContentY
    property real settleOffset: 0
    property real lastRest: NaN

    y: bar.dragging ? bar.dragY
                    : bar.restContentY - bar.listContentY + bar.settleOffset

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
        bar.settleFrom(bar.dragY - (bar.restContentY - bar.listContentY))

    NumberAnimation {
        id: settle
        target: bar
        property: "settleOffset"
        to: 0
        duration: 110
        easing.type: Easing.OutCubic
    }

    // Docked, the bar spans the list: there is a full-width row under it and
    // a rule across it reads as a divider. In overlay mode there is no row,
    // only two pills, and a line running off past both of them reads as
    // something drawn on the 3D view. So it stops just past whichever
    // neighbour reaches furthest right.
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

    // A translucent QQuickWidget does not ask the surface behind it to
    // redraw when its own content moves, so the bar's previous position
    // stays painted in the transparent gap until something unrelated
    // repaints - a black rule stranded across the model. Same nudge the
    // list already makes when it scrolls; coalesced on the other side.
    onYChanged: if (theme.overlay) host.repaintBehind()
    onWidthChanged: if (theme.overlay) host.repaintBehind()

    // --- the line and its handles --------------------------------------- #

    // A rule with a knob at each end. The knobs are the affordance: a line
    // on its own says "boundary" but not "grab me", and this one has to say
    // both. Inset so the line runs between their centres rather than out
    // past them, which would read as two beads threaded on a longer wire.
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

    // Which gap a pointer at `localY` (in the parent's coordinates) is in.
    // Asking the list rather than dividing by a row height, for the same
    // reason `y` does.
    function slotAt(localY) {
        var cy = localY - listTopMargin + listContentY;
        var slot;
        if (list) {
            var idx = list.indexAt(4, cy);
            if (idx < 0) {
                slot = cy < 0 ? minPos - 1 : maxPos;
            } else {
                var item = list.itemAtIndex(idx);
                slot = (item && cy > item.y + item.height / 2) ? idx : idx - 1;
            }
        } else {
            slot = Math.round(cy / rowHeight) - 1;
        }
        return Math.max(minPos, Math.min(maxPos, slot));
    }

    HoverHandler {
        id: hover
        // A grab metaphor rather than a resize one: this drags a boundary
        // through the history, it does not resize anything.
        cursorShape: bar.dragging ? Qt.ClosedHandCursor : Qt.OpenHandCursor
    }

    MouseArea {
        anchors.fill: parent
        cursorShape: bar.dragging ? Qt.ClosedHandCursor : Qt.OpenHandCursor
        preventStealing: true

        onPressed: function (mouse) {
            // dragY before dragging, so the binding it hands over to
            // already holds the position the bar is standing at. The other
            // order shows one frame of the bar at y = 0.
            bar.grabOffset = mouse.y;
            bar.dragY = bar.y;
            bar.dragPos = bar.pos;
            bar.dragging = true;
            nxt.beginTipDrag(bar.body);
        }

        onPositionChanged: function (mouse) {
            if (!bar.dragging)
                return;
            // Measured in the parent's coordinates on purpose: this item
            // moves as the drag proceeds, so its own frame is not stable.
            var y = mapToItem(bar.parent, mouse.x, mouse.y).y;
            // The drawn position follows the hand; the slot follows the
            // rows. They are updated separately because they answer
            // different questions, and only the second one is guarded -
            // the preview has to fire once per row crossed, not once per
            // mouse move.
            bar.dragY = bar.clampY(y - bar.grabOffset);
            var slot = bar.slotAt(y);
            if (slot === bar.dragPos)
                return;
            bar.dragPos = slot;
            // Roll the model as the bar crosses each row. Guarded on the
            // slot actually changing, so this fires once per row crossed
            // rather than once per mouse move.
            nxt.previewTipRow(bar.body, slot);
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
