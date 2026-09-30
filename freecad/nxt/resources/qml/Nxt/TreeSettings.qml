import QtQuick
import QtQuick.Controls.Basic

// The tree's quick settings, opened from the gear in the header.
//
// A popup in a window of its own, as the context menu is (see
// ContextMenu.qml), so it can be wider than a narrow dock and closes on
// Escape or a click elsewhere. Every control applies as it is changed -
// there is nothing to confirm. The same values are on the Preferences page,
// which the link at the bottom opens.
Popup {
    id: settingsPopup

    popupType: Popup.Window
    padding: 10
    width: 260
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    focus: true

    readonly property var values: prefs.values

    background: Rectangle {
        radius: 5
        color: theme.background
        border.width: 1
        border.color: theme.border
    }

    component Caption: Text {
        font.pixelSize: theme.fontAside
        color: theme.textDim
        topPadding: 4
    }

    contentItem: Column {
        spacing: 6

        Text {
            text: qsTr("Tree settings")
            font.pixelSize: theme.fontSmall
            font.bold: true
            color: theme.text
            bottomPadding: 2
        }

        Caption { text: qsTr("Part workbench models") }
        Segmented {
            width: parent.width
            value: settingsPopup.values.PartLayout
            options: [
                {value: "expression", label: qsTr("Expression rows")},
                {value: "nested", label: qsTr("Nested")}
            ]
            onPicked: function (v) { prefs.set("PartLayout", v); }
        }

        Caption { text: qsTr("Row density") }
        Segmented {
            width: parent.width
            value: settingsPopup.values.RowDensity
            options: [
                {value: "compact", label: qsTr("Compact")},
                {value: "normal", label: qsTr("Normal")},
                {value: "roomy", label: qsTr("Roomy")}
            ]
            onPicked: function (v) { prefs.set("RowDensity", v); }
        }

        Caption { text: qsTr("Overlay") }
        Segmented {
            width: parent.width
            value: settingsPopup.values.OverlayMode
            options: [
                {value: "freecad", label: qsTr("FreeCAD")},
                {value: "nxt", label: qsTr("Nxt (experimental)")}
            ]
            onPicked: function (v) { prefs.set("OverlayMode", v); }
        }

        Caption { text: qsTr("Reference chips") }
        Segmented {
            width: parent.width
            value: settingsPopup.values.ReferenceChips
            options: [
                {value: "problems", label: qsTr("Problems")},
                {value: "all", label: qsTr("All")},
                {value: "none", label: qsTr("None")}
            ]
            onPicked: function (v) { prefs.set("ReferenceChips", v); }
        }

        Item { width: 1; height: 2 }

        // An on/off setting. Written back, then shown from the store:
        // `checked` stays bound to what is saved, not to the last click.
        component Setting: NxtSwitch {
            required property string key
            width: parent.width
            checked: settingsPopup.values[key] === true
            onToggled: {
                prefs.set(key, checked);
                checked = Qt.binding(function () {
                    return settingsPopup.values[key] === true;
                });
            }
        }

        Setting {
            key: "UnderConstrainedMarks"
            text: qsTr("Mark under-constrained sketches")
        }
        Setting {
            key: "RowToolTips"
            text: qsTr("Show tooltips on rows")
        }
        Setting {
            key: "FollowSelection"
            text: qsTr("Show objects picked in the 3D view")
        }
        Setting {
            key: "EditOnDoubleClick"
            text: qsTr("Double-click a face to edit its feature")
        }
        Setting {
            key: "DependencyArrows"
            text: qsTr("Show dependency arrows")
        }

        Rectangle {
            width: parent.width
            height: 1
            color: theme.border
        }

        Text {
            text: qsTr("More preferences…")
            font.pixelSize: theme.fontSmall
            color: theme.link
            font.underline: moreMouse.containsMouse

            MouseArea {
                id: moreMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    settingsPopup.close();
                    prefs.openPage();
                }
            }
        }
    }

    onClosed: Qt.callLater(settingsPopup.destroy)
}
