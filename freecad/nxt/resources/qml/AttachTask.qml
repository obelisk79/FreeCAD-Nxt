import QtQuick
import Nxt.Controls

// Experimental: Nxt's attachment task panel. `attach` is
// tools/attach_task.py's bridge; FreeCAD draws OK and Cancel above it.
// A card per step: what the object is attached to (picks named for what
// they are, the next one listened for), the way and its variant, and the
// offset, shut until wanted.
Item {
    id: root

    readonly property int gap: 10
    readonly property int labelWidth: 78
    readonly property var picks: attach.references
    property bool offsetOpen: attach.offsetUsed

    implicitWidth: 320
    implicitHeight: column.implicitHeight + 2 * gap

    Rectangle { anchors.fill: parent; color: theme.background }

    Column {
        id: column
        x: root.gap
        y: root.gap
        width: root.width - 2 * root.gap
        spacing: root.gap

        Row {
            width: parent.width
            height: theme.fieldHeight
            spacing: 6

            Text {
                width: parent.width - (detach.visible ? detach.width + 6 : 0)
                anchors.verticalCenter: parent.verticalCenter
                text: attach.attached ? qsTr("Attached")
                    : root.picks.length > 0 ? qsTr("Not attached yet")
                    : qsTr("Not attached")
                font.pixelSize: theme.fontSmall
                color: theme.textDim
                elide: Text.ElideRight
            }
            TextButton {
                id: detach
                visible: root.picks.length > 0
                text: qsTr("Detach")
                onClicked: attach.detach()
            }
        }

        // -- what it is attached to --
        Card {
            Repeater {
                model: root.picks

                Row {
                    id: pickRow
                    required property var modelData
                    required property int index
                    width: parent.width
                    height: theme.fieldHeight
                    spacing: 6

                    Row {
                        width: root.labelWidth
                        height: parent.height
                        spacing: 6
                        Rectangle {
                            anchors.verticalCenter: parent.verticalCenter
                            width: Math.round(theme.fieldHeight * 0.66)
                            height: width
                            radius: width / 2
                            color: theme.accent
                            Text {
                                anchors.centerIn: parent
                                text: pickRow.index + 1
                                font.pixelSize: theme.fontAside
                                font.bold: true
                                color: theme.accentText
                            }
                        }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: pickRow.modelData.word
                            font.pixelSize: theme.fontSmall
                            color: theme.textDim
                        }
                    }
                    PickChip {
                        text: pickRow.modelData.text
                        shape: pickRow.modelData.shape
                        faulty: pickRow.modelData.faulty
                        maxWidth: parent.width - root.labelWidth - 6
                        onRemoved: attach.removeReference(pickRow.index)
                    }
                }
            }

            Row {
                visible: attach.picking
                width: parent.width
                height: theme.fieldHeight
                spacing: 6

                Rectangle {
                    width: parent.width - (done.visible ? done.width + 6 : 0)
                    height: parent.height
                    radius: height / 2
                    color: theme.hover
                    border.width: 2
                    border.color: theme.accent
                    Text {
                        x: 10
                        width: parent.width - 20
                        anchors.verticalCenter: parent.verticalCenter
                        text: attach.hint.length > 0 ? attach.hint
                            : qsTr("Pick a face, edge or point")
                        font.pixelSize: theme.fontSmall
                        font.italic: true
                        color: theme.text
                        elide: Text.ElideRight
                    }
                }
                TextButton {
                    id: done
                    visible: root.picks.length > 0
                    text: qsTr("Done")
                    onClicked: attach.stopPicking()
                }
            }

            TextButton {
                visible: !attach.picking && root.picks.length < 4
                text: qsTr("+ Pick")
                onClicked: attach.pick()
            }

            Text {
                visible: root.picks.length === 0
                width: parent.width
                wrapMode: Text.WordWrap
                text: qsTr("Pick in the 3D view or the tree. A whole object "
                           + "takes its position.")
                font.pixelSize: theme.fontAside
                color: theme.textDim
            }

            Notice {
                width: parent.width
                text: attach.problem.length === 0 ? ""
                    : attach.fix.length > 0 ? attach.problem + " " + attach.fix
                    : attach.problem
            }
        }

        // -- the way --
        Card {
            visible: attach.wayLabel.length > 0 || root.picks.length > 0

            Row {
                width: parent.width
                height: theme.fieldHeight
                spacing: 6

                Label { text: qsTr("Way") }
                DropBox {
                    id: wayBox
                    width: parent.width - root.labelWidth - flip.width - 12
                    height: parent.height
                    text: attach.wayLabel.length > 0 ? attach.wayLabel
                                                     : qsTr("Choose")
                    onOpened: {
                        var at = wayBox.mapToItem(root, 0, wayBox.height);
                        attach.openWays(at.x, at.y, wayBox.width);
                    }
                }
                GlyphToggle {
                    id: flip
                    glyph: "⇅"
                    tip: qsTr("Flip sides")
                    checked: attach.flipped
                    onToggled: attach.setFlipped(!attach.flipped)
                }
            }

            Row {
                visible: attach.variants.length > 0
                width: parent.width
                height: theme.fieldHeight
                spacing: 6

                Label { text: attach.choice }
                Segmented {
                    width: parent.width - root.labelWidth - 6
                    height: parent.height
                    options: attach.variants
                    value: attach.variant
                    onPicked: function (value) { attach.chooseVariant(value); }
                }
            }

            Row {
                visible: attach.alongPath
                width: parent.width
                height: theme.fieldHeight
                spacing: 6

                Label { text: qsTr("Along path") }
                NumberField {
                    width: (parent.width - root.labelWidth - 6) / 2
                    shown: attach.pathText
                    send: function (text) { return attach.setPath(text); }
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: qsTr("0 start, 1 end")
                    font.pixelSize: theme.fontAside
                    font.italic: true
                    color: theme.textDim
                }
            }
        }

        // -- the offset --
        Card {
            visible: attach.attached

            Row {
                width: parent.width
                height: theme.fieldHeight
                spacing: 6

                Disclosure {
                    anchors.verticalCenter: parent.verticalCenter
                    expanded: root.offsetOpen
                    onToggled: root.offsetOpen = !root.offsetOpen
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: qsTr("Offset")
                    font.pixelSize: theme.fontSmall
                    font.bold: true
                    color: theme.text
                    TapHandler { onTapped: root.offsetOpen = !root.offsetOpen }
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    visible: !attach.offsetUsed
                    text: qsTr("None")
                    font.pixelSize: theme.fontSmall
                    color: theme.textDim
                }
                TextButton {
                    visible: attach.offsetUsed && root.offsetOpen
                    text: qsTr("Reset")
                    onClicked: attach.resetOffset()
                }
            }

            OffsetRow {
                visible: root.offsetOpen
                label: qsTr("Move")
                first: 0
            }
            OffsetRow {
                visible: root.offsetOpen && attach.turns
                label: qsTr("Turn")
                first: 3
            }
            Text {
                visible: root.offsetOpen
                width: parent.width
                wrapMode: Text.WordWrap
                text: qsTr("Measured along the attached axes.")
                font.pixelSize: theme.fontAside
                color: theme.textDim
            }
        }
    }

    // A rounded group of controls.
    component Card: Rectangle {
        default property alias content: inner.children
        width: column.width
        height: visible ? inner.implicitHeight + 2 * root.gap : 0
        radius: 6
        color: theme.surface
        border.width: 1
        border.color: theme.border
        Column {
            id: inner
            x: root.gap
            y: root.gap
            width: parent.width - 2 * root.gap
            spacing: 8
        }
    }

    component Label: Text {
        width: root.labelWidth
        anchors.verticalCenter: parent.verticalCenter
        font.pixelSize: theme.fontSmall
        color: theme.textDim
        elide: Text.ElideRight
    }

    // A pick: its shape, what it names, and a button that removes it.
    component PickChip: Rectangle {
        id: chip
        property string text: ""
        property string shape: "object"
        property bool faulty: false
        property real maxWidth: 200
        signal removed()

        width: Math.min(maxWidth, chipRow.implicitWidth + 16)
        height: theme.fieldHeight
        radius: height / 2
        color: faulty ? Qt.rgba(theme.warning.r, theme.warning.g,
                                theme.warning.b, 0.14)
                      : theme.chip
        border.width: 1
        border.color: faulty ? theme.warning : theme.border

        Row {
            id: chipRow
            x: 8
            anchors.verticalCenter: parent.verticalCenter
            spacing: 6

            ShapeMark {
                anchors.verticalCenter: parent.verticalCenter
                shape: chip.faulty ? "warning" : chip.shape
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                width: Math.min(implicitWidth,
                                chip.maxWidth - 16 - 2 * 6 - 14 - 16)
                text: chip.text
                font.pixelSize: theme.fontSmall
                color: theme.text
                elide: Text.ElideMiddle
            }
            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                width: 16
                height: 16
                radius: 8
                color: removeTap.pressed ? theme.pressed
                     : removeHover.hovered ? theme.border : "transparent"
                Accessible.role: Accessible.Button
                Accessible.name: qsTr("Remove")
                Text {
                    anchors.centerIn: parent
                    text: "×"
                    font.pixelSize: theme.fontRow
                    color: removeHover.hovered ? theme.text : theme.textDim
                }
                HoverHandler { id: removeHover }
                TapHandler {
                    id: removeTap
                    onTapped: chip.removed()
                }
            }
        }
    }

    // What a pick is, drawn small: a dot, a stroke, a curve, a square;
    // a triangle when it is the pick at fault.
    component ShapeMark: Canvas {
        id: mark
        property string shape: "object"
        width: 12
        height: 12
        onShapeChanged: requestPaint()
        onPaint: {
            var g = getContext("2d");
            g.reset();
            var ink = mark.shape === "warning" ? theme.warning : theme.textDim;
            g.fillStyle = ink;
            g.strokeStyle = ink;
            g.lineWidth = 2;
            g.beginPath();
            if (mark.shape === "point") {
                g.arc(6, 6, 3, 0, 2 * Math.PI);
                g.fill();
            } else if (mark.shape === "edge") {
                g.moveTo(1, 11); g.lineTo(11, 1); g.stroke();
            } else if (mark.shape === "curve") {
                g.moveTo(1, 10); g.bezierCurveTo(4, 0, 8, 12, 11, 2); g.stroke();
            } else if (mark.shape === "warning") {
                g.moveTo(6, 1); g.lineTo(11.5, 11); g.lineTo(0.5, 11);
                g.closePath(); g.fill();
            } else if (mark.shape === "face") {
                g.fillRect(1, 2, 10, 8);
            } else {
                g.strokeRect(1.5, 1.5, 9, 9);
            }
        }
    }

    // Three offset fields after a label: X, Y and Z of the move or turn.
    component OffsetRow: Row {
        id: offsetRow
        property string label: ""
        property int first: 0
        readonly property real each: (width - root.labelWidth - 6 - 2 * 6) / 3

        width: column.width - 2 * root.gap
        height: theme.fieldHeight
        spacing: 6

        Label { text: offsetRow.label }
        Repeater {
            model: ["X", "Y", "Z"]
            Row {
                id: axisCell
                required property string modelData
                required property int index
                width: offsetRow.each
                height: parent.height
                spacing: 4
                Text {
                    id: axisName
                    anchors.verticalCenter: parent.verticalCenter
                    text: axisCell.modelData
                    font.pixelSize: theme.fontSmall
                    font.bold: true
                    color: theme.textDim
                }
                NumberField {
                    width: axisCell.width - axisName.width - 4
                    shown: attach.offset[offsetRow.first + axisCell.index] || ""
                    send: function (text) {
                        return attach.setOffset(offsetRow.first + axisCell.index,
                                                text);
                    }
                }
            }
        }
    }

    // A field that shows the stored value until typed in, then applies
    // on Return or on leaving it; Escape puts the value back.
    component NumberField: TextField {
        id: field
        property string shown: ""
        property var send: null
        property bool typed: false

        height: theme.fieldHeight
        Component.onCompleted: text = shown
        onShownChanged: if (!typed) text = shown

        function apply() {
            if (typed && !(send && send(text)))
                text = shown;
            typed = false;
        }

        onEdited: if (input.activeFocus) typed = text !== shown
        onAccepted: apply()
        onDismissed: {
            text = shown;
            typed = false;
        }
        Connections {
            target: field.input
            function onActiveFocusChanged() {
                if (!field.input.activeFocus)
                    field.apply();
            }
        }
    }
}
