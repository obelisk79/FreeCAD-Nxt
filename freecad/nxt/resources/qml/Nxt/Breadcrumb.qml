import QtQuick

// "Bracket › Body › Pocket001": the containers the top of the list is
// inside, once their own rows have scrolled away. Pinned over the top of
// the list; a name scrolls back to its row. Hidden with nothing to say.
Item {
    id: bar

    //: Outermost first: [{row, label}].
    property var crumbs: []
    signal crumbClicked(int row)

    //: Space at each end, and either side of a separator.
    readonly property int pad: theme.rowPad + 4
    readonly property int gap: 6
    readonly property bool overflows: path.width > width - 2 * pad
    //: How far the trail is scrolled back from its end, to show the outer
    //: names a long trail has no room for. Back to the end on every new
    //: trail: the innermost names are the ones that say where you are.
    property real scroll: 0
    readonly property real maxScroll:
        Math.max(0, path.width - (width - 2 * pad))
    //: The pointer is over the strip: in Nxt's overlay the panel's wheel
    //: asks this before scrolling the list (NxtTree.qml's scrollWheel).
    readonly property bool hovered: hover.hovered

    function scrollBy(distance) {
        scroll = Math.max(0, Math.min(maxScroll, scroll + distance));
    }

    onCrumbsChanged: scroll = 0
    onMaxScrollChanged: scrollBy(0)

    height: theme.rowHeight + 4
    visible: crumbs.length > 0
    clip: true

    // Docked, a strip of the panel with a divider under it; in Nxt's
    // overlay a pill, as the header and the rows are there.
    Rectangle {
        anchors.fill: parent
        anchors.margins: theme.overlay ? 2 : 0
        radius: theme.overlay ? 4 : 0
        color: theme.overlay ? theme.pill : theme.background
        border.width: theme.overlay ? 1 : 0
        border.color: theme.pillBorder
    }
    Rectangle {
        anchors.bottom: parent.bottom
        width: parent.width
        height: 1
        visible: !theme.overlay
        color: theme.border
    }

    HoverHandler { id: hover }

    // Too long to fit, it keeps its end in view: the innermost names are
    // the ones that say where the list is. The wheel, or a drag along the
    // strip, scrolls back to the outer ones.
    WheelHandler {
        enabled: bar.overflows
        acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
        onWheel: function (event) {
            var d = event.pixelDelta.x || event.pixelDelta.y;
            if (!d)
                d = (event.angleDelta.x || event.angleDelta.y) / 120 * 40;
            bar.scrollBy(d);
        }
    }
    DragHandler {
        id: drag
        enabled: bar.overflows
        target: null
        yAxis.enabled: false
        property real from: 0
        onActiveChanged: if (active) from = bar.scroll
        onTranslationChanged: if (active) {
            bar.scroll = Math.max(0, Math.min(bar.maxScroll,
                                               from + translation.x));
        }
    }

    Row {
        id: path
        anchors.verticalCenter: parent.verticalCenter
        x: bar.overflows ? bar.width - bar.pad - width + bar.scroll
                         : bar.pad
        spacing: bar.gap

        Repeater {
            model: bar.crumbs

            Row {
                required property int index
                required property var modelData
                readonly property bool innermost:
                    index === bar.crumbs.length - 1

                spacing: bar.gap

                Text {
                    visible: index > 0
                    text: "›"
                    font.pixelSize: theme.fontRow
                    color: theme.textDim
                }
                Text {
                    objectName: "crumb"
                    text: modelData.label
                    font.pixelSize: theme.fontRow
                    font.bold: innermost
                    font.underline: crumbMouse.containsMouse
                    color: innermost ? theme.text : theme.textDim

                    MouseArea {
                        id: crumbMouse
                        anchors.fill: parent
                        anchors.margins: -3
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: bar.crumbClicked(modelData.row)
                    }
                    Accessible.role: Accessible.Link
                    Accessible.name: modelData.label
                }
            }
        }
    }

    // Where names run on past an edge, they fade out rather than being cut
    // mid-letter: on the left while outer names are out of sight, on the
    // right once the strip is scrolled back from the end.
    component Fade: Rectangle {
        property bool leading: true
        width: Math.min(40, bar.width / 4)
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.margins: theme.overlay ? 3 : 0
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.0; color: leading ? bar.ground
                                                         : "transparent" }
            GradientStop { position: 1.0; color: leading ? "transparent"
                                                         : bar.ground }
        }
    }
    readonly property color ground: theme.overlay ? theme.pill
                                                  : theme.background
    Fade {
        visible: bar.overflows && bar.scroll < bar.maxScroll
        anchors.left: parent.left
    }
    Fade {
        leading: false
        visible: bar.overflows && bar.scroll > 0
        anchors.right: parent.right
    }
}
