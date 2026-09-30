import QtQuick
import QtQuick.Controls.Basic

// Nxt's tooltip: Qt Quick's own ToolTip, drawn in the panel's theme.
//
// Drop one inside whatever it explains and bind `shown` to that item's
// hover; it fills its parent, so the tip lines up under it. Nothing is
// built until the pointer has rested for `delay` ms: a tree has hundreds
// of rows with several of these each, and a ToolTip per control, made up
// front, would cost a popup object per control per row for tips almost
// none of which are ever seen.
//
// In a window of its own (Popup.Window), as the context menu and the
// settings popup are, so a narrow dock does not clip it. Off entirely
// when the "Show tooltips on rows" preference is (theme.showToolTips).
Item {
    id: root

    property bool shown: false
    property string text: ""
    property int delay: 450

    anchors.fill: parent

    readonly property bool wanted: shown && theme.showToolTips
                                   && text.length > 0

    // Set once the pointer has rested; cleared the moment it leaves.
    property bool open: false

    onWantedChanged: {
        if (wanted) {
            settle.restart();
        } else {
            settle.stop();
            open = false;
        }
    }

    Timer {
        id: settle
        interval: root.delay
        onTriggered: {
            root.open = root.wanted;
            loader.active = loader.active || root.open;
        }
    }

    // Built the first time it is wanted, then kept: showing and hiding an
    // existing popup is immediate, where destroying one leaves its window
    // up until the deletion is processed.
    Loader {
        id: loader
        anchors.fill: parent
        active: false
        sourceComponent: ToolTip {
            id: tip
            popupType: Popup.Window
            visible: root.open
            enter: null
            exit: null
            timeout: -1
            padding: 6
            text: root.text

            contentItem: Text {
                text: tip.text
                font.pixelSize: theme.fontSmall
                color: theme.text
                wrapMode: Text.NoWrap
            }

            background: Rectangle {
                radius: 4
                color: theme.surface
                border.width: 1
                border.color: theme.border
            }
        }
    }
}
