import QtQuick
import Nxt.Controls
import Nxt.Tree

// Experimental: the sketch's solver status at the top centre of the 3D
// view (tools/sketch_panel.py), in place of the task panel's message.
// The link selects what the status is about; the gear opens the grid,
// snap and render order settings below the pill. Sized to its content.
Item {
    id: root

    property bool open: false
    readonly property var status: sketch.status
    readonly property var values: sketch.switches
    readonly property int gap: 6
    readonly property int pad: 10

    implicitWidth: Math.max(pill.width, root.open ? panel.width : 0)
    implicitHeight: pill.height + (root.open ? panel.height + gap : 0)

    // Every press on the pill or its settings stays here, gaps included.
    MouseArea {
        anchors.fill: parent
        z: -1
        acceptedButtons: Qt.AllButtons
        onWheel: function (wheel) { wheel.accepted = true; }
    }

    function orderName(id) {
        return id === 1 ? qsTr("Normal")
             : id === 2 ? qsTr("Construction")
             : id === 3 ? qsTr("External") : "";
    }
    function paintUp(ctx, w, h, ink) {
        ctx.strokeStyle = ink;
        ctx.lineWidth = Math.max(1.2, w * 0.12);
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        ctx.beginPath();
        ctx.moveTo(w * 0.5, h * 0.85);
        ctx.lineTo(w * 0.5, h * 0.15);
        ctx.moveTo(w * 0.22, h * 0.43);
        ctx.lineTo(w * 0.5, h * 0.15);
        ctx.lineTo(w * 0.78, h * 0.43);
        ctx.stroke();
    }

    // A switch for one setting; absent where this FreeCAD lacks it.
    component Toggle: NxtSwitch {
        required property string key
        width: parent.width
        visible: root.values[key] !== undefined
        stored: root.values[key] === true
        onChangedTo: function (on) { sketch.turn(key, on); }
    }

    // A labelled value: kept on Return or on leaving, dropped on Escape.
    component Value: Item {
        id: value

        property alias label: caption.text
        property string stored: ""
        signal changedTo(string text)

        width: parent.width
        height: theme.fieldHeight

        Text {
            id: caption
            anchors.verticalCenter: parent.verticalCenter
            font.pixelSize: theme.fontSmall
            color: theme.text
        }
        TextField {
            id: field

            property bool typed: false

            function revert() {
                text = value.stored;
                typed = false;
            }
            function apply() {
                if (typed && text !== value.stored)
                    value.changedTo(text);
                typed = false;
            }

            anchors.right: parent.right
            width: Math.round(parent.width * 0.42)
            height: parent.height
            Component.onCompleted: revert()
            onEdited: if (input.activeFocus) typed = true
            onAccepted: apply()
            onDismissed: {
                revert();
                input.focus = false;
            }
            input.onActiveFocusChanged: {
                if (!input.activeFocus)
                    apply();
            }
        }
        onStoredChanged: if (!field.typed) field.revert()
    }

    Rectangle {
        id: panel

        visible: root.open
        anchors.top: pill.bottom
        anchors.topMargin: root.gap
        anchors.horizontalCenter: parent.horizontalCenter
        width: Math.round(theme.rowHeight * 10)
        height: body.implicitHeight + 2 * root.pad
        radius: 6
        color: theme.surface
        border.width: 1
        border.color: theme.border

        Column {
            id: body
            x: root.pad
            y: root.pad
            width: parent.width - 2 * root.pad
            spacing: root.gap

            Toggle { key: "grid"; text: qsTr("Grid") }
            Toggle { key: "gridAuto"; text: qsTr("Grid auto-spacing") }
            Value {
                visible: root.values.spacing !== undefined
                label: qsTr("Spacing")
                stored: root.values.spacing || ""
                onChangedTo: function (text) { sketch.setSpacing(text); }
            }
            Rectangle { width: parent.width; height: 1; color: theme.border }
            Toggle { key: "snap"; text: qsTr("Snap") }
            Toggle { key: "snapToGrid"; text: qsTr("Snap to grid") }
            Toggle { key: "snapToObjects"; text: qsTr("Snap to objects") }
            Value {
                label: qsTr("Snap angle")
                stored: root.values.snapAngle || ""
                onChangedTo: function (text) { sketch.setSnapAngle(text); }
            }
            Rectangle { width: parent.width; height: 1; color: theme.border }
            Toggle { key: "autoConstraints"; text: qsTr("Auto constraints") }
            Rectangle { width: parent.width; height: 1; color: theme.border }
            Text {
                text: qsTr("Render order, top first")
                font.pixelSize: theme.fontAside
                font.capitalization: Font.AllUppercase
                color: theme.textDim
            }
            Repeater {
                model: 3

                Item {
                    id: place

                    required property int index
                    readonly property var order: root.values.order || []

                    width: body.width
                    height: theme.rowHeight

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: root.orderName(place.order[place.index])
                        font.pixelSize: theme.fontSmall
                        color: theme.text
                    }
                    IconButton {
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        visible: place.index > 0
                        paint: root.paintUp
                        tip: qsTr("Draw above")
                        onClicked: sketch.drawAbove(place.index)
                    }
                }
            }
        }
    }

    Rectangle {
        id: pill

        anchors.top: parent.top
        anchors.horizontalCenter: parent.horizontalCenter
        width: row.implicitWidth + 2 * root.pad
        height: Math.round(theme.rowHeight * 1.3)
        radius: height / 2
        color: theme.surface
        border.width: 1
        border.color: root.status.mark >= 3 ? theme.danger
                    : root.status.mark === 2 ? theme.warning : theme.border

        Row {
            id: row
            anchors.centerIn: parent
            spacing: root.gap

            SeverityMark {
                anchors.verticalCenter: parent.verticalCenter
                level: root.status.mark || 0
                size: theme.markSizeSmall
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                visible: text.length > 0
                text: root.status.text || ""
                font.pixelSize: theme.fontSmall
                color: theme.text
            }
            // Built as IconButton is, which works over the 3D view: a
            // MouseArea (a TapHandler leaves the press to the view, which
            // starts a box selection), and the action a frame after the
            // release.
            Item {
                id: link
                anchors.verticalCenter: parent.verticalCenter
                visible: linkText.text.length > 0
                width: linkText.implicitWidth
                height: Math.max(linkText.implicitHeight, theme.rowHeight)
                Accessible.role: Accessible.Link
                Accessible.name: linkText.text

                Text {
                    id: linkText
                    anchors.verticalCenter: parent.verticalCenter
                    text: root.status.link || ""
                    font.pixelSize: theme.fontSmall
                    font.underline: true
                    color: theme.link
                }
                // Ctrl: list what is free in Contents, without selecting.
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: function (mouse) {
                        follow.listing = root.status.action === "dof"
                            && (mouse.modifiers & Qt.ControlModifier) !== 0;
                        follow.restart();
                    }
                }
                Timer {
                    id: follow
                    property bool listing: false
                    interval: 30
                    onTriggered: {
                        if (listing)
                            sketch.contents.showFree();
                        else
                            sketch.select(root.status.action);
                    }
                }
            }
            IconButton {
                anchors.verticalCenter: parent.verticalCenter
                paint: Glyphs.gear
                iconScale: 0.7
                highlighted: root.open
                tip: root.open ? "" : qsTr("Sketch settings")
                name: qsTr("Sketch settings")
                onClicked: root.open = !root.open
            }
        }
    }
}
