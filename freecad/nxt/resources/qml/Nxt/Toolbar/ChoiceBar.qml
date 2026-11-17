import QtQuick
import Nxt.Controls

// FreeCAD's workbench selector, in the style its preference sets:
// "tabs" as buttons (icon and name, the current one filled), or "combo" as
// one button with the current icon and name that opens the list. `more`
// adds FreeCAD's own + button. Signals are announced a frame after the
// click is drawn.
Item {
    id: bar

    property int size: 24
    property int iconSize: 16
    property var choices: []
    property int current: -1
    property string style: "tabs"
    property bool more: false
    //: Framed, and its clicks left to the strip's hand.
    property bool editing: false
    readonly property int padding: Math.round((size - iconSize) / 2)
    readonly property int announceMs: 30
    readonly property var shown: current >= 0 && current < choices.length
                                 ? choices[current] : ({text: "", icon: ""})

    signal chosen(int index)
    signal menuRequested(point at)
    signal moreRequested(point at)

    implicitWidth: content.implicitWidth
    implicitHeight: size

    // A pill or button: an icon and a name, filled when `on`.
    component Pill: Rectangle {
        id: pill

        property string icon: ""
        property string label: ""
        property bool on: false
        property bool arrow: false
        property alias pressed: press.pressed
        signal tapped(point at)

        width: inner.implicitWidth + 2 * bar.padding
        height: bar.size
        radius: 4
        color: on ? theme.accent
                  : press.pressed ? theme.pressed
                  : hover.hovered ? theme.hover : "transparent"
        border.color: on ? theme.accent : theme.border
        border.width: 1

        Row {
            id: inner
            x: bar.padding
            anchors.verticalCenter: parent.verticalCenter
            spacing: bar.padding

            Image {
                visible: pill.icon !== ""
                anchors.verticalCenter: parent.verticalCenter
                width: bar.iconSize
                height: bar.iconSize
                sourceSize: Qt.size(bar.iconSize * 2, bar.iconSize * 2)
                source: pill.icon
                mipmap: true
            }

            Text {
                visible: pill.label !== ""
                anchors.verticalCenter: parent.verticalCenter
                text: pill.label
                color: pill.on ? theme.accentText : theme.text
                font.pixelSize: theme.fontSmall
            }

            Text {
                visible: pill.arrow
                anchors.verticalCenter: parent.verticalCenter
                text: "▾"
                color: pill.on ? theme.accentText : theme.textDim
                font.pixelSize: theme.fontSmall
            }
        }

        HoverHandler { id: hover }

        MouseArea {
            id: press
            anchors.fill: parent
            enabled: bar.enabled && !bar.editing
            onClicked: announce.restart()
        }

        Timer {
            id: announce
            interval: bar.announceMs
            onTriggered: pill.tapped(pill.mapToItem(null, 0, pill.height))
        }

        Accessible.role: Accessible.Button
        Accessible.name: pill.label
        Accessible.checked: pill.on
    }

    Rectangle {
        anchors.fill: parent
        visible: bar.editing
        radius: 4
        color: "transparent"
        border.color: theme.border
        border.width: 1
    }

    Row {
        id: content
        spacing: bar.padding

        Repeater {
            model: bar.style === "tabs" ? bar.choices.length : 0

            delegate: Pill {
                required property int index
                icon: bar.choices[index].icon
                label: bar.choices[index].text
                on: index === bar.current
                onTapped: if (!on) bar.chosen(index)
            }
        }

        Pill {
            visible: bar.style === "combo"
            icon: bar.shown.icon
            label: bar.shown.text
            arrow: true
            onTapped: (at) => bar.menuRequested(at)
        }

        Pill {
            visible: bar.more
            label: "+"
            arrow: true
            onTapped: (at) => bar.moreRequested(at)
        }
    }
}
