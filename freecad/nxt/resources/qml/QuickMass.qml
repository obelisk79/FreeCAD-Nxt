import QtQuick
import QtQuick.Controls.Basic

// Quick Mass at the bottom centre of the 3D view (quick_mass.py): material,
// unit system, and the selection's mass. Sized to its content.
Rectangle {
    id: bar

    implicitWidth: row.implicitWidth + 16
    implicitHeight: Math.round(theme.rowHeight * 1.5)
    radius: 5
    color: theme.surface
    border.width: 1
    border.color: theme.border

    // A field that opens its options in a window of its own, upwards.
    component Picker: Rectangle {
        id: picker

        property var options: []
        property int current: 0
        property bool searchable: false
        property real fieldWidth: 150
        signal picked(int index)

        width: fieldWidth
        height: Math.round(bar.height * 0.72)
        radius: 3
        color: pickerMouse.pressed ? theme.pressed
             : pickerMouse.containsMouse ? theme.hover : theme.background
        border.width: 1
        border.color: list.opened ? theme.accent : theme.border

        Text {
            anchors.verticalCenter: parent.verticalCenter
            x: 8
            width: parent.width - 26
            elide: Text.ElideRight
            text: picker.options[picker.current] || ""
            font.pixelSize: theme.fontSmall
            color: theme.text
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            anchors.right: parent.right
            anchors.rightMargin: 7
            text: "▴"
            font.pixelSize: theme.fontSmall
            color: theme.textDim
        }

        MouseArea {
            id: pickerMouse
            anchors.fill: parent
            hoverEnabled: true
            onClicked: list.opened ? list.close() : picker.openList()
        }

        // Wayland places a popup against its parent item's whole rect, so
        // the list opens from a 1px item in the bar (as NxtTree's menus do).
        function openList() {
            var at = picker.mapToItem(bar, 0, 0);
            var offset = quickMass.anchorOffset();
            listAnchor.x = at.x + offset.x;
            listAnchor.y = at.y - list.height - 3 + offset.y;
            list.parent = listAnchor;
            list.x = 0;
            list.y = 0;
            list.open();
        }

        Popup {
            id: list

            popupType: Popup.Window
            padding: 1
            width: Math.max(picker.width, 220)
            height: Math.min(360, column.implicitHeight + 2)
            closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
            focus: true

            property string query: ""
            readonly property var shown: {
                var out = [];
                var q = list.query.toLowerCase();
                for (var i = 0; i < picker.options.length; ++i)
                    if (!q || picker.options[i].toLowerCase().indexOf(q) >= 0)
                        out.push(i);
                return out;
            }

            onOpened: {
                list.query = "";
                filter.text = "";
                if (picker.searchable)
                    filter.forceActiveFocus();
                var at = list.shown.indexOf(picker.current);
                if (at >= 0)
                    view.positionViewAtIndex(at, ListView.Center);
            }

            background: Rectangle {
                radius: 3
                color: theme.background
                border.width: 1
                border.color: theme.border
            }

            contentItem: Column {
                id: column

                Rectangle {
                    visible: picker.searchable
                    width: parent.width
                    height: visible ? theme.rowHeight + 6 : 0
                    color: "transparent"

                    TextInput {
                        id: filter
                        anchors.fill: parent
                        anchors.margins: 6
                        verticalAlignment: TextInput.AlignVCenter
                        font.pixelSize: theme.fontSmall
                        color: theme.text
                        clip: true
                        onTextChanged: list.query = text
                        Keys.onReturnPressed: {
                            if (list.shown.length > 0) {
                                picker.picked(list.shown[0]);
                                list.close();
                            }
                        }
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        x: 6
                        visible: filter.text.length === 0
                        text: qsTr("Filter materials")
                        font.pixelSize: theme.fontSmall
                        color: theme.textDim
                    }
                    Rectangle {
                        anchors.bottom: parent.bottom
                        width: parent.width
                        height: 1
                        color: theme.border
                    }
                }

                ListView {
                    id: view
                    width: parent.width
                    height: Math.min(contentHeight,
                                     360 - (picker.searchable
                                            ? theme.rowHeight + 8 : 2))
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    model: list.shown

                    delegate: Rectangle {
                        id: option
                        required property int modelData
                        width: view.width
                        height: theme.rowHeight
                        color: optionMouse.pressed ? theme.pressed
                             : optionMouse.containsMouse ? theme.hover
                                                         : "transparent"

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            x: 8
                            text: picker.options[option.modelData]
                            font.pixelSize: theme.fontSmall
                            font.bold: option.modelData === picker.current
                            color: theme.text
                        }

                        MouseArea {
                            id: optionMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            onClicked: {
                                picker.picked(option.modelData);
                                list.close();
                            }
                        }
                    }
                }
            }
        }
    }

    Item {
        id: listAnchor
        width: 1
        height: 1
    }

    Row {
        id: row
        anchors.centerIn: parent
        spacing: 8

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: qsTr("Quick Mass")
            font.pixelSize: theme.fontSmall
            font.bold: true
            color: theme.textDim
        }

        Picker {
            anchors.verticalCenter: parent.verticalCenter
            fieldWidth: 170
            searchable: true
            options: quickMass.materials
            current: quickMass.material
            onPicked: function (index) { quickMass.pickMaterial(index); }
            Accessible.name: qsTr("Material")
        }

        Picker {
            anchors.verticalCenter: parent.verticalCenter
            fieldWidth: 170
            options: quickMass.units
            current: quickMass.unit
            onPicked: function (index) { quickMass.pickUnit(index); }
            Accessible.name: qsTr("Unit system")
        }

        // A fixed width: resizing the bar as the mass changes would resize
        // its view mid-frame.
        TextMetrics {
            id: widest
            font.pixelSize: theme.fontSmall
            font.bold: true
            text: qsTr("Select a solid or body") + "  "
        }

        Text {
            anchors.verticalCenter: parent.verticalCenter
            width: Math.ceil(widest.advanceWidth)
            elide: Text.ElideLeft
            horizontalAlignment: Text.AlignRight
            text: quickMass.mass
            font.pixelSize: theme.fontSmall
            font.bold: true
            color: theme.text
        }
    }
}
