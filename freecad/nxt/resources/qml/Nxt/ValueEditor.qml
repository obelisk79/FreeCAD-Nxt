import QtQuick

// The editor for one property, chosen by the property's kind rather than
// by the object it belongs to - which is what lets the inspector show objects
// nobody has written anything for.
//
//   quantity, number, text   a field. Return applies, Escape reverts, a
//                            leading "=" binds an expression. Entering it
//                            selects what you would retype.
//   bool                     a box.
//   enum                     a drop-down, its list above the whole panel.
//   color                    a swatch; clicking it opens a colour picker.
//   vector, placement        one small field per component.
//   link                     chips naming what it points at.
//   anything else            the value as text, with "Edit..." to hand it
//                            to FreeCAD's own editor.
//
// Read-only values are dimmed and italic, as the native editor greys them.
// A value that differs between several selected objects shows as mixed.
Item {
    id: editor

    property var spec: ({})
    property bool editable: true        // false where "Edit..." is wanted
    //: The object the property belongs to ("Document#Name" or "Name"),
    //: for help writing an expression; empty where none can be bound.
    property string owner: ""

    signal edited(var value)
    signal partEdited(string path, string text)
    signal colourRequested()
    signal nativeRequested()

    readonly property string kind: editor.spec.kind || ""
    readonly property bool locked: !!editor.spec.readOnly
    readonly property bool hasExpression:
        !!editor.spec.expression && editor.spec.expression.length > 0
    readonly property string shown: editor.hasExpression
                                    ? "= " + editor.spec.expression
                                    : (editor.spec.text || "")
    readonly property bool isField: editor.kind === "quantity"
                                    || editor.kind === "number"
                                    || editor.kind === "text"
    property bool choosing: false

    implicitWidth: body.implicitWidth
    implicitHeight: body.implicitHeight

    //: The leading number of a quantity, as the user's unit system writes
    //: it: a sign, digits, a decimal point or comma, an exponent.
    readonly property var leadingNumber: /^\s*[-+]?[\d.,]+(?:[eE][-+]?\d+)?/

    function selectValue() {
        var input = field.input;
        if (!input.activeFocus)
            return;
        var number = editor.kind === "quantity" && !editor.hasExpression
                     ? editor.leadingNumber.exec(input.text) : null;
        if (number)
            input.select(number[0].search(/\S/), number[0].length);
        else
            input.selectAll();
    }

    Component {
        id: choices
        ChoiceList {}
    }

    function openChoices(anchor) {
        var root = anchor.Window.contentItem;
        var list = choices.createObject(root, {
            options: editor.spec.options,
            current: editor.spec.text,
            below: anchor.mapToItem(root, 0, anchor.height),
            anchorHeight: anchor.height,
            minWidth: anchor.width
        });
        editor.choosing = true;
        list.chosen.connect(function (value) {
            if (value !== editor.spec.text)
                editor.edited(value);
        });
        list.Component.destruction.connect(function () {
            editor.choosing = false;
        });
        list.forceActiveFocus();
    }

    Column {
        id: body
        width: editor.width
        spacing: 3

        // --- a field ----------------------------------------------------- #
        Row {
            visible: editor.isField && !editor.locked
            spacing: 4
            width: parent.width
            height: theme.fieldHeight

            TextField {
                id: field
                owner: editor.kind === "text" ? "" : editor.owner
                width: parent.width - (unitLabel.visible
                                       ? unitLabel.width + 4 : 0)
                placeholder: editor.spec.mixed ? qsTr("— mixed") : ""
                Component.onCompleted: field.text = editor.spec.mixed
                                                    ? "" : editor.shown
                onAccepted: {
                    editor.edited(field.text);
                    field.input.focus = false;
                }
                onDismissed: {
                    field.text = editor.spec.mixed ? "" : editor.shown;
                    field.input.focus = false;
                }
                Connections {
                    target: editor
                    // A new value from the document, unless being typed.
                    function onShownChanged() {
                        if (!field.input.activeFocus)
                            field.text = editor.spec.mixed ? ""
                                                           : editor.shown;
                    }
                }
                Connections {
                    target: field.input
                    // Deferred: the press that focused the field places
                    // the cursor after this runs.
                    function onActiveFocusChanged() {
                        if (field.input.activeFocus)
                            Qt.callLater(editor.selectValue);
                    }
                }
            }

            Text {
                id: unitLabel
                anchors.verticalCenter: parent.verticalCenter
                visible: !!editor.spec.unit && !editor.hasExpression
                text: editor.spec.unit || ""
                font.pixelSize: theme.fontSmall
                color: theme.textDim
            }
        }

        // --- a yes/no ---------------------------------------------------- #
        Row {
            visible: editor.kind === "bool"
            spacing: 5
            height: theme.fieldHeight

            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                width: theme.markSize
                height: theme.markSize
                radius: 2
                opacity: editor.locked ? 0.5 : 1.0
                color: editor.spec.checked && !editor.spec.mixed
                       ? theme.accent : "transparent"
                border.width: 1
                border.color: editor.spec.checked ? theme.accent
                                                  : theme.border

                Text {
                    anchors.centerIn: parent
                    visible: !!editor.spec.checked || !!editor.spec.mixed
                    text: editor.spec.mixed ? "–" : "✓"
                    font.pixelSize: theme.fontAside
                    color: editor.spec.mixed ? theme.textDim
                                             : theme.accentText
                }
            }

            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: editor.spec.mixed ? qsTr("mixed")
                      : (editor.spec.checked ? qsTr("on") : qsTr("off"))
                font.pixelSize: theme.fontSmall
                font.italic: editor.locked
                color: editor.locked ? theme.textDim : theme.text
            }

            HoverHandler {
                enabled: !editor.locked
                cursorShape: Qt.PointingHandCursor
            }
            TapHandler {
                enabled: !editor.locked
                onTapped: editor.edited(!editor.spec.checked)
            }
        }

        // --- a choice ---------------------------------------------------- #
        Chip {
            id: choice
            visible: editor.kind === "enum"
            text: (editor.spec.mixed ? qsTr("— mixed") : (editor.spec.text || ""))
                  + (editor.locked ? "" : "  ▾")
            active: editor.choosing
            interactive: !editor.locked
            onClicked: if (!editor.choosing) editor.openChoices(choice)
        }

        // --- a colour ---------------------------------------------------- #
        Row {
            visible: editor.kind === "color"
            spacing: 6
            height: theme.fieldHeight

            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                width: theme.markSize + 2
                height: theme.markSize + 2
                radius: 2
                color: editor.spec.text || "transparent"
                border.width: 1
                border.color: theme.border
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: editor.spec.mixed ? qsTr("mixed") : (editor.spec.text || "")
                font.pixelSize: theme.fontSmall
                color: theme.text
            }
            HoverHandler {
                enabled: !editor.locked
                cursorShape: Qt.PointingHandCursor
            }
            TapHandler {
                enabled: !editor.locked
                onTapped: editor.colourRequested()
            }
        }

        // --- components -------------------------------------------------- #
        // A placement is two lines: where (X Y Z) and how it is turned
        // (axis X Y Z and an angle). A vector is one line.
        Repeater {
            model: editor.kind === "placement" ? [qsTr("Position"), qsTr("Rotation")]
                 : editor.kind === "vector" ? [""] : []

            Column {
                id: line
                required property string modelData
                required property int index
                width: body.width
                spacing: 2

                Text {
                    visible: line.modelData.length > 0
                    text: line.modelData
                    font.pixelSize: theme.fontAside
                    color: theme.textDim
                }

                Flow {
                    width: parent.width
                    spacing: 4

                    Repeater {
                        // Position: parts 0-2. Rotation: 3-6.
                        model: {
                            var parts = editor.spec.parts || [];
                            if (editor.kind !== "placement")
                                return parts;
                            return line.index === 0 ? parts.slice(0, 3)
                                                    : parts.slice(3);
                        }

                        Row {
                            id: part
                            required property var modelData
                            spacing: 3
                            height: theme.fieldHeight

                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: part.modelData.label
                                font.pixelSize: theme.fontAside
                                font.bold: true
                                color: theme.textDim
                            }
                            TextField {
                                id: partField
                                width: 58
                                Component.onCompleted:
                                    partField.text = part.modelData.text
                                onAccepted: {
                                    editor.partEdited(part.modelData.path,
                                                      partField.text);
                                    partField.input.focus = false;
                                }
                                onDismissed: {
                                    partField.text = part.modelData.text;
                                    partField.input.focus = false;
                                }
                            }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                visible: part.modelData.unit.length > 0
                                text: part.modelData.unit
                                font.pixelSize: theme.fontAside
                                color: theme.textDim
                            }
                        }
                    }
                }
            }
        }

        // --- links ------------------------------------------------------- #
        Flow {
            visible: editor.kind === "link"
            width: parent.width
            spacing: 3

            Repeater {
                model: editor.kind === "link" ? editor.spec.links : []
                Chip {
                    required property string modelData
                    text: modelData
                    interactive: false
                }
            }
            Text {
                visible: editor.kind === "link"
                         && (!editor.spec.links
                             || editor.spec.links.length === 0)
                text: qsTr("none")
                font.pixelSize: theme.fontSmall
                font.italic: true
                color: theme.textDim
            }
        }

        // --- read-only, or no editor of our own --------------------------- #
        Row {
            visible: (editor.isField && editor.locked)
                     || editor.kind === "other"
                     || (editor.kind === "link" && !editor.locked)
            spacing: 6
            width: parent.width

            Text {
                width: Math.min(implicitWidth,
                                parent.width - (edit.visible
                                                ? edit.width + 6 : 0))
                visible: editor.kind !== "link"
                text: editor.shown + (editor.spec.unit
                                      ? " " + editor.spec.unit : "")
                elide: Text.ElideRight
                font.pixelSize: theme.fontSmall
                font.italic: editor.locked
                color: theme.textDim
                Accessible.name: qsTr("%1, read only").arg(editor.spec.label || "")
            }

            // Hands this one property to FreeCAD's own editor: kinds we
            // have no editor for, and links, which want picking in the 3D
            // view rather than typing.
            Text {
                id: edit
                visible: !editor.locked && (editor.kind === "other"
                                            || editor.kind === "link")
                text: qsTr("Edit…")
                font.pixelSize: theme.fontSmall
                font.underline: editHover.hovered
                color: theme.link
                Accessible.role: Accessible.Button
                Accessible.name: qsTr("Edit %1").arg(editor.spec.label || "")

                HoverHandler {
                    id: editHover
                    cursorShape: Qt.PointingHandCursor
                }
                TapHandler { onTapped: editor.nativeRequested() }
            }
        }
    }
}
