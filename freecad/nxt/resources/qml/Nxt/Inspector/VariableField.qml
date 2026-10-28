import QtQuick
import Nxt.Controls

// One VarSet variable in the Property Inspector: the name takes the room
// the fixed-width value leaves, with its tooltip on hover. Edit opens its
// name and tooltip in place below; `adding` makes it the form for a new
// variable, with a type to choose (fixed once made: FreeCAD can't change
// it).
Column {
    id: field

    property var spec: ({})             // an entry of the variables card
    //: Names and tooltips can change: one VarSet is selected.
    property bool editable: true
    property bool adding: false
    property bool expanded: false
    property string error: ""
    property string typeId: ""

    readonly property string tipText: {
        var tip = field.spec.tip || "";
        if (label.truncated)
            return tip ? field.spec.name + "\n" + tip : field.spec.name;
        return tip;
    }
    readonly property var types: field.adding ? inspector.variableTypes() : []
    readonly property real captionWidth:
        Math.max(nameCaption.implicitWidth, typeCaption.implicitWidth,
                 tipCaption.implicitWidth)
    readonly property real formFieldWidth: form.width - captionWidth - 6

    function open() {
        field.error = "";
        nameField.text = field.adding ? "" : (field.spec.name || "");
        tipField.text = field.adding ? "" : (field.spec.tip || "");
        if (field.adding && !field.typeId && field.types.length)
            field.typeId = field.types[0].id;
        field.expanded = true;
        nameField.input.forceActiveFocus();
        nameField.input.selectAll();
    }

    function close() {
        field.expanded = false;
        field.error = "";
    }

    // Closed before the bridge is called: a successful edit lays the
    // cards out again, and this field may not outlive the call.
    function save() {
        var name = nameField.text, tip = tipField.text;
        var adding = field.adding, prop = field.spec.name;
        field.close();
        var why = adding ? inspector.addVariable(field.typeId, name, tip)
                         : inspector.editVariable(prop, name, tip);
        if (why) {
            field.expanded = true;
            field.error = why;
        }
    }

    function labelOf(typeId) {
        for (var i = 0; i < field.types.length; ++i)
            if (field.types[i].id === typeId)
                return field.types[i].label;
        return "";
    }

    spacing: 2

    Item {
        visible: !field.adding
        width: field.width
        height: theme.fieldHeight

        HoverHandler { id: rowHover }

        Text {
            id: label
            anchors.left: parent.left
            anchors.right: value.left
            anchors.rightMargin: 6
            anchors.verticalCenter: parent.verticalCenter
            elide: Text.ElideRight
            text: field.spec.label || ""
            font.pixelSize: theme.fontSmall
            color: theme.textDim

            HoverHandler { id: labelHover }
            NxtToolTip {
                shown: labelHover.hovered
                text: field.tipText
            }
        }

        ValueEditor {
            id: value
            anchors.right: editButton.left
            anchors.rightMargin: 2
            anchors.verticalCenter: parent.verticalCenter
            width: theme.valueWidth
            spec: field.spec
            owner: inspector.owner
            labelled: false
            onEdited: function (v) {
                inspector.setValue(field.spec.name, v, field.spec.unit || "");
            }
        }

        // Its room is kept while hidden, so every value lines up.
        IconButton {
            id: editButton
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            visible: field.editable
            opacity: rowHover.hovered || field.expanded ? 1 : 0
            tip: field.expanded ? qsTr("Close") : qsTr("Edit variable")
            highlighted: field.expanded
            paint: function (ctx, w, h, ink) {
                ctx.strokeStyle = ink;
                ctx.lineWidth = Math.max(1.2, w / 9);
                ctx.lineCap = "round";
                ctx.lineJoin = "round";
                ctx.beginPath();
                ctx.moveTo(w * 0.18, h * 0.82);
                ctx.lineTo(w * 0.24, h * 0.6);
                ctx.lineTo(w * 0.68, h * 0.16);
                ctx.lineTo(w * 0.84, h * 0.32);
                ctx.lineTo(w * 0.4, h * 0.76);
                ctx.closePath();
                ctx.moveTo(w * 0.56, h * 0.28);
                ctx.lineTo(w * 0.72, h * 0.44);
                ctx.stroke();
            }
            onClicked: field.expanded ? field.close() : field.open()
        }
    }

    TextButton {
        visible: field.adding && !field.expanded
        text: qsTr("+ Add variable")
        primary: true
        onClicked: field.open()
    }

    Rectangle {
        visible: field.expanded
        width: field.width
        height: form.implicitHeight + 2 * pad
        radius: 4
        color: theme.chip
        readonly property real pad: 6

        Column {
            id: form
            x: parent.pad
            y: parent.pad
            width: parent.width - 2 * parent.pad
            spacing: 4

            Row {
                spacing: 6
                Text {
                    id: nameCaption
                    width: field.captionWidth
                    height: theme.fieldHeight
                    verticalAlignment: Text.AlignVCenter
                    text: qsTr("Name")
                    font.pixelSize: theme.fontSmall
                    color: theme.textDim
                }
                TextField {
                    id: nameField
                    width: field.formFieldWidth
                    placeholder: qsTr("FrameWidth")
                    onAccepted: field.save()
                    onDismissed: field.close()
                    onEdited: field.error = ""
                }
            }

            Row {
                spacing: 6
                Text {
                    id: typeCaption
                    width: field.captionWidth
                    height: theme.fieldHeight
                    verticalAlignment: Text.AlignVCenter
                    text: qsTr("Type")
                    font.pixelSize: theme.fontSmall
                    color: theme.textDim
                }
                Text {
                    visible: !field.adding
                    height: theme.fieldHeight
                    verticalAlignment: Text.AlignVCenter
                    text: field.spec.typeLabel || ""
                    font.pixelSize: theme.fontSmall
                    color: theme.text
                }
                ValueEditor {
                    visible: field.adding
                    width: field.formFieldWidth
                    labelled: false
                    spec: ({
                        name: "type", kind: "enum",
                        text: field.labelOf(field.typeId),
                        options: field.types.map(function (t) {
                            return t.label;
                        })
                    })
                    onEdited: function (v) {
                        for (var i = 0; i < field.types.length; ++i)
                            if (field.types[i].label === v)
                                field.typeId = field.types[i].id;
                    }
                }
            }

            Row {
                spacing: 6
                Text {
                    id: tipCaption
                    width: field.captionWidth
                    height: theme.fieldHeight
                    verticalAlignment: Text.AlignVCenter
                    text: qsTr("Tooltip")
                    font.pixelSize: theme.fontSmall
                    color: theme.textDim
                }
                TextField {
                    id: tipField
                    width: field.formFieldWidth
                    placeholder: qsTr("What it sets")
                    onAccepted: field.save()
                    onDismissed: field.close()
                }
            }

            Text {
                visible: field.error.length > 0
                width: form.width
                wrapMode: Text.Wrap
                text: field.error
                font.pixelSize: theme.fontSmall
                color: theme.danger
            }

            Row {
                anchors.right: parent.right
                spacing: 2
                TextButton {
                    text: qsTr("Cancel")
                    onClicked: field.close()
                }
                TextButton {
                    text: field.adding ? qsTr("Add") : qsTr("Save")
                    primary: true
                    onClicked: field.save()
                }
            }
        }
    }
}
