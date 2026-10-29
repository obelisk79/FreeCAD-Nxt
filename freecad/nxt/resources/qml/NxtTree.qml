import QtQuick
import Nxt.Controls
import Nxt.Tree

// Root of the Nxt model panel: one list in creation order, sketches as
// siblings of the features that use them.
//
// No QtQuick.Controls: the host QQuickWidget's style would reach them.
Rectangle {
    id: root
    color: theme.canvas
    implicitWidth: 280
    implicitHeight: 520

    readonly property int headerHeight: Math.round(theme.rowHeight * 1.25)

    // Header/detail-strip width cap; Screen.width is 0 until shown.
    readonly property real contentCap: Screen.width > 0
        ? Math.max(theme.headerMinWidth,
                   Screen.width * theme.headerMaxPercent / 100)
        : width

    // Overlay hit test (view_overlay.py): is (x, y) the panel's or the 3D view's?
    function wantsPoint(x, y) {
        if (header.contains(header.mapFromItem(root, x, y)))
            return true;
        if (breadcrumb.visible
                && breadcrumb.contains(breadcrumb.mapFromItem(root, x, y)))
            return true;
        if (scrollBar.visible
                && scrollBar.contains(scrollBar.mapFromItem(root, x, y)))
            return true;
        var bar = tipContent.childAt(x - tipLayer.x,
                                     y - treePane.y - tipContent.y);
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

    // Overlay wheel (view_overlay.py). `angle` in eighths of a degree.
    property real wheelBoost: 1
    property double lastWheel: 0

    function scrollWheel(angle, pixel, paging) {
        if (breadcrumb.visible && breadcrumb.hovered && breadcrumb.overflows) {
            breadcrumb.scrollBy(pixel !== 0 ? pixel : angle / 120 * 40);
            return;
        }
        var now = Date.now();
        wheelBoost = now - lastWheel < 150 ? Math.min(5, wheelBoost + 0.5)
                                           : 1;
        lastWheel = now;
        var step;
        if (paging)
            step = Math.sign(angle || pixel) * treeList.height * 0.9;
        else if (pixel !== 0)
            step = pixel;
        else
            step = angle / 120 * theme.rowHeight * 3 * wheelBoost;
        var top = treeList.originY;
        var bottom = Math.max(top, top + treeList.contentHeight
                                   - treeList.height);
        treeList.contentY = Math.max(top, Math.min(bottom,
                                                   treeList.contentY - step));
    }

    // -- header --

    TreeHeader {
        id: header
        objectName: "header"
        width: Math.min(parent.width, root.contentCap)
        height: root.headerHeight
        // Above the list, so search results can hang over it.
        z: 100
        ghost: ghost
        settingsOpen: root.settingsOpen
        onSettingsClicked: root.toggleSettings()
        onMenuRequested: function (x, y) {
            var at = header.mapToItem(root, x, y);
            root.openContextMenu(null, at.x, at.y, nxt.headerMenu());
        }
    }

    // -- tree --

    Item {
        id: treePane
        anchors.top: header.bottom
        anchors.bottom: parent.bottom
        width: parent.width

        readonly property real overlayBarSpace:
            host.viewOverlay ? theme.scrollBarWidth : 0

        // Docked only: empty space below the rows is the document's top level.
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
            anchors.leftMargin: treePane.overlayBarSpace
            anchors.topMargin: 3
            clip: true
            model: nxt.treeModel
            boundsBehavior: Flickable.StopAtBounds
            flickableDirection: Flickable.VerticalFlick
            cacheBuffer: 400
            // Rows are recycled while scrolling, not rebuilt.
            reuseItems: true
            focus: true
            keyNavigationEnabled: false
            // In the overlay, empty-space presses belong to the model behind.
            interactive: !host.viewOverlay

            WheelHandler {
                target: null
                enabled: !host.viewOverlay
                acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                onWheel: function (event) {
                    root.scrollWheel(event.angleDelta.y, event.pixelDelta.y,
                                     event.modifiers & Qt.ShiftModifier);
                    event.accepted = true;
                }
            }

            property int barGap: -1
            property int dropGap: -1
            readonly property int gapAfterRow: barGap >= 0 ? barGap : dropGap
            property var dragSources: []
            // See the bridge's rowHeld.
            property int heldRow: -1
            property real heldOffset: 0
            property bool reorderDrag: false
            property int intoRow: -1

            delegate: TreeRow { dragGhost: ghost; detailCap: root.contentCap }

            footer: Item {
                width: treeList.width
                height: theme.rowHeight
            }

            // A translucent QQuickWidget does not repaint what is behind it when
            // content moves; nudge it (coalesced host-side).
            onContentYChanged: if (theme.overlay) host.repaintBehind()
            onContentHeightChanged: if (theme.overlay) host.repaintBehind()
            onCountChanged: if (theme.overlay) host.repaintBehind()
            onHeightChanged: if (theme.overlay) host.repaintBehind()
        }

        Breadcrumb {
            id: breadcrumb
            objectName: "breadcrumb"
            z: 50
            width: theme.overlay ? header.width : parent.width

            property int under: -1
            property var containers: []

            function refresh(changed) {
                var at = treeList.indexAt(0, treeList.contentY + height);
                if (at === under && !changed)
                    return;
                under = at;
                containers = (at >= 0 && nxt.breadcrumb(at)) || [];
            }

            // itemAtIndex is null for rows too far off to exist.
            crumbs: containers.filter(function (crumb) {
                var item = treeList.itemAtIndex(crumb.row);
                return item === null || item.y < treeList.contentY;
            })
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

        // Timeline bars: an overlay, not list rows.
        Item {
            id: tipLayer
            anchors.fill: parent
            anchors.leftMargin: treePane.overlayBarSpace
            clip: true
            z: 5

            // Bars ride with the rows in content coordinates; scrolling moves one item.
            Item {
                id: tipContent
                y: -treeList.contentY
                width: parent.width
                height: treeList.contentHeight

                // Bumps every few rows so bars re-read itemAtIndex (not reactive).
                readonly property int realised:
                    Math.floor(treeList.contentY / (theme.rowHeight * 5))

            Repeater {
                model: nxt.tipBars

                TimelineBar {
                    required property var modelData

                    x: theme.rowPad + modelData.depth * theme.indent
                    body: modelData.body
                    pos: modelData.pos
                    minPos: modelData.minPos
                    maxPos: modelData.maxPos
                    rowHeight: theme.rowHeight
                    list: treeList
                    fullWidth: treeList.width
                    realised: tipContent.realised
                    listTopMargin: treeList.anchors.topMargin
                    visible: y + height >= treeList.contentY
                             && y <= treeList.contentY + treeList.height

                    onDragPosChanged: if (dragging) treeList.barGap = dragPos
                    onDraggingChanged: treeList.barGap = dragging ? dragPos : -1
                }
            }
            }
        }

        DependencyArrows {
            anchors.fill: treeList
            list: treeList
            z: 4
        }

        NxtScrollBar {
            id: scrollBar
            target: treeList
            z: 6
            anchors.top: treeList.top
            anchors.bottom: parent.bottom
            x: host.viewOverlay ? 0 : parent.width - width
        }

        Text {
            anchors.centerIn: parent
            visible: treeList.count === 0
            text: nxt.hasDocument ? qsTr("This document is empty")
                                  : qsTr("Open or create a document")
            color: theme.textDim
            font.pixelSize: theme.fontRow
        }
    }

    // -- drag ghost --

    DragGhost {
        id: ghost
        list: treeList
    }

    // -- context menu --

    Component {
        id: contextMenuComponent
        ContextMenu {}
    }

    // Wayland places a popup against its parent item's whole rect, so popups
    // open from this 1px item. See host.menuAnchorOffset().
    Item {
        id: menuAnchor
        width: 1
        height: 1
    }

    property bool settingsOpen: false
    property var settingsPopup: null
    // A gear press closes the popup before its click arrives; ignore that click.
    property double settingsClosedAt: 0

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
        var gear = header.gear;
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

    function openContextMenu(rowItem, x, y, data) {
        data = data || nxt.contextMenu();
        if (!data || !data.bar)
            return;
        var menu = contextMenuComponent.createObject(root);
        menu.load(data);
        // After the menu closes, so a dialog does not open beneath it.
        menu.chosen.connect(function (command) {
            nxt.runMenuItem(command);
        });
        menu.closed.connect(function () { treeList.forceActiveFocus(); });
        var at = rowItem
            ? rowItem.mapToItem(root, theme.rowPad + theme.indent,
                                rowItem.height)
            : Qt.point(x, y);
        // Kept inside FreeCAD's window: under Wayland Qt cannot tell
        // where the window is on screen, so it cannot move a menu that
        // runs off the bottom. Below the row if it fits, else above it,
        // else as low as it fits.
        var room = host.menuRoom();
        var tall = menu.implicitHeight;
        if (room.height > 0 && room.y + at.y + tall > room.height) {
            var top = rowItem ? at.y - rowItem.height : at.y;
            at.y = room.y + top - tall >= 0
                ? top - tall
                : Math.max(0, room.height - tall) - room.y;
        }
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

    // -- keyboard --

    // Space/Home/End/Delete are FreeCAD shortcuts, offered the key before
    // the panel; claim them in shortcutOverride (a focused TextInput still
    // gets them first).
    Keys.onShortcutOverride: function (event) {
        if (event.key === Qt.Key_Escape && ghost.Drag.active) {
            event.accepted = true;
            return;
        }
        if ((event.key === Qt.Key_Space || event.key === Qt.Key_Home
             || event.key === Qt.Key_End || event.key === Qt.Key_Delete
             || event.key === Qt.Key_Backspace)
                && !(event.modifiers & (Qt.ControlModifier | Qt.AltModifier
                                        | Qt.MetaModifier)))
            event.accepted = true;
    }

    Keys.onPressed: function (event) {
        if (event.key === Qt.Key_Escape && ghost.Drag.active) {
            ghost.cancel();
            event.accepted = true;
            return;
        }
        if (event.key === Qt.Key_F2) {
            root.startRename(nxt.treeRenameRow());
            event.accepted = true;
        } else if (event.key === Qt.Key_Menu
                   || (event.key === Qt.Key_F10
                       && (event.modifiers & Qt.ShiftModifier))) {
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
            // Unaccepted otherwise, so FreeCAD can clear the selection.
            event.accepted = nxt.closeDetail() || isolation.leave();
        } else if (event.key === Qt.Key_Delete
                   || event.key === Qt.Key_Backspace) {
            nxt.deleteSelected();
            event.accepted = true;
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

    // -- bridge signals --

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
