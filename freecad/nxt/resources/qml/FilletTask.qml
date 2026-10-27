import QtQuick
import Nxt.Controls

// The Nxt fillet's and chamfer's task panel. `task` is tools/fillet_task.py's bridge;
// FreeCAD draws OK and Cancel above it.
Item {
    id: root

    readonly property int gap: 10
    readonly property color amber: theme.warning
    readonly property color amberWash: Qt.rgba(amber.r, amber.g, amber.b, 0.14)

    implicitWidth: 320
    implicitHeight: column.implicitHeight + 2 * gap

    Rectangle { anchors.fill: parent; color: theme.background }

    Column {
        id: column
        x: root.gap
        y: root.gap
        width: root.width - 2 * root.gap
        spacing: root.gap

        // -- radius --
        Card {
            Row {
                width: parent.width
                Text {
                    width: parent.width / 2
                    text: task.flat ? qsTr("Distance") : qsTr("Radius")
                    color: theme.textDim
                    font.pixelSize: theme.fontSmall
                }
                Text {
                    width: parent.width / 2
                    horizontalAlignment: Text.AlignRight
                    text: task.fits >= 0 ? qsTr("fits up to %1").arg(task.fitsText) : ""
                    color: root.amber
                    font.pixelSize: theme.fontSmall
                }
            }
            TextField {
                id: radiusField
                width: parent.width
                height: theme.fieldHeight
                suffix: task.radiusUnit
                Component.onCompleted: text = task.radiusNumber

                // Typed and not yet applied: kept over outside changes.
                property bool typed: false

                function revert() {
                    text = task.radiusNumber
                    typed = false
                }
                function apply() {
                    if (typed && !task.setRadiusText(text))
                        revert()
                    typed = false
                }

                onEdited: if (input.activeFocus) typed = text !== task.radiusNumber

                onAccepted: { apply(); input.selectAll() }
                onDismissed: { revert(); input.focus = false }
                onUpPressed: { apply(); task.step(1, false) }
                onDownPressed: { apply(); task.step(-1, false) }
                input.onActiveFocusChanged: {
                    if (input.activeFocus)
                        Qt.callLater(input.selectAll)
                    else
                        apply()
                }

                Connections {
                    target: task
                    function onChanged() {
                        if (radiusField.typed)
                            return
                        radiusField.revert()
                        if (radiusField.input.activeFocus)
                            radiusField.input.selectAll()
                    }
                }
                WheelHandler {
                    acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                    onWheel: function (event) {
                        var steps = event.angleDelta.y > 0 ? 1 : event.angleDelta.y < 0 ? -1 : 0
                        if (steps === 0)
                            return
                        radiusField.apply()
                        // As a drag handle steps: fine, coarse with its key.
                        task.stepBy(steps, event.modifiers)
                        radiusField.input.forceActiveFocus()
                        Qt.callLater(radiusField.input.selectAll)
                    }
                }
                Rectangle {
                    anchors.fill: parent
                    radius: 3
                    color: "transparent"
                    border.width: 1
                    border.color: root.amber
                    visible: task.failing > 0
                }
            }
        }

        // -- edges --
        Card {
            Row {
                width: parent.width
                spacing: 8
                Text {
                    width: parent.width - sourceLabel.width - clearButton.width - 16
                    text: task.useAllEdges ? qsTr("All edges · %1").arg(task.edges.length)
                                           : qsTr("Edges · %1").arg(task.edges.length)
                    color: theme.text
                    font.pixelSize: theme.fontRow
                    font.bold: true
                    anchors.verticalCenter: parent.verticalCenter
                }
                Text {
                    id: sourceLabel
                    text: task.source
                    color: theme.textDim
                    font.pixelSize: theme.fontSmall
                    anchors.verticalCenter: parent.verticalCenter
                }
                PanelButton {
                    id: clearButton
                    text: qsTr("Clear")
                    enabled: task.edges.length > 0 && !task.useAllEdges
                    onClicked: task.clear()
                }
            }

            Flow {
                width: parent.width
                spacing: 6
                visible: !task.useAllEdges
                Repeater {
                    model: task.edges
                    delegate: Rectangle {
                        required property var modelData
                        height: theme.chipHeight + 4
                        width: chipLabel.implicitWidth + remove.width + 16
                        radius: height / 2
                        color: modelData.short ? root.amberWash : theme.chip
                        border.width: 1
                        border.color: modelData.short ? root.amber : theme.border

                        HoverHandler {
                            onHoveredChanged: task.hover(hovered ? modelData.name : "")
                        }
                        Text {
                            id: chipLabel
                            x: 10
                            anchors.verticalCenter: parent.verticalCenter
                            text: modelData.short ? modelData.name + " · " + modelData.limit
                                                  : modelData.name
                            color: modelData.short ? root.amber : theme.text
                            font.pixelSize: theme.fontSmall
                        }
                        Text {
                            id: remove
                            anchors.right: parent.right
                            anchors.rightMargin: 6
                            anchors.verticalCenter: parent.verticalCenter
                            width: 14
                            text: "×"
                            color: theme.textDim
                            font.pixelSize: theme.fontRow
                            horizontalAlignment: Text.AlignHCenter
                            MouseArea {
                                anchors.fill: parent
                                anchors.margins: -4
                                onClicked: task.remove(modelData.name)
                            }
                        }
                    }
                }
            }

            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: task.useAllEdges
                      ? qsTr("Every edge of %1 is rounded.").arg(task.source)
                      : task.edges.length === 0
                        ? qsTr("Pick edges in the 3D view; a face adds all its edges.")
                        : qsTr("Pick again to remove. Hover a chip to find its edge.")
                color: theme.textDim
                font.pixelSize: theme.fontSmall
            }
        }

        // -- edges that do not fit --
        Notice {
            width: parent.width
            text: task.failing <= 0 ? ""
                  : (task.flat ? qsTr("%1 of %2 edges won't chamfer at %3.")
                               : qsTr("%1 of %2 edges won't fillet at %3."))
                    .arg(task.failing).arg(task.edges.length).arg(task.radiusText)
            action: task.fits > 0 ? qsTr("Use %1 for all").arg(task.fitsText) : ""
            onActed: task.useFits()
        }

        // -- options --
        Card {
            Item {
                width: parent.width
                height: optionsTitle.implicitHeight
                Disclosure {
                    id: dart
                    anchors.verticalCenter: parent.verticalCenter
                    expanded: options.visible
                }
                Text {
                    id: optionsTitle
                    x: dart.width + 6
                    text: qsTr("Options")
                    color: theme.text
                    font.pixelSize: theme.fontRow
                    font.bold: true
                }
                MouseArea {
                    anchors.fill: parent
                    onClicked: options.visible = !options.visible
                }
            }
            Column {
                id: options
                width: parent.width
                spacing: 6
                visible: false
                NxtSwitch {
                    width: parent.width
                    text: qsTr("Use all edges")
                    stored: task.useAllEdges
                    onChangedTo: function (on) { task.setUseAllEdges(on) }
                }
                NxtSwitch {
                    width: parent.width
                    text: qsTr("Include tangent edges")
                    stored: task.tangentEdges
                    onChangedTo: function (on) { task.setTangentEdges(on) }
                }
                NxtSwitch {
                    width: parent.width
                    visible: task.flat
                    text: qsTr("Triangular corners")
                    stored: task.triangleCorners
                    onChangedTo: function (on) { task.setTriangleCorners(on) }
                }
                NxtSwitch {
                    width: parent.width
                    text: qsTr("Show what changes")
                    stored: task.preview
                    onChangedTo: function (on) { task.setPreview(on) }
                }
                NxtSwitch {
                    width: parent.width
                    text: qsTr("Refine result")
                    stored: task.refine
                    onChangedTo: function (on) { task.setRefine(on) }
                }
            }
        }
    }

    // A rounded group of controls.
    component Card: Rectangle {
        default property alias content: inner.children
        width: column.width
        height: inner.implicitHeight + 24
        radius: 6
        color: theme.surface
        border.width: 1
        border.color: theme.border
        Column {
            id: inner
            x: 12; y: 12
            width: parent.width - 24
            spacing: 10
        }
    }

    // A small outlined text button.
    component PanelButton: Rectangle {
        property alias text: label.text
        property color ink: theme.text
        signal clicked()
        height: theme.fieldHeight
        width: label.implicitWidth + 20
        radius: 4
        color: area.pressed && enabled ? theme.pressed
             : area.containsMouse && enabled ? theme.hover : "transparent"
        border.width: 1
        border.color: ink
        opacity: enabled ? 1.0 : 0.4
        Text {
            id: label
            anchors.centerIn: parent
            color: parent.ink
            font.pixelSize: theme.fontSmall
        }
        MouseArea {
            id: area
            anchors.fill: parent
            hoverEnabled: true
            enabled: parent.enabled
            onClicked: parent.clicked()
        }
    }
}
