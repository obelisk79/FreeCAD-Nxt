import QtQuick
import QtQuick.Controls.Basic
import Nxt.Controls

// The tree's quick settings popup, opened from the header gear. Applies live;
// the same values are on the Preferences page.
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

        Caption { text: qsTr("Tree structure") }
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
                {value: "nxt", label: qsTr("Nxt")}
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

        // Shows a click at once, then follows the stored value.
        component Setting: NxtSwitch {
            required property string key
            width: parent.width
            stored: settingsPopup.values[key] === true
            onChangedTo: function (on) { prefs.set(key, on); }
        }

        Setting {
            key: "EditOnDoubleClick"
            text: qsTr("Double-click a face to edit its feature")
        }
        Setting {
            key: "DependencyArrows"
            text: qsTr("Show dependency arrows")
        }
        Setting {
            key: "HighlightRelated"
            text: qsTr("Highlight related objects")
        }
        Setting {
            key: "TreeLines"
            text: qsTr("Show tree lines")
        }
        Setting {
            key: "DetailAutoShow"
            text: qsTr("Show details on click")
        }
        Setting {
            key: "QuickMass"
            text: qsTr("Show Quick Mass in the 3D view")
        }
        Setting {
            key: "RepairProfiles"
            text: qsTr("Auto repair 'Wire not closed' errors")
        }
        Setting {
            key: "SketchPanel"
            text: qsTr("Experimental sketch task panel")
        }
        Setting {
            key: "AttachPanel"
            text: qsTr("Experimental attachment panel")
        }
        Setting {
            key: "AutoRename"
            text: qsTr("Rename new objects")
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
