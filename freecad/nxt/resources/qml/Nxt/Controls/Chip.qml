import QtQuick

// A reference pill: "something is wrong with what this names".
// Named when it fits, otherwise its icon.
Rectangle {
    id: chip

    property alias text: label.text
    property bool interactive: true
    property bool active: false

    property bool compact: false
    //: Served desaturated.
    property url iconUrl: ""

    //: Sub-element ("Face3") when not the whole object.
    property string sub: ""

    // 0 none, 1 warning, 2 error: the chip reddens, not the row.
    property int severity: 0

    //: Names the object even in icon form.
    property string tip: ""

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
    color: active ? theme.accent
         : chipTap.pressed ? theme.pressed
         : hover.hovered && interactive ? theme.hover : theme.chip
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

    // A notch marks a reference to part of the object.
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
        enabled: chip.interactive || chip.tip.length > 0
        onHoveredChanged: if (chip.interactive)
                              chip.hoveredChanged(hovered)
    }

    NxtToolTip {
        shown: hover.hovered
        text: chip.tip
    }

    TapHandler {
        id: chipTap
        enabled: chip.interactive
        // singleTapped: `tapped` also fires as half of a double tap.
        onSingleTapped: chip.clicked()
        onDoubleTapped: chip.doubleClicked()
    }
}
