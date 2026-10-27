import QtQuick
import Nxt.Controls

// Tree header: document name, sketch problems, search, buttons.
Item {
    id: header

    property Item ghost
    property bool settingsOpen: false
    readonly property alias gear: gear
    // The room between the name's start and the buttons: all the search
    // field's with no name. It keeps at least half of it.
    readonly property real searchRoom: collapseButton.x - 4 - docLabel.x - 10
    readonly property real searchFloor: Math.max(80, searchRoom / 2)

    signal settingsClicked()
    signal menuRequested(real x, real y)

    TapHandler {
        acceptedButtons: Qt.RightButton
        enabled: nxt.hasDocument
        onTapped: function (point) {
            header.menuRequested(point.position.x, point.position.y);
        }
    }

    Rectangle {
        anchors.fill: parent
        anchors.margins: 2
        radius: 4
        visible: theme.overlay
        color: theme.pill
        border.width: 1
        border.color: theme.pillBorder
    }

    // Drop on the document name: move out of its container.
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
        ghost: header.ghost
    }

    Text {
        id: docLabel
        anchors.verticalCenter: parent.verticalCenter
        x: 9
        // The name takes what it needs; the elastic search field gives way first.
        width: Math.min(implicitWidth,
                        Math.max(52, header.searchRoom - header.searchFloor
                                 - (problems.visible ? problems.width + 8
                                                     : 0)))
        text: nxt.hasDocument ? nxt.documentLabel : qsTr("No document")
        elide: Text.ElideMiddle
        font.pixelSize: theme.fontRow
        font.bold: true
        color: !nxt.hasDocument ? theme.textDim
             : nxt.atRoot ? theme.accent : theme.text

        HoverHandler { id: docHover }
        TapHandler {
            enabled: nxt.hasDocument
            onDoubleTapped: nxt.activateRoot()
        }
        NxtToolTip {
            shown: docHover.hovered && nxt.hasDocument
            text: nxt.atRoot
                  ? qsTr("New objects go in at the top level")
                  : qsTr("Double-click: add new objects at the top level")
        }
    }

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

        TapHandler { onTapped: nxt.revealFirstProblem() }
    }

    SearchBox {
        id: search
        objectName: "treeSearch"
        anchors.verticalCenter: parent.verticalCenter
        anchors.left: problems.visible ? problems.right : docLabel.right
        anchors.leftMargin: 10
        anchors.right: collapseButton.left
        anchors.rightMargin: 4
        placeholder: qsTr("search")
        // The hits use the header's whole width, from its left edge.
        listWidth: header.width - 8
        listX: 4 - search.x
        results: nxt.searchResults
        onQueryChanged: function (value) { nxt.setSearch(value); }
        onChosen: function (name) { nxt.revealObject(name); }
    }

    IconButton {
        id: collapseButton
        objectName: "collapseButton"
        anchors.verticalCenter: parent.verticalCenter
        anchors.right: dockButton.visible ? dockButton.left : gear.left
        anchors.rightMargin: 2
        enabled: nxt.hasDocument
        tip: qsTr("Collapse all") + "\n" + qsTr("Shift-click: expand all")
        paint: function (ctx, w, h, ink) {
            ctx.strokeStyle = ink;
            ctx.lineWidth = Math.max(1.2, w / 9);
            ctx.lineCap = "round";
            ctx.lineJoin = "round";
            ctx.beginPath();
            ctx.moveTo(w * 0.2, h * 0.08);
            ctx.lineTo(w * 0.5, h * 0.34);
            ctx.lineTo(w * 0.8, h * 0.08);
            ctx.moveTo(w * 0.2, h * 0.92);
            ctx.lineTo(w * 0.5, h * 0.66);
            ctx.lineTo(w * 0.8, h * 0.92);
            ctx.moveTo(w * 0.1, h * 0.5);
            ctx.lineTo(w * 0.9, h * 0.5);
            ctx.stroke();
        }
        onClicked: function (mouse) {
            nxt.collapseTree((mouse.modifiers & Qt.ShiftModifier) !== 0);
        }
    }

    // The overlay hides the dock title bar, so the way back is here.
    IconButton {
        id: dockButton
        objectName: "dockButton"
        visible: host.viewOverlay
        anchors.verticalCenter: parent.verticalCenter
        anchors.right: gear.left
        anchors.rightMargin: 2
        tip: qsTr("Back to the dock")
        iconScale: 0.66
        iconAspect: 0.8
        paint: function (ctx, w, h, ink) {
            var line = Math.max(1, Math.round(w / 12));
            ctx.strokeStyle = ink;
            ctx.fillStyle = ink;
            ctx.lineWidth = line;
            ctx.strokeRect(line / 2, line / 2, w - line, h - line);
            ctx.fillRect(0, 0, Math.round(w * 0.36), h);
        }
        onClicked: host.leaveViewOverlay()
    }

    // In the header, not the title bar: FreeCAD's overlay mode replaces it.
    IconButton {
        id: gear
        objectName: "gear"
        anchors.verticalCenter: parent.verticalCenter
        anchors.right: parent.right
        anchors.rightMargin: 6
        tip: qsTr("Tree settings")
        highlighted: header.settingsOpen
        iconScale: 0.7
        paint: function (ctx, w, h, ink) {
            var c = w / 2, outer = w / 2, inner = outer * 0.72;
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
            ctx.moveTo(c + outer * 0.32, c);
            ctx.arc(c, c, outer * 0.32, 0, 2 * Math.PI, true);
            ctx.fill("evenodd");
        }
        onClicked: header.settingsClicked()
    }

    Rectangle {
        anchors.bottom: parent.bottom
        width: header.parent ? header.parent.width : width  // the divider spans the panel
        height: 1
        visible: !theme.overlay
        color: theme.border
    }
}
