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

    // Where the pointer rested, in this item: the tip opens just below and
    // to the right of it, as a native tooltip does, rather than centred
    // on the control - which on a small control inside a scaled or
    // overlaid panel landed well away from the pointer.
    property point anchor: Qt.point(0, 0)

    HoverHandler { id: pointer }

    // What the tip opens from: a one-pixel item at the spot, not the
    // control. Under Wayland a popup in a window of its own is placed
    // against the rectangle of the item it opens from, taken in that
    // item's window - and the panel's window is an offscreen one at the
    // corner of FreeCAD's - so the tip landed a panel's offset away from
    // the pointer. The context menu opens the same way; see
    // host.menuAnchorOffset(), zero everywhere but Wayland.
    Item {
        id: spot
        width: 1
        height: 1
    }

    function offset() {
        return (typeof host !== "undefined" && host)
               ? host.menuAnchorOffset() : Qt.point(0, 0);
    }

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
            root.anchor = pointer.point.position;
            var shift = root.offset();
            spot.x = root.anchor.x + 12 + shift.x;
            spot.y = root.anchor.y + 20 + shift.y;
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
            parent: spot
            x: 0
            y: 0
            // Kept this far inside the screen near an edge.
            margins: 4
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
