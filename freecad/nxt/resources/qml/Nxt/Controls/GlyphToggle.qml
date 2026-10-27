import QtQuick

// A square on/off button showing a glyph: a yes/no that qualifies the
// value before it (Reversed, beside Direction).
//
// A click shows the new state at once; `toggled` follows a frame later,
// so it is drawn before whatever it sets off. Once `checked` changes the
// button shows it; if it never does, it goes back.
Rectangle {
    id: button

    property string glyph: ""
    property string tip: ""
    property bool checked: false
    signal toggled()

    property var pending: undefined
    readonly property bool shown: pending !== undefined ? pending : checked
    readonly property bool held: tap.pressed

    onCheckedChanged: {
        settle.stop();
        pending = undefined;
    }

    function flip() {
        button.pending = !button.shown;
        announce.restart();
        settle.restart();
    }

    Timer {
        id: announce
        interval: 30
        onTriggered: button.toggled()
    }
    Timer {
        id: settle
        interval: 2500
        onTriggered: button.pending = undefined
    }

    width: theme.fieldHeight
    height: theme.fieldHeight
    radius: 3
    activeFocusOnTab: enabled
    color: shown ? (held ? Qt.darker(theme.accent, 1.15) : theme.accent)
         : held ? theme.pressed
         : hover.hovered && enabled ? theme.hover : theme.background
    border.width: activeFocus ? 2 : 1
    border.color: shown || activeFocus ? theme.accent
                : hover.hovered && enabled ? theme.textDim : theme.border
    opacity: enabled ? 1.0 : 0.45

    Behavior on color { ColorAnimation { duration: 70 } }

    Text {
        anchors.centerIn: parent
        text: button.glyph
        font.pixelSize: theme.fontRow
        color: button.shown ? theme.accentText : theme.text
    }

    HoverHandler {
        id: hover
    }
    TapHandler {
        id: tap
        enabled: button.enabled
        onTapped: { button.forceActiveFocus(); button.flip() }
    }
    Keys.onSpacePressed: button.flip()

    NxtToolTip {
        shown: hover.hovered && button.tip.length > 0
        text: button.tip
    }

    Accessible.role: Accessible.CheckBox
    Accessible.name: button.tip
    Accessible.checked: button.shown
}
