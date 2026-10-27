import QtQuick

// A small square button with a Canvas-drawn icon and a tooltip.
Item {
    id: button

    property var paint: null
    property string tip: ""
    property string name: tip
    //: Drawn hovered, e.g. while its menu is open.
    property bool highlighted: false
    property real iconScale: 0.62
    property real iconAspect: 1.0
    // A HoverHandler, not containsMouse: a MouseArea's hover can stick
    // when the click rebuilds the tree or opens a popup.
    readonly property bool hovered: hover.hovered
    // A click dismisses the tooltip until the pointer leaves and returns.
    property bool tipDismissed: false

    signal clicked(var mouse)

    width: Math.round(theme.rowHeight * 0.9)
    height: width

    Rectangle {
        anchors.fill: parent
        radius: 4
        color: press.pressed ? theme.pressed : theme.hover
        visible: button.hovered || button.highlighted || press.pressed
    }

    Canvas {
        anchors.centerIn: parent
        width: Math.round(button.width * button.iconScale)
        height: Math.round(width * button.iconAspect)
        antialiasing: true
        property color ink: button.hovered ? theme.text : theme.textDim
        onInkChanged: requestPaint()
        onWidthChanged: requestPaint()
        onPaint: {
            var ctx = getContext("2d");
            ctx.reset();
            if (button.paint)
                button.paint(ctx, width, height, ink);
        }
    }

    // A MouseArea, for the click's modifiers: a TapHandler's event point
    // does not carry them.
    HoverHandler {
        id: hover
        onHoveredChanged: if (!hovered) button.tipDismissed = false
    }

    MouseArea {
        id: press
        anchors.fill: parent
        onPressed: button.tipDismissed = true
        // A frame after the release: the release is drawn first, and the
        // action may rebuild the tree under the pointer, which must not
        // happen inside the MouseArea's own event.
        onClicked: function (event) {
            announce.click = {modifiers: event.modifiers,
                              button: event.button};
            announce.restart();
        }
    }
    Timer {
        id: announce
        property var click
        interval: 30
        onTriggered: button.clicked(announce.click)
    }

    NxtToolTip {
        shown: button.hovered && !button.tipDismissed && button.tip !== ""
        text: button.tip
    }

    Accessible.role: Accessible.Button
    Accessible.name: button.name.split("\n")[0]
}
