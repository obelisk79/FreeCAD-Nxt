import QtQuick
import Nxt.Controls
import Nxt.Tree

// Experimental: the sketch dialog's cards (tools/sketch_panel.py puts this
// in place of FreeCAD's solver message). `sketch` is its bridge. Nothing
// but the closed Contents card shows until the solver finds a problem, or
// one element or constraint is selected; with Contents open, a selection
// shows under its row there instead. The chips on a selection's card
// select what they name.
Item {
    id: root

    readonly property int gap: 10
    readonly property var picked: sketch.selection
    readonly property var groups: sketch.issues
    //: The selection shows in the Contents list, under its row.
    readonly property bool listing: sketch.contents.open

    implicitWidth: 300
    implicitHeight: column.implicitHeight + 2 * gap

    Rectangle { anchors.fill: parent; color: theme.background }

    component Card: Rectangle {
        default property alias content: inner.children
        width: column.width
        height: inner.implicitHeight + 20
        radius: 6
        color: theme.surface
        border.width: 1
        border.color: theme.border
        Column {
            id: inner
            x: 10; y: 10
            width: parent.width - 20
            spacing: 6
        }
    }

    component Caption: Text {
        font.pixelSize: theme.fontAside
        font.capitalization: Font.AllUppercase
        color: theme.textDim
    }

    // One constraint: its number, what it is, and what may be done to it.
    component ConstraintRow: Item {
        id: line

        property var row: ({})
        property bool fixes: false
        readonly property bool known: row !== undefined
                                      && row.number !== undefined

        width: parent.width
        height: theme.rowHeight
        opacity: known && row.active === false ? 0.55 : 1.0

        Text {
            id: number
            anchors.verticalCenter: parent.verticalCenter
            width: Math.round(theme.fontSmall * 2)
            horizontalAlignment: Text.AlignRight
            text: line.known ? line.row.number : ""
            font.pixelSize: theme.fontSmall
            color: theme.textDim
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: number.right
            anchors.leftMargin: 8
            anchors.right: actions.left
            anchors.rightMargin: 6
            elide: Text.ElideRight
            textFormat: Text.PlainText
            text: !line.known ? ""
                : line.row.name ? line.row.name + "  " + line.row.value
                : line.row.value ? line.row.label + "  " + line.row.value
                                 : line.row.label
            font.pixelSize: theme.fontSmall
            color: theme.text
        }
        Row {
            id: actions
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            visible: line.fixes && line.known
            spacing: 2

            IconButton {
                paint: line.known && line.row.active ? Glyphs.deactivate
                                                     : Glyphs.activate
                tip: line.known && line.row.active ? qsTr("Deactivate")
                                                   : qsTr("Activate")
                onClicked: sketch.setActive(line.row.index,
                                            !line.row.active)
            }
            IconButton {
                visible: line.known && line.row.dimensional
                         && line.row.driving
                paint: Glyphs.reference
                tip: qsTr("Make reference")
                onClicked: sketch.setDriving(line.row.index, false)
            }
            IconButton {
                paint: Glyphs.remove
                tip: qsTr("Delete")
                onClicked: sketch.remove(line.row.index)
            }
        }
    }

    // Chips that select what they name: each item has `title` and `name`.
    component Picks: Flow {
        id: picks
        property var items: []
        width: parent.width
        spacing: 4
        // By count: a new list would rebuild the chip under its click.
        Repeater {
            model: picks.items.length
            Chip {
                required property int index
                readonly property var item: picks.items[index] || ({})
                text: item.title || ""
                tip: item.tip || ""
                onClicked: sketch.pick(item.name)
            }
        }
    }

    Column {
        id: column
        x: root.gap
        y: root.gap
        width: root.width - 2 * root.gap
        spacing: root.gap

        // -- what the solver found --
        // By count: a new list would rebuild the rows under a click.
        Repeater {
            model: root.groups.length

            Card {
                id: issue

                required property int index
                readonly property var group: root.groups[index] || ({})
                readonly property var rows: group.rows || []

                border.color: group.mark >= 3 ? theme.danger : theme.warning

                Row {
                    spacing: 6
                    SeverityMark {
                        anchors.verticalCenter: parent.verticalCenter
                        level: issue.group.mark || 0
                        size: theme.markSizeSmall
                    }
                    Caption {
                        anchors.verticalCenter: parent.verticalCenter
                        text: issue.group.title || ""
                    }
                }
                Repeater {
                    model: issue.rows.length
                    ConstraintRow {
                        required property int index
                        row: issue.rows[index]
                        fixes: true
                    }
                }
                TextButton {
                    visible: issue.group.key === "MalformedConstraints"
                    text: qsTr("Validate sketch…")
                    primary: true
                    onClicked: sketch.validate()
                }
            }
        }

        // -- the element selected --
        Card {
            id: elementCard

            readonly property var rows: root.picked.rows || []

            visible: root.picked.kind === "element" && !root.listing

            Text {
                text: root.picked.title || ""
                font.pixelSize: theme.fontRow
                font.bold: true
                color: theme.text
            }
            NxtSwitch {
                width: parent.width
                text: qsTr("Construction")
                stored: root.picked.construction === true
                onChangedTo: function (on) {
                    sketch.setConstruction(root.picked.geo, on);
                }
            }
            Caption {
                text: elementCard.rows.length ? qsTr("Constraints on it")
                                              : qsTr("No constraints on it")
            }
            Picks {
                items: elementCard.rows.map(function (row) {
                    var said = row.name || row.label;
                    return {title: row.number + "  " + said
                                   + (row.value ? "  " + row.value : ""),
                            name: "Constraint" + row.number};
                })
            }
        }

        // -- the constraint selected --
        Card {
            visible: root.picked.kind === "constraint" && !root.listing

            Item {
                width: parent.width
                height: title.implicitHeight
                Text {
                    id: title
                    text: root.picked.label
                          ? root.picked.label + " " + root.picked.number : ""
                    font.pixelSize: theme.fontRow
                    font.bold: true
                    color: theme.text
                }
                Text {
                    anchors.right: parent.right
                    anchors.baseline: title.baseline
                    text: root.picked.value || ""
                    font.pixelSize: theme.fontSmall
                    color: theme.textDim
                }
            }
            TextField {
                id: nameField

                // The constraint being named: the selection may move on
                // before the field is left.
                property int naming: -1
                readonly property string stored: root.picked.name || ""

                function revert() {
                    text = stored;
                    naming = -1;
                }
                function apply() {
                    if (naming >= 0 && text !== stored)
                        sketch.rename(naming, text);
                    naming = -1;
                }

                width: parent.width
                height: theme.fieldHeight
                placeholder: qsTr("Name")
                Component.onCompleted: revert()
                onEdited: {
                    if (input.activeFocus && naming < 0
                            && root.picked.index !== undefined)
                        naming = root.picked.index;
                }
                onAccepted: apply()
                onDismissed: {
                    revert();
                    input.focus = false;
                }
                input.onActiveFocusChanged: {
                    if (!input.activeFocus)
                        apply();
                }

                Connections {
                    target: sketch
                    function onChanged() {
                        if (nameField.naming < 0)
                            nameField.revert();
                    }
                }
            }
            Caption {
                visible: (root.picked.geometry || []).length > 0
                text: qsTr("Geometry")
            }
            Picks {
                items: root.picked.geometry || []
            }
            NxtSwitch {
                width: parent.width
                visible: root.picked.dimensional === true
                text: qsTr("Driving")
                stored: root.picked.driving === true
                onChangedTo: function (on) {
                    sketch.setDriving(root.picked.index, on);
                }
            }
            NxtSwitch {
                width: parent.width
                text: qsTr("Active")
                stored: root.picked.active === true
                onChangedTo: function (on) {
                    sketch.setActive(root.picked.index, on);
                }
            }
        }

        // -- the sketch's elements and constraints --
        SketchContents {
            width: parent.width
        }

        // FreeCAD's own lists, below the panel, while this is experimental.
        TextButton {
            readonly property bool on: sketch.browsing.length > 0
            text: on ? qsTr("Hide FreeCAD's lists")
                     : qsTr("Show FreeCAD's lists")
            onClicked: {
                sketch.browse("constraints", !on);
                sketch.browse("elements", !on);
            }
        }
    }
}
