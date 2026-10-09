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

    // Nxt's overlay (view_overlay.py): does a press at (x, y) land on
    // something the panel draws? Asked for every press before it is
    // delivered: a point on a pill, the header, a strip or a rollback bar
    // is the panel's; anything else goes straight to the 3D view. Asked,
    // not inferred from whether the scene accepted the press - a tap
    // handler on a chip takes a press without accepting it, and the chip's
    // click was lost to the model.
    function wantsPoint(x, y) {
        if (header.contains(header.mapFromItem(root, x, y)))
            return true;
        if (breadcrumb.visible
                && breadcrumb.contains(breadcrumb.mapFromItem(root, x, y)))
            return true;
        var bar = tipLayer.childAt(x - tipLayer.x, y - treePane.y);
        if (bar !== null)
            return true;
        var p = treeList.mapFromItem(root, x, y);
        var index = treeList.indexAt(p.x + treeList.contentX,
                                     p.y + treeList.contentY);
        if (index < 0)
            return false;
        var row = treeList.itemAtIndex(index);
        if (!row)
            return false;
        var r = row.mapFromItem(root, x, y);
        return row.wantsPoint(r.x, r.y);
    }

    // Nxt's overlay: the wheel over the panel scrolls the list (see
    // view_overlay.py; the list itself takes no input there, so that the
    // wheel elsewhere zooms the model). `angle` is in eighths of a degree,
    // as Qt reports a wheel; `pixel` is a touchpad's own distance, if any.
    function scrollWheel(angle, pixel) {
        // Over a breadcrumb too long for its strip, the wheel scrolls the
        // trail, as it does docked.
        if (breadcrumb.visible && breadcrumb.hovered && breadcrumb.overflows) {
            breadcrumb.scrollBy(pixel !== 0 ? pixel : angle / 120 * 40);
            return;
        }
        var step = pixel !== 0 ? pixel
                               : angle / 120 * theme.rowHeight * 3;
        var top = treeList.originY;
        var bottom = Math.max(top, top + treeList.contentHeight
                                   - treeList.height);
        treeList.contentY = Math.max(top, Math.min(bottom,
                                                   treeList.contentY - step));
    }

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

        // The document's name is the top level of its tree: drop a row on
        // it to move the object out of its container, as onto the stock
        // tree's document row.
        Rectangle {
            anchors.fill: docLabel
            anchors.margins: -3
            radius: 4
            color: theme.hover
            border.width: 1
            border.color: theme.accent
            visible: docDrop.accepting
        }
        RootDropArea {
            id: docDrop
            anchors.fill: docLabel
            anchors.margins: -3
            ghost: ghost
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
            anchors.right: dockButton.visible ? dockButton.left : gear.left
            anchors.rightMargin: 4
            placeholder: qsTr("search")
            results: nxt.searchResults
            onQueryChanged: function (value) { nxt.setSearch(value); }
            onChosen: function (name) { nxt.revealObject(name); }
        }

        // Inside the 3D view (Nxt's overlay) the dock and its title bar are
        // hidden, so the way back is here: put the panel back in its dock.
        Item {
            id: dockButton
            objectName: "dockButton"
            visible: host.viewOverlay
            anchors.verticalCenter: parent.verticalCenter
            anchors.right: gear.left
            anchors.rightMargin: 2
            width: gear.width
            height: width

            Rectangle {
                anchors.fill: parent
                radius: 4
                color: theme.hover
                visible: dockHover.hovered
            }

            // A window with its left side filled: the panel, docked.
            Canvas {
                anchors.centerIn: parent
                width: Math.round(parent.width * 0.66)
                height: Math.round(width * 0.8)
                antialiasing: true
                property color ink: dockHover.hovered ? theme.text
                                                      : theme.textDim
                onInkChanged: requestPaint()
                onWidthChanged: requestPaint()
                onPaint: {
                    var ctx = getContext("2d");
                    ctx.reset();
                    var line = Math.max(1, Math.round(width / 12));
                    ctx.strokeStyle = ink;
                    ctx.fillStyle = ink;
                    ctx.lineWidth = line;
                    ctx.strokeRect(line / 2, line / 2,
                                   width - line, height - line);
                    ctx.fillRect(0, 0, Math.round(width * 0.36), height);
                }
            }

            HoverHandler {
                id: dockHover
                cursorShape: Qt.PointingHandCursor
            }
            TapHandler { onTapped: host.leaveViewOverlay() }
            NxtToolTip {
                shown: dockHover.hovered
                text: qsTr("Back to the dock")
            }

            Accessible.role: Accessible.Button
            Accessible.name: qsTr("Back to the dock")
        }

        // The tree's quick settings. In the header rather than the title
        // bar: FreeCAD's overlay mode replaces the title bar, and the
        // header is the one part of the panel that is always there.
        Item {
            id: gear
            objectName: "gear"
            anchors.verticalCenter: parent.verticalCenter
            anchors.right: parent.right
            anchors.rightMargin: 6
            width: Math.round(theme.rowHeight * 0.9)
            height: width

            Rectangle {
                anchors.fill: parent
                radius: 4
                color: theme.hover
                visible: gearMouse.containsMouse || root.settingsOpen
            }

            // Drawn, so it takes the theme's colour in light and dark.
            Canvas {
                id: gearIcon
                anchors.centerIn: parent
                width: Math.round(parent.width * 0.7)
                height: width
                antialiasing: true
                property color ink: gearMouse.containsMouse
                                    ? theme.text : theme.textDim
                onInkChanged: requestPaint()
                onWidthChanged: requestPaint()
                onPaint: {
                    var ctx = getContext("2d");
                    ctx.reset();
                    var c = width / 2, outer = width / 2, inner = outer * 0.72;
                    var teeth = 8;
                    ctx.fillStyle = ink;
                    ctx.beginPath();
                    for (var i = 0; i < teeth * 2; ++i) {
                        var r = i % 2 === 0 ? outer : inner;
                        var a0 = (i - 0.5) * Math.PI / teeth;
                        var a1 = (i + 0.5) * Math.PI / teeth;
                        ctx.lineTo(c + r * Math.cos(a0), c + r * Math.sin(a0));
                        ctx.lineTo(c + r * Math.cos(a1), c + r * Math.sin(a1));
                    }
                    ctx.closePath();
                    // The hub, cut out.
                    ctx.moveTo(c + outer * 0.32, c);
                    ctx.arc(c, c, outer * 0.32, 0, 2 * Math.PI, true);
                    ctx.fill("evenodd");
                }
            }

            MouseArea {
                id: gearMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.toggleSettings()
            }

            Accessible.role: Accessible.Button
            Accessible.name: qsTr("Tree settings")
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

        // Docked, empty space below the rows is the document's top level:
        // a row dropped there leaves its container. Beneath the list, so a
        // row under the pointer is always the target first. Not in Nxt's
        // overlay, where empty space is the model's - the header's name is
        // the way there.
        RootDropArea {
            anchors.fill: parent
            z: -1
            enabled: !host.viewOverlay
            ghost: ghost
            allowAt: function (x, y) {
                return treeList.indexAt(x, y - treeList.y
                                           + treeList.contentY) < 0;
            }
        }

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
            // Inside the 3D view (Nxt's own overlay) the list does not
            // take presses or drags on its empty space - they belong to
            // the model behind, and reach it by propagation
            // (view_overlay.py).
            interactive: !host.viewOverlay

            // Which row, if any, has opened a space under it for something
            // being dragged. Two sources that cannot both be active - you
            // are either dragging an object or dragging the bar - kept
            // separate so neither has to clear the other's state.
            property int barGap: -1
            property int dropGap: -1
            readonly property int gapAfterRow: barGap >= 0 ? barGap : dropGap
            // The rows being dragged, and whether the drag is a reorder
            // within a Body (see the drag ghost below).
            property var dragSources: []
            // A row kept where it is on screen while strips above it
            // open and close (auto-show; see the bridge's rowHeld).
            property int heldRow: -1
            property real heldOffset: 0
            property bool reorderDrag: false

            delegate: TreeRow { dragGhost: ghost; detailCap: root.contentCap }

            // One empty row after the last: scrolled to the end, the last
            // row - and a rollback bar under it - is never jammed against
            // the bottom edge.
            footer: Item {
                width: treeList.width
                height: theme.rowHeight
            }

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

        // The containers the top of the list is inside, once their rows
        // have scrolled away: pinned over the top of the list.
        Breadcrumb {
            id: breadcrumb
            objectName: "breadcrumb"
            z: 50
            // Docked it spans the panel, as the header's divider does; in
            // Nxt's overlay it is a pill the width of the header's.
            width: theme.overlay ? header.width : parent.width

            //: The row just under the strip, and every container of it.
            property int under: -1
            property var containers: []

            // `changed`: the rows themselves did, so the same row number
            // may be another object now.
            function refresh(changed) {
                var at = treeList.indexAt(0, treeList.contentY + height);
                if (at === under && !changed)
                    return;
                under = at;
                containers = (at >= 0 && nxt.breadcrumb(at)) || [];
            }

            // Only those out of sight: a container still on screen is
            // its own heading. A row too far off to exist is out of sight.
            crumbs: containers.filter(function (crumb) {
                var item = treeList.itemAtIndex(crumb.row);
                return item === null || item.y < treeList.contentY;
            })
            // Under the strip, not behind it.
            onCrumbClicked: function (row) {
                treeList.positionViewAtIndex(row, ListView.Beginning);
                treeList.contentY = Math.max(treeList.originY,
                                             treeList.contentY - height);
            }

            Connections {
                target: treeList
                function onContentYChanged() { breadcrumb.refresh(false); }
            }
            Connections {
                target: nxt.treeModel
                function onModelReset() { breadcrumb.refresh(true); }
                function onRowsInserted() { breadcrumb.refresh(true); }
                function onRowsRemoved() { breadcrumb.refresh(true); }
                function onDataChanged() { breadcrumb.refresh(true); }
            }
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

        // The selection's dependencies, over the list's right edge.
        DependencyArrows {
            anchors.fill: treeList
            list: treeList
            z: 4
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
        width: sliding ? shot.width : label.implicitWidth + 34
        height: theme.rowHeight
        visible: Drag.active

        property var names: []
        // Sliding: a reorder within a Body. The ghost is then a picture of
        // the row itself, locked to its column and held at the point it was
        // grabbed, so the row moves rather than a label beside the pointer.
        property bool sliding: false
        // While sliding: the row it would be dropped after, if the drop
        // is allowed there, and what the panel said about each row asked.
        property string slideTarget: ""
        property var verdicts: ({})

        Drag.active: false
        Drag.hotSpot.x: 12
        Drag.hotSpot.y: height / 2

        function begin(objectNames, text, icon, grabbedAt) {
            names = objectNames;
            label.text = text;
            ghostIcon.source = icon;
            sliding = grabbedAt !== null && grabbedAt !== undefined;
            shot.sourceItem = null;
            slideTarget = "";
            verdicts = ({});
            // The drop target is the row under the pointer, so the hot spot
            // is the point that was grabbed.
            Drag.hotSpot.x = sliding ? grabbedAt.x : 12;
            Drag.hotSpot.y = sliding ? grabbedAt.y : height / 2;
            treeList.dragSources = objectNames;
            treeList.reorderDrag = sliding;
            Drag.active = true;
        }

        // The row's picture: the part of `item` from `left`, `w` wide.
        // Drawn by the scene graph in the next frame, not grabbed to an
        // image: grabToImage answers asynchronously, and in a panel that
        // was not repainting it could fail to answer at all - the label
        // stood in until something (switching windows) made the panel
        // redraw. Cropped, so in an overlay the picture is the pill, not
        // a bar the width of the 3D view.
        function picture(item, left, w, h) {
            if (!Drag.active)
                return;
            shot.width = w;
            shot.height = h;
            shot.sourceRect = Qt.rect(left, 0, w, h);
            shot.sourceItem = item;
            shot.scheduleUpdate();
        }

        function finish() {
            if (sliding) {
                Drag.active = false;
                if (slideTarget !== "")
                    nxt.dropOn(names, slideTarget);
                treeList.dropGap = -1;
            } else {
                Drag.drop();
                Drag.active = false;
            }
            names = [];
            sliding = false;
            shot.sourceItem = null;
            treeList.dragSources = [];
            treeList.reorderDrag = false;
        }

        // A drag moves pixels over the translucent surface in overlay mode;
        // see treeList's onContentYChanged.
        onYChanged: {
            if (!Drag.active)
                return;
            if (sliding)
                slide();
            if (theme.overlay)
                host.repaintBehind();
        }

        function allowed(target) {
            if (verdicts[target] === undefined)
                verdicts[target] = nxt.canDropOn(names, target);
            return verdicts[target];
        }

        // Opens the gap where the dragged row is, so it sits over the
        // space it will drop into. Worked out on the list as it would be
        // with no gap open: the gap moves rows, and measuring rows that
        // are moving because of the answer would make the answer flicker.
        // The slot chosen is the row boundary nearest the dragged row's
        // top edge; the gap opens there, a row high, under the ghost.
        function slide() {
            var want = ghost.mapToItem(treeList.contentItem, 0, 0).y;
            var first = treeList.indexAt(10, treeList.contentY);
            var last = treeList.indexAt(10, treeList.contentY
                                            + treeList.height);
            if (first < 0) first = 0;
            if (last < 0) last = treeList.count - 1;
            var gapRow = treeList.dropGap;
            var open = gapRow >= 0 ? treeList.itemAtIndex(gapRow) : null;
            var shift = open ? open.gap : 0;
            var best = -1, bestDistance = 1e9;
            for (var i = first; i <= last; ++i) {
                var item = treeList.itemAtIndex(i);
                if (!item)
                    continue;
                var top = item.y - (gapRow >= 0 && i > gapRow ? shift : 0);
                var bottom = top + item.height - (i === gapRow ? shift : 0);
                var distance = Math.abs(bottom - want);
                if (distance < bestDistance) {
                    bestDistance = distance;
                    best = i;
                }
            }
            var target = best >= 0 ? treeList.itemAtIndex(best).name : "";
            var ok = target !== "" && allowed(target);
            slideTarget = ok ? target : "";
            treeList.dropGap = ok ? best : -1;
        }

        ShaderEffectSource {
            id: shot
            // Once taken, not redrawn: the row it shows is dimmed while it
            // is being dragged, and the copy keeps it as it was. (A copy
            // leaves out its source's own opacity, so the dimming would
            // not show in it anyway.)
            live: false
            hideSource: false
            visible: ghost.sliding && sourceItem !== null

            // Lifted: a shadow line under it and a little transparency, so
            // it reads as held above the list rather than part of it.
            opacity: 0.95
            Rectangle {
                anchors.fill: parent
                z: -1
                radius: 4
                color: theme.surface
                border.width: 1
                // Accent where it can drop; plain where it cannot.
                border.color: ghost.slideTarget !== "" ? theme.accent
                                                       : theme.border
            }

            // How many are in hand, when the picture shows only the one
            // that was grabbed.
            Rectangle {
                visible: ghost.names.length > 1
                anchors.right: parent.right
                anchors.rightMargin: -6
                anchors.verticalCenter: parent.top
                width: Math.max(height, count.implicitWidth + 8)
                height: theme.chipHeight
                radius: height / 2
                color: theme.accent

                Text {
                    id: count
                    anchors.centerIn: parent
                    text: ghost.names.length
                    font.pixelSize: theme.fontSmall
                    font.bold: true
                    color: theme.accentText
                }
            }
        }

        Rectangle {
            anchors.fill: parent
            visible: !shot.visible
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

    // ========================================================= context menu

    Component {
        id: contextMenuComponent
        ContextMenu {}
    }

    // What the context menu opens from: a point, not a control. Under
    // Wayland a menu in a window of its own is placed against the whole
    // rectangle of the item it opens from - opened from the panel, it sat
    // at the panel's bottom-left corner - so it opens from this one-pixel
    // item, moved to the click first. See host.menuAnchorOffset().
    Item {
        id: menuAnchor
        width: 1
        height: 1
    }

    // Built afresh for each opening, from the selection as it is now:
    // where the row was right-clicked, or under a row from the keyboard.
    // The menu is a window of its own (see ContextMenu.qml).
    // The gear's quick settings: one at a time, opened below the gear with
    // its right edge on the gear's, from the same anchor the context menu
    // uses (see menuAnchor).
    property bool settingsOpen: false
    property var settingsPopup: null
    // When the popup last closed, in ms. A press on the gear while the
    // popup is open closes it (a press outside it) before the gear's click
    // arrives - and the click then opened it again. A click that lands
    // just after a close is that same press, so it does not reopen.
    property double settingsClosedAt: 0

    // The gear: open the settings, or close them if they are open.
    function toggleSettings() {
        if (settingsOpen) {
            if (settingsPopup)
                settingsPopup.close();
            return;
        }
        if (Date.now() - settingsClosedAt < 300)
            return;
        openSettings();
    }

    function openSettings() {
        if (settingsOpen)
            return;
        var popup = settingsComponent.createObject(root);
        settingsPopup = popup;
        var at = gear.mapToItem(root, gear.width - popup.width, gear.height);
        var offset = host.menuAnchorOffset();
        menuAnchor.x = Math.max(0, at.x) + offset.x;
        menuAnchor.y = at.y + 2 + offset.y;
        popup.parent = menuAnchor;
        popup.x = 0;
        popup.y = 0;
        settingsOpen = true;
        popup.closed.connect(function () {
            root.settingsOpen = false;
            root.settingsPopup = null;
            root.settingsClosedAt = Date.now();
            treeList.forceActiveFocus();
        });
        popup.open();
    }

    Component {
        id: settingsComponent
        TreeSettings {}
    }

    function openContextMenu(rowItem, x, y) {
        var data = nxt.contextMenu();
        if (!data || !data.bar)
            return;
        var menu = contextMenuComponent.createObject(root);
        menu.load(data);
        // Run once the menu has gone, so a command that opens a dialog or
        // a task panel does not start underneath it.
        menu.chosen.connect(function (command) {
            Qt.callLater(function () { nxt.runMenuItem(command); });
        });
        menu.closed.connect(function () { treeList.forceActiveFocus(); });
        var at = rowItem
            ? rowItem.mapToItem(root, theme.rowPad + theme.indent,
                                rowItem.height)
            : Qt.point(x, y);
        var offset = host.menuAnchorOffset();
        menuAnchor.x = at.x + offset.x;
        menuAnchor.y = at.y + offset.y;
        menu.parent = menuAnchor;
        menu.popup(menuAnchor, 0, 0);
    }

    function startRename(row) {
        if (row < 0)
            return;
        treeList.positionViewAtIndex(row, ListView.Contain);
        var item = treeList.itemAtIndex(row);
        if (item)
            item.beginRename();
    }

    // ============================================================= keyboard

    // Driven by the selection rather than by the list's currentIndex, so a
    // key does the same thing wherever the row happens to be - and so it
    // agrees with what the 3D view and the rest of FreeCAD consider current.
    // A focused TextInput consumes these first, so typing a space into the
    // search box or a rename field does not toggle anything.
    // Space is also a FreeCAD shortcut (toggle visibility), and a shortcut
    // is offered the key before the panel is: FreeCAD's command then ran
    // in place of the handler below, without the Part Design handling in
    // toggleSelectedVisibility. Claiming the key here keeps it for the
    // panel while the panel has the keyboard.
    // Home and End likewise: Home is FreeCAD's "home view".
    Keys.onShortcutOverride: function (event) {
        if ((event.key === Qt.Key_Space || event.key === Qt.Key_Home
             || event.key === Qt.Key_End)
                && !(event.modifiers & (Qt.ControlModifier | Qt.AltModifier
                                        | Qt.MetaModifier)))
            event.accepted = true;
    }

    Keys.onPressed: function (event) {
        if (event.key === Qt.Key_F2) {
            root.startRename(nxt.treeRenameRow());
            event.accepted = true;
        } else if (event.key === Qt.Key_Menu
                   || (event.key === Qt.Key_F10
                       && (event.modifiers & Qt.ShiftModifier))) {
            // Beside the row it is for, under its icon.
            var at = nxt.contextMenuRow();
            if (at >= 0) {
                treeList.positionViewAtIndex(at, ListView.Contain);
                var rowItem = treeList.itemAtIndex(at);
                if (rowItem) {
                    root.openContextMenu(rowItem, 0, 0);
                }
            }
            event.accepted = true;
        } else if (event.key === Qt.Key_Escape) {
            // Only taken when it closed something, so Escape still
            // reaches FreeCAD (clearing the selection) otherwise.
            event.accepted = nxt.closeDetail() || isolation.leave();
        } else if (event.key === Qt.Key_Space) {
            nxt.toggleSelectedVisibility();
            event.accepted = true;
        } else if (event.key === Qt.Key_Up || event.key === Qt.Key_Down) {
            var target = nxt.stepSelection(
                event.key === Qt.Key_Up ? -1 : 1,
                (event.modifiers & Qt.ShiftModifier) !== 0);
            if (target >= 0) {
                treeList.currentIndex = target;
                treeList.positionViewAtIndex(target, ListView.Contain);
            }
            event.accepted = true;
        } else if (event.key === Qt.Key_Home || event.key === Qt.Key_End) {
            var end = nxt.jumpSelection(
                event.key === Qt.Key_End,
                (event.modifiers & Qt.ShiftModifier) !== 0);
            if (end >= 0) {
                treeList.currentIndex = end;
                treeList.positionViewAtIndex(end, ListView.Contain);
            }
            event.accepted = true;
        } else if (event.key === Qt.Key_Left || event.key === Qt.Key_Right) {
            var row = nxt.stepBranch(event.key === Qt.Key_Right ? 1 : -1);
            if (row >= 0) {
                treeList.currentIndex = row;
                treeList.positionViewAtIndex(row, ListView.Contain);
            }
            event.accepted = true;
        }
    }

    // ====================================================== reveal plumbing

    Connections {
        target: nxt
        function onContextMenuRequested(x, y) {
            root.openContextMenu(null, x, y);
        }
        function onRenameRowRequested(row) {
            root.startRename(row);
        }
        function onRowHeld(row) {
            var item = treeList.itemAtIndex(row);
            treeList.heldRow = item ? row : -1;
            if (item)
                treeList.heldOffset = item.y - treeList.contentY;
        }
        function onRowReleased() {
            var row = treeList.heldRow;
            treeList.heldRow = -1;
            if (row < 0)
                return;
            var offset = treeList.heldOffset;
            // After the rows have taken their new heights.
            Qt.callLater(function () {
                var item = treeList.itemAtIndex(row);
                if (!item)
                    return;
                treeList.contentY = item.y - offset;
                treeList.returnToBounds();
            });
        }
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
