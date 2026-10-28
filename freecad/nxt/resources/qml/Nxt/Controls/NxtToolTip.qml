import QtQuick
import QtQuick.Controls.Basic

// Nxt's tooltip, in its own window (Popup.Window) so a narrow dock does not
// clip it. Built lazily: a tree has hundreds of rows with several each.
Item {
    id: root

    property bool shown: false
    property string text: ""
    property int delay: 450

    anchors.fill: parent

    readonly property bool wanted: shown && theme.showToolTips
                                   && text.length > 0

    property bool open: false

    // Opens below-right of the pointer, as a native tooltip does.
    property point anchor: Qt.point(0, 0)

    HoverHandler { id: pointer }

    // Opens from a 1px item at the spot: under Wayland the popup is placed
    // against the anchor in the offscreen panel window. The tree's host
    // knows its offset (host.menuAnchorOffset()); other views, such as the
    // Property Inspector, have no host, and the offset is found from this
    // item's own view (expressions.anchorOffset, quick_host.popup_offset).
    Item {
        id: spot
        width: 1
        height: 1
    }

    function offset() {
        if (typeof host !== "undefined" && host)
            return host.menuAnchorOffset();
        if (typeof expressions !== "undefined" && expressions)
            return expressions.anchorOffset(root);
        return Qt.point(0, 0);
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

    // Kept once built: destroying a popup leaves its window up until deleted.
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
