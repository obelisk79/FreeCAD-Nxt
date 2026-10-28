import QtQuick
import Nxt.Controls

// One VarSet variable: the name takes the room the fixed-width value
// leaves. Edit opens its name and tooltip in place below; `adding` makes
// it the form for a new variable instead, with a type to choose.
Column {
    id: row

    property var spec: ({})             // one entry from properties.describe
    property string owner: ""           // the object, for expressions
    property string objectKey: ""       // the VarSet, for edits
    property bool adding: false
    property bool expanded: false
    property string error: ""
    property string typeId: ""

    signal edited(var value)

    readonly property bool truncated: label.truncated
    readonly property string tipText: {
        var tip = row.spec.tip || "";
        if (row.truncated)
            return tip ? row.spec.name + "\n" + tip : row.spec.name;
        return tip;
    }
    readonly property var types: row.adding ? nxt.variableTypes() : []
    readonly property real formLabelWidth:
        Math.max(nameCaption.implicitWidth, tipCaption.implicitWidth,
                 typeCaption.implicitWidth)

    function open() {
        row.error = "";
        nameField.text = row.adding ? "" : (row.spec.name || "");
        tipField.text = row.adding ? "" : (row.spec.tip || "");
        if (row.adding && !row.typeId && row.types.length)
            row.typeId = row.types[0].id;
        row.expanded = true;
        nameField.input.forceActiveFocus();
        nameField.input.selectAll();
    }

    function close() {
        row.expanded = false;
        row.error = "";
    }

    function save() {
        var why = row.adding
            ? nxt.addVariable(row.objectKey, row.typeId, nameField.text,
                              tipField.text)
            : nxt.editVariable(row.objectKey, row.spec.name, nameField.text,
                               tipField.text);
        if (why)
            row.error = why;
        else
            row.close();
    }

    function labelOf(typeId) {
        for (var i = 0; i < row.types.length; ++i)
            if (row.types[i].id === typeId)
                return row.types[i].label;
        return "";
    }

    spacing: 2

    Item {
        visible: !row.adding
        width: row.width
        height: theme.fieldHeight

        HoverHandler { id: rowHover }

        Text {
            id: label
            anchors.left: parent.left
            anchors.right: value.left
            anchors.rightMargin: 6
            anchors.verticalCenter: parent.verticalCenter
            elide: Text.ElideRight
            text: row.spec.name || ""
            font.pixelSize: theme.fontSmall
            color: theme.textDim

            HoverHandler { id: labelHover }
            NxtToolTip {
                shown: labelHover.hovered
                text: row.tipText
            }
        }

        ValueEditor {
            id: value
            anchors.right: editButton.left
            anchors.rightMargin: 2
            anchors.verticalCenter: parent.verticalCenter
            width: theme.valueWidth
            spec: row.spec
            owner: row.owner
            onEdited: function (v) { row.edited(v); }
        }

        // Its room is kept while hidden, so every value lines up.
        IconButton {
            id: editButton
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            opacity: rowHover.hovered || row.expanded ? 1 : 0
            enabled: !row.spec.readOnly
            tip: row.expanded ? qsTr("Close") : qsTr("Edit variable")
            highlighted: row.expanded
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
            onClicked: row.expanded ? row.close() : row.open()
        }
    }

    TextButton {
        visible: row.adding && !row.expanded
        text: qsTr("+ Add variable")
        primary: true
        onClicked: row.open()
    }

    Rectangle {
        visible: row.expanded
        width: row.width
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
                    width: row.formLabelWidth
                    height: theme.fieldHeight
                    verticalAlignment: Text.AlignVCenter
                    text: qsTr("Name")
                    font.pixelSize: theme.fontSmall
                    color: theme.textDim
                }
                TextField {
                    id: nameField
                    width: form.width - row.formLabelWidth - 6
                    placeholder: qsTr("FrameWidth")
                    onAccepted: row.save()
                    onDismissed: row.close()
                    onEdited: row.error = ""
                }
            }

            Row {
                spacing: 6
                Text {
                    id: typeCaption
                    width: row.formLabelWidth
                    height: theme.fieldHeight
                    verticalAlignment: Text.AlignVCenter
                    text: qsTr("Type")
                    font.pixelSize: theme.fontSmall
                    color: theme.textDim
                }
                // Set when the variable is made: FreeCAD can't change it.
                Text {
                    visible: !row.adding
                    height: theme.fieldHeight
                    verticalAlignment: Text.AlignVCenter
                    text: row.spec.typeLabel || ""
                    font.pixelSize: theme.fontSmall
                    color: theme.text
                }
                ValueEditor {
                    visible: row.adding
                    width: form.width - row.formLabelWidth - 6
                    labelled: false
                    spec: ({
                        name: "type", kind: "enum",
                        text: row.labelOf(row.typeId),
                        options: row.types.map(function (t) {
                            return t.label;
                        })
                    })
                    onEdited: function (v) {
                        for (var i = 0; i < row.types.length; ++i)
                            if (row.types[i].label === v)
                                row.typeId = row.types[i].id;
                    }
                }
            }

            Row {
                spacing: 6
                Text {
                    id: tipCaption
                    width: row.formLabelWidth
                    height: theme.fieldHeight
                    verticalAlignment: Text.AlignVCenter
                    text: qsTr("Tooltip")
                    font.pixelSize: theme.fontSmall
                    color: theme.textDim
                }
                TextField {
                    id: tipField
                    width: form.width - row.formLabelWidth - 6
                    placeholder: qsTr("What it sets")
                    onAccepted: row.save()
                    onDismissed: row.close()
                }
            }

            Text {
                visible: row.error.length > 0
                width: form.width
                wrapMode: Text.Wrap
                text: row.error
                font.pixelSize: theme.fontSmall
                color: theme.danger
            }

            Row {
                anchors.right: parent.right
                spacing: 2
                TextButton {
                    text: qsTr("Cancel")
                    onClicked: row.close()
                }
                TextButton {
                    text: row.adding ? qsTr("Add") : qsTr("Save")
                    primary: true
                    onClicked: row.save()
                }
            }
        }
    }
}
