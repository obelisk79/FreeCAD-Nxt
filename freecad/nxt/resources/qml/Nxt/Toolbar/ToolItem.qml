import QtQuick
import Nxt.Controls

// One command of the tool strip: icon, optional label, optional dropdown
// arrow. "split" opens the menu from the arrow, "instant" from any click.
// Clicks are announced a frame after release, so the release is drawn
// first and the command may rebuild the strip outside this item's event.
Item {
    id: item

    property int size: 24
    property int iconSize: 16
    property string icon: ""
    property string text: ""
    property string tip: ""
    property bool checked: false
    property string dropdown: ""
    //: Drawn as disabled while still enabled for edit mode's hand.
    property bool dimmed: !enabled
    //: Framed, and its clicks left to the strip's hand.
    property bool editing: false

    readonly property bool hovered: hover.hovered
    readonly property int padding: Math.round((size - iconSize) / 2)
    readonly property int arrowWidth: dropdown === ""
                                      ? 0 : Math.round(iconSize * 0.5)
    readonly property real disabledOpacity: 0.4
    //: After the release is drawn: see the header comment.
    readonly property int announceMs: 30

    signal activated()
    signal menuRequested(point at)

    implicitWidth: content.width + 2 * padding + arrowWidth
    implicitHeight: size

    Rectangle {
        anchors.fill: parent
        radius: 4
        color: press.pressed || item.checked ? theme.pressed : theme.hover
        border.color: item.checked ? theme.accent : "transparent"
        border.width: item.checked ? 1 : 0
        visible: !item.dimmed && (item.hovered || press.pressed || item.checked)
    }

    Rectangle {
        anchors.fill: parent
        visible: item.editing
        radius: 4
        color: "transparent"
        border.color: theme.border
        border.width: 1
    }

    Row {
        id: content
        x: item.padding
        anchors.verticalCenter: parent.verticalCenter
        spacing: item.padding
        opacity: item.dimmed ? item.disabledOpacity : 1

        Image {
            visible: item.icon !== ""
            width: item.iconSize
            height: item.iconSize
            sourceSize: Qt.size(item.iconSize * 2, item.iconSize * 2)
            source: item.icon
            smooth: true
            mipmap: true
        }

        Text {
            visible: item.text !== ""
            anchors.verticalCenter: parent.verticalCenter
            text: item.text
            color: theme.text
            font.pixelSize: theme.fontSmall
        }
    }

    Canvas {
        id: arrow
        visible: item.dropdown !== ""
        width: item.arrowWidth
        height: width
        x: item.width - width - Math.round(item.padding / 2)
        anchors.verticalCenter: parent.verticalCenter
        property color ink: item.hovered ? theme.text : theme.textDim
        onInkChanged: requestPaint()
        onPaint: {
            var ctx = getContext("2d");
            ctx.reset();
            ctx.fillStyle = ink;
            ctx.beginPath();
            ctx.moveTo(0, height * 0.35);
            ctx.lineTo(width, height * 0.35);
            ctx.lineTo(width / 2, height * 0.75);
            ctx.closePath();
            ctx.fill();
        }
    }

    HoverHandler { id: hover }

    MouseArea {
        id: press
        anchors.fill: parent
        enabled: item.enabled && !item.editing
        onClicked: (event) => {
            announce.menu = item.dropdown === "instant"
                || (item.dropdown === "split"
                    && event.x >= item.width - item.arrowWidth - item.padding);
            announce.restart();
        }
    }

    Timer {
        id: announce
        property bool menu: false
        interval: item.announceMs
        onTriggered: menu ? item.menuRequested(item.mapToItem(null, 0, item.height))
                          : item.activated()
    }

    NxtToolTip {
        shown: item.hovered && !press.pressed && !item.editing
        text: item.tip
    }

    Accessible.role: Accessible.Button
    Accessible.name: item.tip.split("\n")[0]
    Accessible.checked: item.checked
}
