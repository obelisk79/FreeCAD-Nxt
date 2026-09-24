import QtQuick

// A reference pill: "something is wrong with what this names".
// Named when it fits, otherwise its icon. See DESIGN.md rules 4 and 5.
Rectangle {
    id: chip

    property alias text: label.text
    property bool interactive: true
    property bool active: false

    //: Drawn instead of the label when several references share a row.
    property bool compact: false
    //: The referenced object's own FreeCAD icon, served desaturated.
    property url iconUrl: ""

    //: The part of the object this refers to - "Face3", or several - when
    //: the reference is to a sub-element rather than the whole thing.
    property string sub: ""

    // Severity of whatever this chip names - 0 none, 1 warning, 2 error.
    // A feature whose sketch is broken reddens the chip rather than its own
    // label, so the blame lands on the thing that is actually wrong.
    property int severity: 0

    readonly property color ink: chip.active ? theme.accentText
                               : chip.severity >= 2 ? theme.danger
                               : chip.severity >= 1 ? theme.warning
                               : theme.text

    signal clicked()
    signal doubleClicked()
    signal hoveredChanged(bool hovered)

    implicitWidth: chip.compact
                 ? implicitHeight
                 : label.implicitWidth + glyph.width + 14
    implicitHeight: theme.chipHeight
    radius: height / 2
    color: active ? theme.accent : theme.chip
    border.width: 1
    border.color: active ? theme.accent : Qt.rgba(theme.border.r, theme.border.g, theme.border.b, 0.8)
    opacity: hover.hovered && interactive ? 1.0 : 0.92

    Behavior on color { ColorAnimation { duration: 90 } }

    Row {
        anchors.centerIn: parent
        spacing: 3
        visible: !chip.compact

        Text {
            id: glyph
            anchors.verticalCenter: parent.verticalCenter
            text: "◇"       // hollow diamond: a reference, not a child
            font.pixelSize: theme.fontAside
            color: chip.severity > 0 ? chip.ink
                 : chip.active ? theme.accentText
                 : theme.textDim
        }

        Text {
            id: label
            anchors.verticalCenter: parent.verticalCenter
            font.pixelSize: theme.fontSmall
            color: chip.ink
            elide: Text.ElideRight
        }
    }

    Image {
        id: icon
        visible: chip.compact
        anchors.centerIn: parent
        width: Math.round(parent.height * 0.72)
        height: width
        sourceSize.width: width * 2
        sourceSize.height: width * 2
        source: chip.iconUrl
        opacity: hover.hovered ? 1.0 : 0.75
        Behavior on opacity { NumberAnimation { duration: 90 } }
    }

    // A reference to one face of an object is not the same fact as a
    // reference to the object, and the compact form has no room to say so
    // in words. A notch out of the corner does it: a partial reference
    // reads as a partial shape.
    Rectangle {
        visible: chip.compact && chip.sub.length > 0
        width: Math.max(4, Math.round(chip.height * 0.30))
        height: width
        radius: width / 2
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: -1
        color: chip.severity >= 2 ? theme.danger
             : chip.severity >= 1 ? theme.warning
             : theme.textDim
        border.width: 1
        border.color: theme.chip
    }

    HoverHandler {
        id: hover
        enabled: chip.interactive
        cursorShape: Qt.PointingHandCursor
        onHoveredChanged: chip.hoveredChanged(hovered)
    }

    TapHandler {
        enabled: chip.interactive
        // singleTapped rather than tapped: `tapped` fires again as the
        // second half of a double tap, which would re-run the single-click
        // action on the way to the double-click one.
        onSingleTapped: chip.clicked()
        onDoubleTapped: chip.doubleClicked()
    }
}
