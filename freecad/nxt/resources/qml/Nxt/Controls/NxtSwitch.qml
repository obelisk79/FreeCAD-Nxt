import QtQuick
import QtQuick.Controls.Basic

// An on/off toggle: Qt's Switch, drawn in the panel's theme.
//
// Bind `stored` to the value it shows, and act in `changedTo`. A click
// flips the switch at once; `changedTo` follows a frame later, so the
// flip is drawn before whatever the change sets off. The switch then
// follows `stored`, and goes back to it if the change never lands.
Switch {
    id: control

    property bool stored: false
    signal changedTo(bool on)

    font.pixelSize: theme.fontSmall
    padding: 2
    spacing: 10
    hoverEnabled: true
    checked: stored

    onStoredChanged: {
        settle.stop();
        checked = stored;
    }
    onToggled: {
        announce.restart();
        settle.restart();
    }

    Timer {
        id: announce
        interval: 30
        onTriggered: control.changedTo(control.checked)
    }
    Timer {
        id: settle
        interval: 2500
        onTriggered: control.checked = control.stored
    }

    indicator: Rectangle {
        implicitWidth: Math.round(theme.rowHeight * 1.4)
        implicitHeight: Math.round(theme.rowHeight * 0.72)
        x: control.width - width - control.rightPadding
        y: (control.height - height) / 2
        radius: height / 2
        color: control.checked
               ? (control.pressed ? Qt.darker(theme.accent, 1.15)
                  : control.hovered ? Qt.lighter(theme.accent, 1.15)
                  : theme.accent)
               : control.pressed ? theme.pressed
               : control.hovered ? theme.hover : theme.chip
        border.width: 1
        border.color: control.checked ? theme.accent
                    : control.hovered ? theme.text : theme.border
        opacity: control.enabled ? 1.0 : 0.45

        Behavior on color { ColorAnimation { duration: 90 } }

        // Keyboard focus: a ring around the track, clear of it, so it
        // shows on the accent of a switch that is on too. Not for a click.
        Rectangle {
            readonly property real gap: 2
            visible: control.activeFocus
                     && control.focusReason !== Qt.MouseFocusReason
            x: -2 * gap
            y: -2 * gap
            width: parent.width + 4 * gap
            height: parent.height + 4 * gap
            radius: height / 2
            color: "transparent"
            border.width: 2
            border.color: theme.accent
        }

        Rectangle {
            readonly property real inset: 2
            // Held down, the knob stretches toward where it will go.
            width: parent.height - 2 * inset + (control.pressed ? 4 : 0)
            height: parent.height - 2 * inset
            radius: height / 2
            y: inset
            x: control.checked ? parent.width - width - inset : inset
            color: control.checked ? theme.accentText : theme.background
            border.width: 1
            border.color: !control.hovered ? theme.border
                        : control.checked ? Qt.darker(theme.accent, 1.3)
                        : theme.text
            // Hovered, the knob grows a little: something to take hold of.
            scale: control.hovered && !control.pressed ? 1.12 : 1.0
            Behavior on scale { NumberAnimation { duration: 90 } }

            Behavior on x {
                NumberAnimation { duration: 110; easing.type: Easing.OutCubic }
            }
            Behavior on width { NumberAnimation { duration: 80 } }
        }
    }

    contentItem: Text {
        text: control.text
        font: control.font
        color: control.enabled ? theme.text : theme.textDim
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        rightPadding: control.indicator.width + control.spacing
    }
}
