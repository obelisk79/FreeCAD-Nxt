import QtQuick
import QtQuick.Controls.Basic

// Nxt's tooltip: Qt Quick's own, drawn in the panel's theme.
//
// In a window of its own (Popup.Window), as the context menu and the
// settings popup are, so a narrow dock does not clip it. Set `visible`
// from a HoverHandler; `delay` holds it back until the pointer settles.
ToolTip {
    id: tip

    popupType: Popup.Window
    delay: 450
    timeout: -1
    padding: 6

    contentItem: Text {
        text: tip.text
        font.pixelSize: theme.fontSmall
        color: theme.text
        wrapMode: Text.NoWrap
    }

    background: Rectangle {
        radius: 4
        color: theme.surface
        border.width: 1
        border.color: theme.border
    }
}
