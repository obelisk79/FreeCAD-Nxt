import QtQuick
import Nxt.Controls

// One line of the Property Inspector: the name in the label column, then
// the editor (ValueEditor); then any trailing button and the items laid
// beside it on the same line.
Row {
    id: field

    property var spec: ({})
    //: The label column's width, the same down the card.
    property real labelWidth: 84

    readonly property var beside: field.spec.beside || []
    //: No label (bare): the editor takes the label column too.
    readonly property real labelRoom: (field.spec.label || "").length > 0
                                   ? field.labelWidth : -spacing
    readonly property bool hasTrail: !!field.spec.trail
    readonly property real tail: (field.hasTrail ? trailButton.width + spacing : 0)
                                 + besideRow.width
                                 + (field.beside.length > 0 ? spacing : 0)
    readonly property real room: field.width - field.labelRoom - spacing
    readonly property real besideJoined: Math.max(96, Math.min(room * 0.55, room - 78))
    readonly property real editorRoom: field.width - field.labelRoom
                                       - spacing - field.tail

    spacing: 6

    function send(spec, value) {
        inspector.setValue(spec.name, value, spec.unit || "");
    }

    Row {
        visible: field.labelRoom > 0
        width: Math.max(0, field.labelRoom)
        height: theme.fieldHeight
        spacing: 3

        Text {
            anchors.verticalCenter: parent.verticalCenter
            width: Math.min(implicitWidth, field.labelWidth - (marker.visible ? 10 : 0))
            text: field.spec.label || ""
            font.pixelSize: theme.fontSmall
            color: theme.textDim
            elide: Text.ElideRight
        }
        Text {
            id: marker
            anchors.verticalCenter: parent.verticalCenter
            visible: !!field.spec.expression && field.spec.expression.length > 0
            text: "ƒ"
            font.pixelSize: theme.fontAside
            font.italic: true
            font.bold: true
            color: theme.textDim
        }
    }

    ValueEditor {
        id: editor
        width: field.spec.narrow ? Math.min(field.editorRoom, (field.width - field.labelWidth) / 2)
                                 : field.editorRoom
        spec: field.spec
        owner: inspector.owner
        labelled: false
        editsLinks: true
        picking: inspector.picking === (field.spec.name || "")
                 || !!field.spec.picking
        onEdited: function (value) { field.send(field.spec, value); }
        onLeadEdited: function (value) { field.send(field.spec.lead, value); }
        onPartEdited: function (path, text) {
            inspector.setPart(field.spec.name, path, text);
        }
        onPartsEdited: function (parts) {
            inspector.setParts(field.spec.name, parts);
        }
        onColourRequested: inspector.pickColour(field.spec.name, field.spec.text)
        onNativeRequested: inspector.editNative(field.spec.name)
        onLinkRemoved: function (key) { inspector.removeLink(field.spec.name, key); }
        onLinkOpened: function (key) { inspector.openLink(field.spec.name, key); }
        onPickRequested: inspector.pickLinks(field.spec.name)
    }

    GlyphToggle {
        id: trailButton
        visible: field.hasTrail
        glyph: field.hasTrail ? field.spec.trail.glyph : ""
        tip: field.hasTrail ? field.spec.trail.label : ""
        checked: field.hasTrail && !!field.spec.trail.checked
        enabled: field.hasTrail && !field.spec.trail.readOnly
        onToggled: field.send(field.spec.trail, !field.spec.trail.checked)
    }

    Row {
        id: besideRow
        spacing: 6

        Repeater {
            model: field.beside

            Row {
                id: other
                required property var modelData
                spacing: 6
                readonly property bool joined: other.modelData.editor === "segmented"

                Text {
                    visible: (other.modelData.label || "").length > 0
                    height: theme.fieldHeight
                    verticalAlignment: Text.AlignVCenter
                    text: other.modelData.label || ""
                    font.pixelSize: theme.fontSmall
                    color: theme.textDim
                }
                ValueEditor {
                    // Joined buttons take about half, leaving the field
                    // room for a few digits and its unit.
                    width: other.joined ? field.besideJoined : implicitWidth
                    spec: other.modelData
                    owner: inspector.owner
                    labelled: false
                    onEdited: function (value) { field.send(other.modelData, value); }
                }
            }
        }
    }
}
