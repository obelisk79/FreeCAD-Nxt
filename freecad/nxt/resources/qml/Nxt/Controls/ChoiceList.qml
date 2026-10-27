import QtQuick

// A drop-down's list of options. Created on the window's content item,
// since rows clip their content and later rows draw over earlier ones.
Item {
    id: popup

    property var options: []
    //: Display text per option, if not the value.
    property var labels: []
    property string current: ""
    property point below            // anchor's bottom-left, in our coords
    property real anchorHeight: 0
    property real minWidth: 80

    signal chosen(string value)

    anchors.fill: parent
    z: 10000
    focus: true

    // Destroyed after the closing event, or its release hits what is below.
    function dismiss() {
        popup.visible = false;
        Qt.callLater(popup.destroy);
    }

    // Measured, since the Column's width derives from the box (circular).
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
    readonly property int optionPad: 10

    function labelAt(i) {
        return (popup.labels && popup.labels[i]) || popup.options[i];
    }

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
                    required property int index
                    readonly property bool isCurrent:
                        modelData === popup.current

                    width: box.width - 2
                    height: theme.rowHeight
                    color: hover.pressed ? theme.pressed
                         : hover.hovered ? theme.hover : "transparent"

                    Text {
                        id: label
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
}
