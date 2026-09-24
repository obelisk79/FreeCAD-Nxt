import QtQuick
import Nxt

// Root of the Nxt model panel.
//
// One list. A container's children are drawn in the order they were made,
// so a Body reads as a record of the work: sketch, the feature that used
// it, the next sketch, the next feature. Sketches are lifted out of the
// feature that claims them and placed as siblings, because a consumer does
// not own a sketch - the next feature may use the same one - and nesting
// would file a sketch at the point it was first used rather than when it
// was drawn.
//
// This replaced a two-pane layout with the sketches in a shelf below. The
// shelf made reuse obvious and sequence impossible to see; since a sketch
// is built on geometry that existed at one moment, sequence turned out to
// be the thing worth showing. Reuse is now carried by the reference chips
// on the consuming feature.
//
// Deliberately free of QtQuick.Controls: this widget is embedded in a host
// whose Qt style we do not control, and the handful of primitives we need
// are cheaper to draw than to restyle.
Rectangle {
    id: root
    color: theme.canvas
    implicitWidth: 280
    implicitHeight: 520

    readonly property int headerHeight: Math.round(theme.rowHeight * 1.25)

    // What the search field is never squeezed below, including its margins.
    // Below about this it stops being able to show a query and stops being
    // worth the space it takes from the document name.
    readonly property int searchFloor: 128

    // The widest the header and a row's detail strip may grow: a share of
    // the screen, so it adapts to resolution and follows the panel to
    // another monitor, with a floor that keeps them usable on small
    // screens. Screen.width is 0 until the panel is shown, so it waits.
    readonly property real contentCap: Screen.width > 0
        ? Math.max(theme.headerMinWidth,
                   Screen.width * theme.headerMaxPercent / 100)
        : width

    // ================================================================ header

    Item {
        id: header
        objectName: "header"
        width: Math.min(parent.width, root.contentCap)
        height: root.headerHeight
        // Above the list, so the search results can hang over it.
        z: 100

        // The header needs a backdrop of its own in overlay mode for the
        // same reason the rows do. Full width rather than content width:
        // it holds the search field, which is a target, not a label.
        Rectangle {
            anchors.fill: parent
            anchors.margins: 2
            radius: 4
            visible: theme.overlay
            color: theme.pill
            border.width: 1
            border.color: theme.pillBorder
        }

        Text {
            id: docLabel
            anchors.verticalCenter: parent.verticalCenter
            x: 9
            // The name gets the room it asks for, and only gives way once
            // the search field is down to something usable. A flat
            // percentage truncated "PartDesignExample" while the field beside
            // it sat half empty - the field is elastic and the name is not,
            // so the name is what should be measured first.
            width: Math.min(implicitWidth,
                            Math.max(52, parent.width - x - searchFloor
                                     - (problems.visible ? problems.width + 8
                                                         : 0)))
            text: nxt.hasDocument ? nxt.documentLabel : qsTr("No document")
            elide: Text.ElideMiddle
            font.pixelSize: theme.fontRow
            font.bold: true
            color: nxt.hasDocument ? theme.text : theme.textDim
        }

        // How many sketches need attention, and a way to the first of them.
        // The plain profile count that used to sit beside it was cut: it was
        // large, stable and had nothing for the user to do about it. This
        // one is none of those things.
        Row {
            id: problems
            anchors.left: docLabel.right
            anchors.leftMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            spacing: 4
            visible: nxt.problemCount > 0

            SeverityMark {
                anchors.verticalCenter: parent.verticalCenter
                level: 2
                size: theme.markSizeSmall
            }

            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: nxt.problemCount
                font.pixelSize: theme.fontSmall
                font.bold: true
                color: theme.textDim
            }

            HoverHandler { cursorShape: Qt.PointingHandCursor }
            TapHandler { onTapped: nxt.revealFirstProblem() }
        }

        SearchBox {
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: problems.visible ? problems.right : docLabel.right
            anchors.leftMargin: 10
            anchors.right: parent.right
            anchors.rightMargin: 8
            placeholder: qsTr("search")
            results: nxt.searchResults
            onQueryChanged: function (value) { nxt.setSearch(value); }
            onChosen: function (name) { nxt.revealObject(name); }
        }

        Rectangle {
            anchors.bottom: parent.bottom
            width: root.width       // the divider spans the panel
            height: 1
            visible: !theme.overlay
            color: theme.border
        }
    }

    // ================================================================== tree

    Item {
        id: treePane
        anchors.top: header.bottom
        anchors.bottom: parent.bottom
        width: parent.width

        ListView {
            id: treeList
            anchors.fill: parent
            anchors.topMargin: 3
            clip: true
            model: nxt.treeModel
            boundsBehavior: Flickable.StopAtBounds
            flickableDirection: Flickable.VerticalFlick
            cacheBuffer: 400
            focus: true
            // Up and Down are the panel's, not the list's: they move the
            // selection, which the list's own key navigation does not.
            keyNavigationEnabled: false

            // Which row, if any, has opened a space under it for something
            // being dragged. Two sources that cannot both be active - you
            // are either dragging an object or dragging the bar - kept
            // separate so neither has to clear the other's state.
            property int barGap: -1
            property int dropGap: -1
            readonly property int gapAfterRow: barGap >= 0 ? barGap : dropGap

            delegate: TreeRow { dragGhost: ghost; detailCap: root.contentCap }

            // A translucent QQuickWidget composites over what is behind it,
            // but changing content does not ask that surface to redraw - so
            // without this, the previous frame's pills stay stranded in the
            // transparent gaps until something unrelated repaints. Scrolling
            // moves them; expanding a branch and resizing move them too, so
            // every signal that can is wired up. The call is coalesced on
            // the other side, so this is cheap.
            onContentYChanged: if (theme.overlay) host.repaintBehind()
            onContentHeightChanged: if (theme.overlay) host.repaintBehind()
            onCountChanged: if (theme.overlay) host.repaintBehind()
            onHeightChanged: if (theme.overlay) host.repaintBehind()
        }

        // Timeline bars, one per Body with a visible history. An overlay
        // rather than list rows: rows are a uniform height, so a row's y is
        // arithmetic, and the model stays a plain sequence of objects.
        Item {
            id: tipLayer
            anchors.fill: parent
            clip: true
            z: 5

            Repeater {
                model: nxt.tipBars

                TimelineBar {
                    required property var modelData

                    // Starts at the Body's indent, because it is a
                    // position in that Body's history rather than a handle
                    // attached to one row. Where it *ends* is the bar's own
                    // business - see TimelineBar.
                    x: theme.rowPad + modelData.depth * theme.indent
                    body: modelData.body
                    pos: modelData.pos
                    minPos: modelData.minPos
                    maxPos: modelData.maxPos
                    rowHeight: theme.rowHeight
                    list: treeList
                    fullWidth: treeList.width
                    listContentY: treeList.contentY
                    listTopMargin: treeList.anchors.topMargin

                    onDragPosChanged: if (dragging) treeList.barGap = dragPos
                    onDraggingChanged: treeList.barGap = dragging ? dragPos : -1
                }
            }
        }

        ScrollHint { target: treeList }

        Text {
            anchors.centerIn: parent
            visible: treeList.count === 0
            text: nxt.hasDocument ? qsTr("This document is empty")
                                  : qsTr("Open or create a document")
            color: theme.textDim
            font.pixelSize: theme.fontRow
        }
    }

    // ============================================================ drag ghost

    Item {
        id: ghost
        z: 1000
        width: label.implicitWidth + 34
        height: theme.rowHeight
        visible: Drag.active

        property var names: []

        Drag.active: false
        Drag.hotSpot.x: 12
        Drag.hotSpot.y: height / 2

        function begin(objectNames, text, icon) {
            names = objectNames;
            label.text = text;
            ghostIcon.source = icon;
            Drag.active = true;
        }

        function finish() {
            Drag.drop();
            Drag.active = false;
            names = [];
        }

        Rectangle {
            anchors.fill: parent
            radius: 4
            color: theme.accent
            opacity: 0.92

            Image {
                id: ghostIcon
                x: 6
                anchors.verticalCenter: parent.verticalCenter
                width: theme.markSize
                height: width
                sourceSize.width: width * 2
                sourceSize.height: width * 2
            }

            Text {
                id: label
                anchors.verticalCenter: parent.verticalCenter
                x: ghostIcon.x + ghostIcon.width + 6
                font.pixelSize: theme.fontRow
                color: theme.accentText
            }
        }
    }

    // ============================================================= keyboard

    // Driven by the selection rather than by the list's currentIndex, so a
    // key does the same thing wherever the row happens to be - and so it
    // agrees with what the 3D view and the rest of FreeCAD consider current.
    // A focused TextInput consumes these first, so typing a space into the
    // search box or a rename field does not toggle anything.
    Keys.onPressed: function (event) {
        if (event.key === Qt.Key_F2) {
            var row = nxt.treeRenameRow();
            if (row >= 0) {
                treeList.positionViewAtIndex(row, ListView.Contain);
                var item = treeList.itemAtIndex(row);
                if (item)
                    item.beginRename();
            }
            event.accepted = true;
        } else if (event.key === Qt.Key_Space) {
            nxt.toggleSelectedVisibility();
            event.accepted = true;
        } else if (event.key === Qt.Key_Up || event.key === Qt.Key_Down) {
            var target = nxt.stepSelection(
                event.key === Qt.Key_Up ? -1 : 1,
                (event.modifiers & Qt.ShiftModifier) !== 0);
            if (target >= 0)
                treeList.positionViewAtIndex(target, ListView.Contain);
            event.accepted = true;
        } else if (event.key === Qt.Key_Left || event.key === Qt.Key_Right) {
            var row = nxt.stepBranch(event.key === Qt.Key_Right ? 1 : -1);
            if (row >= 0)
                treeList.positionViewAtIndex(row, ListView.Contain);
            event.accepted = true;
        }
    }

    // ====================================================== reveal plumbing

    Connections {
        target: nxt
        function onRevealTreeRow(row) {
            treeList.positionViewAtIndex(row, ListView.Contain);
        }
        // The inspector opens from the row, which knows where its own edge is.
        function onPropertyInspectorRequested(row) {
            treeList.positionViewAtIndex(row, ListView.Contain);
            var item = treeList.itemAtIndex(row);
            if (item)
                item.openInspector();
            else
                nxt.openPropertyInspector("", -1, -1);
        }
    }
}
