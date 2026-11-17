import QtQuick
import QtQuick.Controls.Basic

// A drop-down's list of options, in a window of its own (Popup.Window):
// it may reach past the panel to the edges of the application window,
// and a long list scrolls in itself rather than the panel behind it.
// Opens from a 1px anchor, which Wayland places popups against.
Item {
    id: popup

    property var options: []
    //: Display text per option, if not the value.
    property var labels: []
    property string current: ""
    property point below            // anchor's bottom-left, in our coords
    property real anchorHeight: 0
    property real minWidth: 80

    readonly property int optionPad: 10
    readonly property int gap: 2
    //: As a combo box's maxVisibleItems.
    readonly property int mostRows: 15
    //: As the desktop's wheelScrollLines.
    readonly property int wheelRows: 3
    readonly property int notch: 120
    readonly property alias listWidth: frame.width

    signal chosen(string value)
    //: Closed by a press outside, which may be on the field it came from.
    signal pressedAway()
    property bool escaped: false

    // Destroyed after the closing event, or its release hits what is below.
    function dismiss() {
        frame.close();
    }

    function labelAt(i) {
        return (popup.labels && popup.labels[i]) || popup.options[i];
    }

    // The tree's host knows its own placement; the Property Inspector's
    // is found from this item's view (expressions).
    function offset() {
        if (typeof host !== "undefined" && host)
            return host.menuAnchorOffset();
        if (typeof expressions !== "undefined" && expressions)
            return expressions.anchorOffset(popup);
        return Qt.point(0, 0);
    }
    function room() {
        if (typeof host !== "undefined" && host)
            return host.menuRoom();
        if (typeof expressions !== "undefined" && expressions)
            return expressions.popupRoom(popup);
        return Qt.rect(0, 0, 0, 0);
    }

    // Measured, since the list's width derives from the box (circular).
    FontMetrics {
        id: metrics
        font.pixelSize: theme.fontSmall
        font.bold: true
    }
    readonly property real widest: {
        var most = 0;
        for (var i = 0; i < popup.options.length; ++i)
            most = Math.max(most, metrics.advanceWidth(popup.labelAt(i)));
        return most;
    }

    // Below the field if it fits, else above, else as low as it fits;
    // never taller than the room (the list scrolls).
    function place() {
        var wide = frame.width;
        var tall = Math.min(popup.options.length, popup.mostRows)
                   * theme.rowHeight + 2;
        var at = Qt.point(popup.below.x, popup.below.y + popup.gap);
        var space = popup.room();
        if (space.width > 0 && space.height > 0) {
            tall = Math.min(tall, space.height);
            var bottom = space.y + space.height;
            var above = popup.below.y - popup.anchorHeight - popup.gap - tall;
            if (at.y + tall > bottom)
                at.y = above >= space.y ? above : bottom - tall;
            at.x = Math.max(space.x, Math.min(at.x, space.x + space.width
                                                    - wide));
        }
        frame.height = tall;
        var shift = popup.offset();
        anchor.x = at.x + shift.x;
        anchor.y = at.y + shift.y;
    }

    Component.onCompleted: {
        popup.place();
        frame.open();
        var at = popup.options.indexOf(popup.current);
        if (at >= 0)
            options.positionViewAtIndex(at, ListView.Center);
    }

    Item {
        id: anchor
        width: 1
        height: 1
    }

    Popup {
        id: frame

        parent: anchor
        x: 0
        y: 0
        popupType: Popup.Window
        focus: true
        modal: false
        closePolicy: Popup.CloseOnPressOutside
        padding: 1
        enter: null
        exit: null
        width: Math.max(popup.minWidth,
                        Math.ceil(popup.widest) + 2 * popup.optionPad + 2)
        onClosed: {
            if (!popup.escaped)
                popup.pressedAway();
            Qt.callLater(popup.destroy);
        }

        background: Rectangle {
            radius: 3
            color: theme.background
            border.width: 1
            border.color: theme.border
        }

        contentItem: ListView {
            id: options

            clip: true
            // Stepped by the wheel at once, as a desktop list is: a
            // flick still settling would eat the click that follows.
            interactive: false
            focus: true
            model: popup.options

            Keys.onEscapePressed: {
                popup.escaped = true;
                frame.close();
            }

            // Above the rows, taking only the wheel: clicks and hover
            // still reach them.
            MouseArea {
                anchors.fill: parent
                z: 1
                acceptedButtons: Qt.NoButton
                onWheel: function (wheel) {
                    var step = wheel.pixelDelta.y !== 0 ? wheel.pixelDelta.y
                             : wheel.angleDelta.y / popup.notch
                               * popup.wheelRows * theme.rowHeight;
                    bar.scrollTo(options.contentY - step);
                }
            }

            NxtScrollBar {
                id: bar
                target: options
                anchors.top: parent.top
                anchors.right: parent.right
                anchors.bottom: parent.bottom
            }

            delegate: Rectangle {
                id: option
                required property string modelData
                required property int index
                readonly property bool isCurrent:
                    modelData === popup.current

                width: ListView.view.width
                height: theme.rowHeight
                color: hover.pressed ? theme.pressed
                     : hover.hovered ? theme.hover : "transparent"

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    x: popup.optionPad
                    text: popup.labelAt(option.index)
                    font.pixelSize: theme.fontSmall
                    font.bold: option.isCurrent
                    color: theme.text
                }

                // MouseArea, not TapHandler: nothing below sees the click.
                MouseArea {
                    id: hover
                    readonly property bool hovered: containsMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: {
                        // Dismiss first: choosing can destroy the
                        // field, and this context with it.
                        var value = option.modelData;
                        var list = popup;
                        list.dismiss();
                        list.chosen(value);
                    }
                }
            }
        }
    }
}
