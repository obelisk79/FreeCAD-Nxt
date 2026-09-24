import QtQuick

// A drop-down's list of options.
//
// Created on the window's content item rather than inside the row that
// opened it: a row's strip clips its content and later rows draw over
// earlier ones, so a list opened in place would be cut off or covered.
// Up here it sits above the whole panel, and a press anywhere outside the
// list closes it. It opens below its anchor, or above it when there is no
// room below.
Item {
    id: popup

    property var options: []
    property string current: ""
    property point below            // anchor's bottom-left, in our coords
    property real anchorHeight: 0
    property real minWidth: 80

    signal chosen(string value)

    anchors.fill: parent
    z: 10000
    focus: true

    // Hidden at once, destroyed after the event that closed it has been
    // delivered: destroying mid-event let the release fall through to
    // whatever was underneath - the "All properties" link, which opened
    // the inspector.
    function dismiss() {
        popup.visible = false;
        Qt.callLater(popup.destroy);
    }

    // Wide enough for the longest option. A Column's implicit width is
    // taken from its children's widths, which here come from the box -
    // asking it for its width was circular and gave the minimum.
    FontMetrics {
        id: metrics
        font.pixelSize: theme.fontSmall
        font.bold: true
    }
    readonly property real widest: {
        var most = 0;
        for (var i = 0; i < popup.options.length; ++i)
            most = Math.max(most, metrics.advanceWidth(popup.options[i]));
        return most;
    }
    readonly property int optionPad: 10

    Keys.onEscapePressed: popup.dismiss()

    MouseArea {
        anchors.fill: parent
        onPressed: popup.dismiss()
    }

    Rectangle {
        id: box

        readonly property real gap: 2
        readonly property bool fitsBelow:
            popup.below.y + gap + height <= popup.height

        x: Math.max(0, Math.min(popup.below.x, popup.width - width))
        y: fitsBelow ? popup.below.y + gap
                     : Math.max(0, popup.below.y - popup.anchorHeight
                                   - gap - height)
        width: Math.max(popup.minWidth,
                        Math.ceil(popup.widest) + 2 * popup.optionPad + 2)
        height: list.implicitHeight + 2
        radius: 3
        color: theme.background
        border.width: 1
        border.color: theme.border

        // Swallows presses on the list's own padding, so they do not
        // reach the close-on-press area underneath.
        MouseArea { anchors.fill: parent }

        Column {
            id: list
            x: 1
            y: 1

            Repeater {
                model: popup.options

                Rectangle {
                    id: option
                    required property string modelData
                    readonly property bool isCurrent:
                        modelData === popup.current

                    width: box.width - 2
                    height: theme.rowHeight
                    color: hover.hovered ? theme.hover : "transparent"

                    Text {
                        id: label
                        anchors.verticalCenter: parent.verticalCenter
                        x: popup.optionPad
                        text: option.modelData
                        font.pixelSize: theme.fontSmall
                        font.bold: option.isCurrent
                        color: theme.text
                    }

                    // A MouseArea, not a TapHandler: it takes the press
                    // outright, so nothing underneath sees any of the click.
                    MouseArea {
                        id: hover
                        readonly property bool hovered: containsMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            popup.chosen(option.modelData);
                            popup.dismiss();
                        }
                    }
                }
            }
        }
    }
}
