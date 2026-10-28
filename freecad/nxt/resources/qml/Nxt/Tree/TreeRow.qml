import QtQuick
import QtQuick.Controls.Basic
import Nxt.Controls

// One row of the panel: a fixed-height line plus an optional detail strip.
// Indentation comes from depth only, so lifted sketches need no nesting.
Item {
    id: row

    required property int index
    required property string name
    required property string label
    required property int depth
    required property bool hasChildren
    required property bool expanded
    required property bool objectVisible
    required property bool selected
    required property string iconUrl
    required property var refs
    required property bool isContainer
    required property bool inError
    required property bool highlighted
    required property bool isFeature
    required property bool afterTip
    required property bool isProfile
    required property bool isLifted
    required property bool isActive
    required property bool isActivePart
    required property int severity
    required property var notes
    required property int dof
    required property int constrained
    required property bool detailOpen
    required property string bodyName
    required property var consumers
    required property var keyProps
    required property int propertyCount
    required property var branches
    required property int activeFrom
    //: CAM: the operation's cycle time, or a total row's sum ("" if none).
    required property string cycleTime
    //: "Total Cycle Time:" under an Operations group: no object behind it.
    required property bool isTotal
    required property bool isCam
    required property string typeId

    // Feature that made the face picked in the 3D view; outlined, not selected.
    readonly property bool pickOrigin: nxt.pickOrigins.indexOf(row.name) >= 0

    property Item dragGhost
    property bool dropTarget: false
    property bool renaming: false

    // Docked: beside the dock border (-1). In the 3D view: clear of the widest pill.
    function openInspector() {
        var corner = row.mapToGlobal(0, 0);
        var left = -1;
        if (host.viewOverlay) {
            var edge = row.pillRight;
            var rows = ListView.view ? ListView.view.contentItem.children : [];
            for (var i = 0; i < rows.length; ++i) {
                if (rows[i].visible && rows[i].pillRight !== undefined)
                    edge = Math.max(edge, rows[i].pillRight);
            }
            left = row.mapToGlobal(edge, 0).x;
        }
        nxt.openPropertyInspector(row.name, left, corner.y);
    }
    property real detailCap: width

    // Click on an already-selected label renames, deferred past the
    // double-click interval so a double click (open) wins.
    Timer {
        id: renameDelay
        interval: Application.styleHints.mouseDoubleClickInterval + 20
        onTriggered: if (row.selected && !row.renaming) row.beginRename()
    }

    function armRename() { renameDelay.restart(); }
    function disarmRename() { renameDelay.stop(); }

    // Hit-tests the label's glyphs, not its box.
    function overGlyphs(x, y) {
        var local = title.mapFromItem(head, x, y);
        var glyphs = Math.min(title.width, title.contentWidth);
        return local.x >= 0 && local.x <= glyphs
            && local.y >= 0 && local.y <= title.height;
    }

    // Losing selection cancels a pending rename and commits an open one:
    // the box may never have had keyboard focus to lose.
    onSelectedChanged: {
        if (!row.selected) {
            row.disarmRename();
            row.commitRename();
        }
    }

    // Edits Label, never Name (the immutable link identifier).
    function beginRename() {
        renameInput.text = row.label;
        row.renaming = true;
        host.takeKeyboard();
        renameInput.forceActiveFocus();
        renameInput.selectAll();
    }

    function commitRename() {
        if (!row.renaming)
            return;
        row.renaming = false;
        nxt.rename(row.name, renameInput.text);
    }

    // A recycled row starts clean: nothing it was doing follows it to
    // another object.
    ListView.onPooled: {
        renameDelay.stop();
        row.cancelRename();
        row.dropTarget = false;
        springOpen.stop();
        flashAnimation.stop();
        flash.opacity = 0;
        press.armed = false;
        press.held = false;
    }

    function cancelRename() {
        // Clear first so the following focus loss commits nothing.
        row.renaming = false;
    }

    width: ListView.view ? ListView.view.width : 280
    implicitHeight: head.height + (showDetail ? detail.height : 0) + gap

    readonly property real pillRight: theme.overlay
                                    ? tail.x + tail.width + 5
                                    : head.width

    // -- drag gap --
    readonly property bool gapBelow: ListView.view
                                     && ListView.view.gapAfterRow === row.index
    readonly property int dragGapHeight:
        ListView.view && ListView.view.reorderDrag
            ? theme.rowHeight : Math.round(theme.rowHeight * 0.55)
    readonly property bool dragSource:
        ListView.view && ListView.view.dragSources.indexOf(row.name) >= 0
    readonly property bool slideInto: ListView.view
                                      && ListView.view.intoRow === row.index
    property real gap: 0
    onGapBelowChanged: gap = gapBelow ? row.dragGapHeight : 0

    Behavior on gap {
        NumberAnimation { duration: 120; easing.type: Easing.OutCubic }
    }

    // Under-constrained sketches get the quietest mark: it is not a fault.
    readonly property int markLevel: {
        if (row.severity >= 2) return 3;
        if (row.severity >= 1) return 2;
        if (row.isProfile && row.constrained !== 1
                && theme.showUnderConstrained) return 1;
        return 0;
    }

    // Matches DetailStrip.hasContent, so the mark never promises an
    // empty strip.
    readonly property bool hasDetail:
        (row.notes && row.notes.length > 0)
        || (row.refs && row.refs.length > 0)
        || (row.consumers && row.consumers.length > 0)
        || row.isProfile || row.isLifted
        || (row.keyProps && row.keyProps.length > 0)
        || row.propertyCount > 0
    readonly property bool showDetail: row.detailOpen && row.hasDetail

    // A failure owned by a profile reddens the chip, not the label.
    readonly property bool blamedOnProfile: {
        if (!row.inError || !row.refs)
            return false;
        for (var i = 0; i < row.refs.length; ++i)
            if (row.refs[i].severity >= 2)
                return true;
        return false;
    }

    // Overlay hit test (view_overlay.py): misses fall through to the 3D view.
    function wantsPoint(px, py) {
        if (py < head.height) {
            var left = row.hasChildren ? expander.x : row.pillLeft;
            return px >= left - 2 && px <= row.pillRight + 2;
        }
        return detail.visible && px >= row.detailLeft
               && px <= detail.width - 8;
    }

    readonly property bool showControls: hover.hovered
        || (row.ListView.isCurrentItem && row.ListView.view !== null
            && row.ListView.view.activeFocus)

    readonly property bool isolatedOut:
        isolation.isActive && !isolation.keptNames[row.name]

    readonly property int leftPad: theme.rowPad + depth * theme.indent
    // Strip follows the indent only two levels deep; a tick marks the pill.
    readonly property int detailIndentCap: 2
    readonly property real pillLeft: icon.x - 5
    readonly property real detailLeft:
        Math.max(2, pillLeft - Math.max(0, depth - detailIndentCap)
                               * theme.indent)
    readonly property int guideOffset: Math.round(theme.rowHeight * 0.3)

    readonly property var shownRefs: {
        var out = [];
        if (!row.refs || theme.chipMode === "none")
            return out;
        var all = theme.chipMode === "all";
        for (var i = 0; i < row.refs.length; ++i)
            if (all || row.refs[i].severity > 0 || row.refs[i].pinned)
                out.push(row.refs[i]);
        return out;
    }

    // -- tooltips --

    function refTip(ref) {
        var lines = [ref.label + (ref.label !== ref.name
                                  ? "  (" + ref.name + ")" : "")];
        if (ref.sub.length > 0)
            lines.push(qsTr("Uses %1").arg(ref.sub));
        if (ref.severity >= 2)
            lines.push(qsTr("Has an error"));
        else if (ref.severity >= 1)
            lines.push(qsTr("Has a warning"));
        lines.push(qsTr("Click to show it, double-click to edit it"));
        return lines.join("\n");
    }

    function moreRefsTip() {
        var names = [];
        for (var i = row.chipLimit; i < row.shownRefs.length; ++i)
            names.push(row.shownRefs[i].label);
        return names.join("\n");
    }

    readonly property string nameTip: {
        var differs = row.name !== row.label;
        if (!title.truncated && !differs)
            return "";
        return row.label + (differs ? "\n" + qsTr("Internal name: %1")
                                                .arg(row.name) : "");
    }

    readonly property string markTip: {
        var note = row.notes && row.notes.length > 0 ? row.notes[0] : "";
        var more = row.hasDetail
                   ? "\n" + qsTr("Click for details") + "\n" + row.inspectTip
                   : "";
        if (row.markLevel >= 3)
            return (note || qsTr("Error")) + more;
        if (row.markLevel === 2)
            return (note || qsTr("Warning")) + more;
        if (row.markLevel === 1)
            return (row.dof > 0
                    ? qsTr("Under-constrained: %1 degrees of freedom")
                          .arg(row.dof)
                    : qsTr("Not fully constrained")) + more;
        return row.hasDetail ? qsTr("Show details") + "\n" + row.inspectTip
                             : "";
    }
    readonly property string inspectTip:
        qsTr("Ctrl+click for the Property Inspector")

    function chipText(ref) {
        return ref.sub.length > 0 ? ref.label + ":" + ref.sub : ref.label;
    }

    //: Longer names show as an icon chip; never elided.
    readonly property int chipTextLimit: 16
    //: Width below which chips are icons.
    readonly property int chipTextFloor: 240

    readonly property bool compactChips: {
        // CAM: only the cycle time is written out; references are icons.
        if (row.isCam)
            return row.shownRefs.length > 0;
        if (row.shownRefs.length > 1)
            return true;
        if (row.shownRefs.length === 1)
            return row.width < row.chipTextFloor
                || row.chipText(row.shownRefs[0]).length > row.chipTextLimit;
        return false;
    }
    readonly property int chipLimit: row.compactChips ? 6 : 1

    // -- line --

    TreeLines {
        visible: theme.showTreeLines
        anchors.fill: parent
        branches: theme.showTreeLines ? row.branches : []
        activeFrom: row.activeFrom
        firstX: theme.rowPad + theme.tipGutter + row.guideOffset
        step: theme.indent
        armEnd: row.hasChildren ? expander.x - 1 : icon.x - 6
        headHeight: head.height
        offset: row.y
        ink: theme.overlay ? theme.branchInk : theme.textDim
        opacity: row.isolatedOut ? 0.45 : 1.0
    }

    Item {
        id: head
        width: parent.width
        height: theme.rowHeight
        opacity: (row.dragSource ? 0.3 : 1.0)
                 * (row.isolatedOut ? 0.45 : 1.0)

        // Never animate to/from "transparent" (transparent black flashes grey):
        // keep the colour solid and animate opacity.
        Rectangle {
            id: fill
            y: 1
            height: parent.height - 2
            x: theme.overlay ? icon.x - 5 : 2
            width: theme.overlay
                 ? Math.max(0, tail.x + tail.width + 5 - x)
                 : Math.max(0, parent.width - 4)
            radius: 4

            readonly property color wantColor:
                row.selected ? theme.accent
                : row.pickOrigin ? theme.hover
                : !theme.overlay ? theme.hover
                : hover.hovered ? theme.pillHover
                : theme.pill
            readonly property real want:
                theme.overlay ? 1.0
                : (row.selected || hover.hovered || row.dropTarget
                   || row.slideInto || row.pickOrigin) ? 1.0
                : row.highlighted ? 0.5
                : row.isActive ? 0.28
                : row.isActivePart ? 0.18
                : 0.0
            border.width: row.pickOrigin && !row.selected ? 2
                        : theme.overlay && !row.selected ? 1 : 0
            border.color: row.pickOrigin ? theme.accent : theme.pillBorder

            // Lit at once, let go gently: a pointer swept across the tree
            // answers instantly and leaves a short trail, not a flicker.
            // Set by hand, not by Behaviors, so lighting never waits on
            // which binding Qt happens to update first.
            function settle() {
                fadeOut.stop();
                var lighting = hover.hovered || row.selected
                               || fill.want >= fill.opacity;
                if (lighting) {
                    fill.opacity = fill.want;
                    fill.color = fill.wantColor;
                } else {
                    fadeOut.restart();
                }
            }
            onWantChanged: settle()
            onWantColorChanged: settle()
            Component.onCompleted: {
                fill.opacity = fill.want;
                fill.color = fill.wantColor;
            }
            ParallelAnimation {
                id: fadeOut
                NumberAnimation {
                    target: fill; property: "opacity"; to: fill.want
                    duration: 140; easing.type: Easing.OutQuad
                }
                ColorAnimation {
                    target: fill; property: "color"; to: fill.wantColor
                    duration: 140; easing.type: Easing.OutQuad
                }
            }
        }

        // Glow after a 3D pick scrolls the row into view; overlaid so the
        // selection colour is never animated.
        Rectangle {
            id: flash
            x: fill.x
            y: fill.y
            width: fill.width
            height: fill.height
            radius: fill.radius
            color: "transparent"
            border.width: 2
            border.color: theme.accent
            opacity: 0

            SequentialAnimation {
                id: flashAnimation
                NumberAnimation {
                    target: flash; property: "opacity"
                    to: 1; duration: 120; easing.type: Easing.OutQuad
                }
                PauseAnimation { duration: 450 }
                NumberAnimation {
                    target: flash; property: "opacity"
                    to: 0; duration: 500; easing.type: Easing.InQuad
                }
            }

            Connections {
                target: nxt
                function onFlashRows(names) {
                    if (names.indexOf(row.name) >= 0)
                        flashAnimation.restart();
                }
            }
        }

        // Own outline: the drop target is not hovered while the source holds the grab.
        Rectangle {
            anchors.fill: fill
            radius: fill.radius
            color: "transparent"
            border.width: row.dropTarget || row.slideInto ? 2
                        : row.highlighted ? 1 : 0
            border.color: theme.accent
        }

        // Ancestor guides; hidden in overlay, where they read as model geometry.
        Repeater {
            model: theme.overlay || theme.showTreeLines ? 0 : row.depth
            Rectangle {
                required property int index
                x: theme.rowPad + index * theme.indent + theme.tipGutter
                   + guideOffset
                width: 1
                height: head.height
                color: theme.border
                opacity: 0.5
            }
        }

        // -- active mark --

        Rectangle {
            objectName: "activeMark"
            visible: row.isActive || row.isActivePart
            opacity: row.isActive || row.selected ? 1.0 : 0.7
            x: theme.overlay ? icon.x - 3 : Math.max(1, row.leftPad - 4)
            y: 2
            width: 3
            height: head.height - 4
            radius: 1.5
            color: row.selected ? theme.accentText : theme.accent
        }

        // -- spine: solid where built, dashed past the rollback bar --
        Item {
            id: spine
            // In overlay only past the bar, inside the pill, so rollback
            // is not carried by dimming alone.
            visible: row.bodyName !== "" && (!theme.overlay || row.afterTip)
            x: theme.overlay ? icon.x - 3
                             : row.leftPad + Math.round(theme.tipGutter * 0.45)
            width: 2
            height: head.height

            Rectangle {
                visible: !row.afterTip
                anchors.fill: parent
                color: theme.textDim
                opacity: 0.45
            }

            // Segments rather than a Canvas per row.
            Repeater {
                model: row.afterTip ? 3 : 0
                Rectangle {
                    required property int index
                    width: parent.width
                    height: Math.max(2, Math.round(head.height / 7))
                    y: Math.round(index * head.height / 3)
                       + Math.round(head.height / 12)
                    color: theme.textDim
                    opacity: 0.45
                }
            }
        }

        Disclosure {
            id: expander
            x: row.leftPad + theme.tipGutter
            anchors.verticalCenter: parent.verticalCenter
            shown: row.hasChildren
            expanded: row.expanded
            onToggled: nxt.toggleExpanded(row.name)

            HoverHandler { id: expanderHover }
            NxtToolTip {
                shown: expanderHover.hovered && row.hasChildren
                text: row.expanded ? qsTr("Collapse") : qsTr("Expand")
            }
        }

        Image {
            id: icon
            visible: !row.isTotal
            x: expander.x + expander.width + 2
            anchors.verticalCenter: parent.verticalCenter
            width: theme.iconSize
            height: width
            sourceSize.width: width * 2
            sourceSize.height: width * 2
            source: row.iconUrl + (!row.objectVisible ? "/gray" : "")
            opacity: row.afterTip ? 0.32
                   : row.objectVisible ? 1.0 : 0.38
            Behavior on opacity { NumberAnimation { duration: 110 } }

            HoverHandler { id: iconHover }
            NxtToolTip {
                shown: iconHover.hovered
                text: row.label + (row.name !== row.label
                                   ? "\n" + qsTr("Internal name: %1")
                                                .arg(row.name) : "")
            }
        }

        TextMetrics {
            id: labelMetrics
            font: title.font
            text: row.label
        }

        Text {
            id: title
            visible: !row.renaming
            anchors.verticalCenter: parent.verticalCenter
            x: icon.x + icon.width + 6
            // Must not read tail.x or implicitWidth: binding loop on mode switch.
            width: theme.overlay
                 ? Math.min(labelMetrics.advanceWidth,
                            Math.max(40, head.width - x - 110),
                            host.viewOverlay ? Math.max(40, head.width / 2)
                                             : Infinity)
                 : Math.max(0, head.width - x - tail.width - 16)
            text: row.label
            elide: Text.ElideMiddle
            font.pixelSize: theme.fontRow
            font.bold: row.isContainer
            font.italic: row.isTotal
                         || (!row.objectVisible && !row.isProfile)
            color: row.selected ? theme.accentText
                 : (row.inError && !row.blamedOnProfile) ? theme.danger
                 : row.afterTip ? theme.textDim
                 : row.objectVisible ? theme.text
                 : theme.textDim

            HoverHandler { id: titleHover }
            NxtToolTip {
                shown: titleHover.hovered
                text: row.nameTip
            }
        }

        Rectangle {
            visible: row.renaming
            x: renameInput.x - 4
            y: renameInput.y - 2
            width: renameInput.width + 8
            height: renameInput.height + 4
            radius: 3
            color: theme.background
            border.width: 1
            border.color: theme.accent
        }

        TextInput {
            id: renameInput
            visible: row.renaming
            anchors.verticalCenter: parent.verticalCenter
            x: title.x
            width: theme.overlay
                 ? Math.min(head.width - x - 10,
                            Math.max(160, labelMetrics.advanceWidth + 48))
                 : Math.max(60, head.width - x - 10)
            font: title.font
            color: theme.text
            selectionColor: theme.accent
            selectedTextColor: theme.accentText
            selectByMouse: true
            clip: true

            onEditingFinished: row.commitRename()
            Keys.onEscapePressed: row.cancelRename()
        }

        // -- chips and gutter --

        // x assigned, not anchored, so a mode switch never re-anchors.
        Item {
            id: tail
            y: 0
            height: parent.height
            width: chips.width + (state.width > 0 ? 6 + state.width : 0)
            x: theme.overlay ? title.x + title.width + 6
                             : Math.max(0, head.width - width - 8)

            Row {
                id: chips
                visible: !row.renaming
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left
                spacing: 3

                Rectangle {
                    objectName: "activeChip"
                    visible: row.isActive
                    anchors.verticalCenter: parent.verticalCenter
                    width: activeLabel.implicitWidth + 12
                    height: theme.chipHeight
                    radius: height / 2
                    color: row.selected ? theme.accentText : theme.accent

                    Text {
                        id: activeLabel
                        anchors.centerIn: parent
                        text: qsTr("Active")
                        font.pixelSize: theme.fontSmall
                        font.bold: true
                        color: row.selected ? theme.accent : theme.accentText
                    }
                }

                Chip {
                    objectName: "cycleChip"
                    visible: !!row.cycleTime
                    interactive: false
                    active: row.isTotal
                    text: row.cycleTime
                    tip: row.isTotal ? qsTr("Total cycle time of the active operations")
                                     : qsTr("Estimated cycle time")
                }

                // Shown on the consumer only; the read object lists them in its strip.
                Repeater {
                    model: row.shownRefs.slice(0, row.chipLimit)
                    Chip {
                        required property var modelData
                        compact: row.compactChips
                        text: row.chipText(modelData)
                        sub: modelData.sub
                        iconUrl: modelData.iconUrl
                        severity: modelData.severity
                        onClicked: nxt.revealObjectRow(modelData.name)
                        onDoubleClicked: nxt.activate(modelData.name)
                        tip: row.refTip(modelData)
                    }
                }

                Chip {
                    visible: row.shownRefs.length > row.chipLimit
                    interactive: false
                    text: "+" + (row.shownRefs.length - row.chipLimit)
                    tip: row.moreRefsTip()
                }
            }

            Row {
                id: state
                visible: !row.isTotal
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: chips.right
                anchors.leftMargin: 6
                spacing: 5

                Item {
                    anchors.verticalCenter: parent.verticalCenter
                    width: theme.iconSize
                    height: theme.iconSize

                    EyeToggle {
                        anchors.fill: parent
                        open: row.objectVisible
                        ink: row.selected ? theme.accentText : theme.textDim
                        opacity: row.showControls ? 1.0 : 0.0
                        onToggled: nxt.toggleVisibility(row.name)

                        Behavior on opacity { NumberAnimation { duration: 90 } }

                        HoverHandler { id: eyeHover }
                        NxtToolTip {
                            shown: eyeHover.hovered
                            text: row.objectVisible ? qsTr("Hide")
                                                    : qsTr("Show")
                        }
                    }
                }

                Item {
                    anchors.verticalCenter: parent.verticalCenter
                    width: theme.markSize
                    height: width

                    SeverityMark {
                        id: mark
                        anchors.centerIn: parent
                        size: parent.width
                        level: row.markLevel > 0 ? row.markLevel
                             : (row.hasDetail && row.showControls) ? 1 : 0
                        opacity: row.markLevel > 0 ? 1.0 : 0.45
                        active: row.detailOpen
                        onClicked: nxt.toggleDetail(row.name)
                        onCtrlClicked: row.openInspector()

                        HoverHandler { id: markHover }
                        NxtToolTip {
                            shown: markHover.hovered
                            text: row.detailOpen && row.markLevel === 0
                                  ? qsTr("Hide details") + "\n"
                                    + row.inspectTip
                                  : row.markTip
                        }
                    }
                }
            }
        }

        HoverHandler { id: hover }

        // -- interaction --

        DropArea {
            anchors.fill: parent
            // Reorders find their slot from the ghost (NxtTree.qml).
            enabled: !(row.ListView.view && row.ListView.view.reorderDrag)

            function setGap(open) {
                if (row.ListView.view)
                    row.ListView.view.dropGap = open ? row.index : -1;
            }

            onEntered: function (drag) {
                var says = nxt.dropHint(
                    row.dragGhost ? row.dragGhost.names : [], row.name);
                row.dropTarget = says !== "";
                if (!row.dropTarget) drag.accepted = false;
                setGap(row.dropTarget);
                if (row.dragGhost)
                    row.dragGhost.say(row.dropTarget ? says
                        : qsTr("Can't drop on %1").arg(row.label),
                        row.dropTarget);
                if (row.dropTarget && row.hasChildren && !row.expanded)
                    springOpen.restart();
            }
            onExited: {
                row.dropTarget = false;
                setGap(false);
                springOpen.stop();
                if (row.dragGhost && !row.dragGhost.sliding)
                    row.dragGhost.say("", true);
            }
            onDropped: function (drop) {
                springOpen.stop();
                if (row.dropTarget)
                    nxt.dropOn(row.dragGhost ? row.dragGhost.names : [],
                               row.name);
                row.dropTarget = false;
                setGap(false);
            }

            Timer {
                id: springOpen
                interval: 700
                onTriggered: {
                    if (row.dropTarget && !row.expanded)
                        nxt.toggleExpanded(row.name);
                }
            }
        }

        // z: -1 so this grabbing MouseArea sits under the controls' TapHandlers.
        MouseArea {
            id: press
            // A total row is a sum, not an object: nothing to select or drag.
            enabled: !row.isTotal
            // In the 3D view only the pill takes presses (view_overlay.py).
            x: host.viewOverlay ? row.pillLeft : 0
            width: host.viewOverlay ? row.pillRight - row.pillLeft
                                    : parent.width
            height: parent.height
            z: -1
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            // In head's coordinates.
            property point origin
            property bool armed: false
            // Press on a multi-selection: may start a group drag.
            property bool held: false

            onPressed: function (mouse) {
                if (mouse.button === Qt.RightButton) {
                    var at = mapToItem(null, mouse.x, mouse.y);
                    host.takeKeyboard();
                    if (row.ListView.view)
                        row.ListView.view.forceActiveFocus();
                    nxt.requestContextMenu(row.name, at.x, at.y);
                    return;
                }
                origin = mapToItem(head, mouse.x, mouse.y);
                armed = true;
                var wasSelected = row.selected;
                // The click that brings focus back to the tree only focuses.
                var wasFocused = row.ListView.view
                    && row.ListView.view.activeFocus;
                // The panel itself must hold the keyboard, not just this
                // list inside it: else Space, Delete and the arrows go to
                // whatever widget had focus before (a text field, the
                // console) and act there, or not at all.
                host.takeKeyboard();
                if (row.ListView.view) {
                    row.ListView.view.currentIndex = row.index;
                    row.ListView.view.forceActiveFocus();
                }
                var additive = (mouse.modifiers & Qt.ControlModifier) !== 0;
                var range = (mouse.modifiers & Qt.ShiftModifier) !== 0;
                held = wasSelected && !additive && !range
                       && nxt.dragNames(row.name).length > 1;
                if (range)
                    nxt.selectRange(row.name);
                else if (!held)
                    nxt.select(row.name, additive);
                if (wasSelected && wasFocused && !additive && !held
                        && !row.renaming
                        && row.overGlyphs(origin.x, origin.y))
                    row.armRename();
            }

            onPositionChanged: function (mouse) {
                if (!armed || !row.dragGhost || row.dragGhost.cancelled)
                    return;
                var here = mapToItem(row.dragGhost.parent, mouse.x, mouse.y);
                if (!row.dragGhost.Drag.active) {
                    var at = mapToItem(head, mouse.x, mouse.y);
                    if (Math.abs(at.x - origin.x)
                            + Math.abs(at.y - origin.y) < 8)
                        return;
                    row.disarmRename();
                    var names = held ? nxt.dragNames(row.name) : [row.name];
                    // Container members slide (reorder); others carry a label.
                    var container = nxt.slideContainer(names);
                    var sliding = container !== "";
                    var cropLeft = theme.overlay ? Math.max(0, row.pillLeft - 2)
                                                 : 0;
                    var cropWidth = theme.overlay
                                  ? row.pillRight + 2 - cropLeft
                                  : head.width;
                    row.dragGhost.container = container;
                    row.dragGhost.inBody = row.bodyName !== "";
                    row.dragGhost.sourceDepth = row.depth;
                    row.dragGhost.begin(
                        names,
                        names.length > 1
                            ? qsTr("%1 objects").arg(names.length)
                            : row.label,
                        row.iconUrl,
                        sliding ? Qt.point(origin.x - cropLeft, origin.y)
                                : null);
                    if (sliding) {
                        row.dragGhost.picture(head, cropLeft, cropWidth,
                                              head.height);
                        var corner = row.mapToItem(row.dragGhost.parent, 0, 0);
                        row.dragGhost.x = corner.x + cropLeft;
                    }
                }
                if (row.dragGhost.sliding) {
                    row.dragGhost.y = here.y - origin.y;
                } else {
                    row.dragGhost.x = here.x + 10;
                    row.dragGhost.y = here.y + 6;
                }
            }

            onReleased: {
                armed = false;
                if (row.dragGhost && row.dragGhost.cancelled) {
                    row.dragGhost.cancelled = false;  // Escape ended it
                    held = false;
                    return;
                }
                if (row.dragGhost && row.dragGhost.Drag.active)
                    row.dragGhost.finish();
                else if (held)
                    nxt.select(row.name, false);    // a click after all
                held = false;
            }

            // The press was taken away (a dialog, another grab): no drop.
            onCanceled: {
                armed = false;
                held = false;
                if (row.dragGhost && row.dragGhost.Drag.active)
                    row.dragGhost.cancel();
                if (row.dragGhost)
                    row.dragGhost.cancelled = false;
            }

            // Opens the object anywhere on the row; cancels a pending rename.
            onDoubleClicked: function (mouse) {
                row.disarmRename();
                nxt.activate(row.name);
            }
        }
    }

    // -- detail --

    Item {
        id: detail
        objectName: "detail"
        anchors.top: head.bottom
        width: Math.min(parent.width, row.detailCap)
        height: row.showDetail && detailLoader.item
                ? detailLoader.item.implicitHeight : 0
        visible: row.showDetail
        clip: true

        // Built only while open: a strip per row made long trees slow to
        // scroll.
        Loader {
            id: detailLoader
            width: parent.width
            active: row.showDetail
            sourceComponent: Component {
                Item {
                    width: detailLoader.width
                    height: implicitHeight
                    implicitHeight: content.implicitHeight

                Rectangle {
                    anchors.fill: parent
                    anchors.leftMargin: row.detailLeft
                    anchors.rightMargin: 8
                    anchors.bottomMargin: 3
                    radius: 4
                    color: theme.chip
                    opacity: theme.overlay ? 0.0 : 0.55
                }

                Rectangle {
                    visible: theme.overlay
                    anchors.fill: parent
                    anchors.leftMargin: row.detailLeft
                    anchors.rightMargin: 8
                    anchors.bottomMargin: 3
                    radius: 4
                    color: theme.pill
                    border.width: 1
                    border.color: theme.pillBorder
                }

                Rectangle {
                    visible: row.detailLeft < row.pillLeft - 1
                    x: row.pillLeft
                    y: 0
                    width: 14
                    height: 2
                    radius: 1
                    color: theme.accent
                }

                Item {
                    id: closeButton
                    z: 2
                    anchors.right: parent.right
                    anchors.rightMargin: 10
                    y: 2
                    width: 18
                    height: 18

                    Rectangle {
                        anchors.fill: parent
                        radius: 3
                        color: theme.hover
                        visible: closeMouse.containsMouse
                    }
                    Text {
                        anchors.centerIn: parent
                        text: "\u00d7"
                        font.pixelSize: theme.fontRow
                        color: closeMouse.containsMouse ? theme.text : theme.textDim
                    }
                    MouseArea {
                        id: closeMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: nxt.toggleDetail(row.name)
                    }
                    Accessible.role: Accessible.Button
                    Accessible.name: qsTr("Close details")
                }

                Item {
                    id: pinButton
                    objectName: "detailPin"
                    readonly property bool pinned:
                        nxt.pinnedDetails.indexOf(row.name) >= 0
                    visible: nxt.detailAutoShow
                    z: 2
                    anchors.right: closeButton.left
                    anchors.rightMargin: 2
                    y: 2
                    width: visible ? 18 : 0
                    height: 18

                    Rectangle {
                        anchors.fill: parent
                        radius: 3
                        color: pinButton.pinned ? theme.accent : theme.hover
                        visible: pinButton.pinned || pinMouse.containsMouse
                    }
                    Rectangle {
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: 4
                        width: 8
                        height: 5
                        radius: 1.5
                        color: pinButton.pinned ? theme.accentText
                             : pinMouse.containsMouse ? theme.text : theme.textDim
                    }
                    Rectangle {
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: 9
                        width: 2
                        height: 5
                        color: pinButton.pinned ? theme.accentText
                             : pinMouse.containsMouse ? theme.text : theme.textDim
                    }
                    MouseArea {
                        id: pinMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: nxt.toggleDetailPin(row.name)
                    }
                    NxtToolTip {
                        shown: pinMouse.containsMouse
                        text: pinButton.pinned ? qsTr("Unpin")
                                               : qsTr("Keep these details open")
                    }
                    Accessible.role: Accessible.Button
                    Accessible.name: qsTr("Keep these details open")
                }

                DetailStrip {
                    id: content
                    owner: row.name             // in the active document
                    x: row.detailLeft + 8
                    width: Math.max(40, parent.width - x - 14 - closeButton.width
                                        - pinButton.width)
                    level: row.markLevel
                    notes: row.notes
                    dof: row.dof
                    constrained: row.constrained
                    consumers: row.consumers
                    refs: row.refs
                    isProfile: row.isProfile
                    isLifted: row.isLifted
                    keyProps: row.keyProps
                    objectKey: row.name
                    isVarSet: row.typeId === "App::VarSet"
                    propertyCount: row.propertyCount
                    onKeyEdited: function (prop, value) {
                        nxt.setKeyProperty(row.name, prop, value);
                    }
                    onAllPropertiesRequested: row.openInspector()
                    onConsumerClicked: function (name) { nxt.revealObjectRow(name); }
                    onReferenceClicked: function (name) { nxt.revealObjectRow(name); }
                    onChipActivated: function (name) { nxt.activate(name); }
                }
                }
            }
        }
    }
}
