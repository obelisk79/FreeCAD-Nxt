import QtQuick
import QtQuick.Controls.Basic

// An on/off toggle, in the panel's theme. Nxt's choice over a checkbox for
// any single on/off setting: the state reads from across the room, and
// clicking the label works as well as clicking the track.
//
// Qt's Switch underneath, so Space toggles it, Tab reaches it and a screen
// reader hears a switch and its state; only the drawing is ours. `text` is
// the label, on the left, and the track sits at the right edge.
Switch {
    id: control

    font.pixelSize: theme.fontSmall
    padding: 2
    spacing: 10
    hoverEnabled: true

    indicator: Rectangle {
        implicitWidth: Math.round(theme.rowHeight * 1.4)
        implicitHeight: Math.round(theme.rowHeight * 0.72)
        x: control.width - width - control.rightPadding
        y: (control.height - height) / 2
        radius: height / 2
        color: control.checked ? theme.accent : theme.chip
        border.width: control.visualFocus ? 2 : 1
        border.color: control.visualFocus ? theme.accent
                    : control.checked ? theme.accent : theme.border
        opacity: control.enabled ? 1.0 : 0.45

        Behavior on color { ColorAnimation { duration: 120 } }

        Rectangle {
            readonly property real inset: 2
            width: parent.height - 2 * inset
            height: width
            radius: width / 2
            y: inset
            x: control.checked ? parent.width - width - inset : inset
            color: control.checked ? theme.accentText : theme.background
            border.width: 1
            border.color: theme.border

            Behavior on x {
                NumberAnimation { duration: 120; easing.type: Easing.OutCubic }
            }
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
